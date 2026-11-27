"""场次：预览扣费、开局、列表。开局只能落在本商家自己的批次里。"""

from __future__ import annotations

from datetime import date as date_cls

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.deps import Actor
from app.errors import AppError, ForbiddenError
from app.models import (
    GameSession,
    LedgerEntry,
    Player,
    SalaryPayment,
    SessionPlayer,
)
from app.serializers import session_player_row, session_row
from app.scope import scoped_get
from app.services import options
from app.services.ai_matching import base_name
from app.services.audit import write_audit
from app.services.deposits import (
    _write_entry,
    apply_bonus_delta,
    apply_cash_delta,
    apply_tea_deduction,
)
from app.services.money import deposit_level
from app.services.players import clean_text, get_player
from app.services.tool_lists import tea_free_name_keys
from app.timeutil import (
    bound_end_text,
    bound_end_text_safe,
    bound_start_text,
    bound_start_text_safe,
    normalize_played_at,
    now_text,
    parse_text,
)

MAX_PLAYERS = 10


def default_name(session: Session, played_at: str, merchant_id: int) -> str:
    moment = parse_text(played_at)
    index = int(
        session.scalar(
            select(func.count())
            .select_from(GameSession)
            .where(
                GameSession.merchant_id == merchant_id,
                GameSession.played_at.startswith(moment.date().isoformat()),
            )
        )
        or 0
    )
    return f"{moment.month}月{moment.day}日 第{index + 1}局"


def _unique_ids(player_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for raw in player_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise AppError("玩家参数不正确") from exc
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def preview_session(
    session: Session, merchant_id: int, player_ids: list[int], tea_fee_cents: int
) -> dict:
    if tea_fee_cents < 0:
        raise AppError("茶水不能为负")
    ids = _unique_ids(player_ids)
    if len(ids) > MAX_PLAYERS:
        raise AppError(f"一局最多 {MAX_PLAYERS} 个人")
    low, high = options.thresholds(session, merchant_id)
    tea_free = tea_free_name_keys(session, merchant_id)

    items: list[dict] = []
    removed: list[str] = []
    for player_id in ids:
        player = get_player(session, player_id, merchant_id)
        if base_name(player.game_id) in tea_free:
            removed.append(player.game_id)
            continue
        before = int(player.deposit_cents) + int(player.bonus_cents)
        bonus_before = int(player.bonus_cents)
        bonus_used = min(bonus_before, int(tea_fee_cents))
        cash_after = int(player.deposit_cents) - (int(tea_fee_cents) - bonus_used)
        bonus_after = bonus_before - bonus_used
        after = cash_after + bonus_after
        items.append(
            {
                "player_id": player.id,
                "game_id": player.game_id,
                "account": player.account,
                "before_cents": before,
                "deduct_cents": int(tea_fee_cents),
                "after_cents": after,
                "deposit_before_cents": int(player.deposit_cents),
                "deposit_after_cents": cash_after,
                "bonus_before_cents": bonus_before,
                "bonus_after_cents": bonus_after,
                "bonus_deduct_cents": bonus_used,
                "level": deposit_level(after, low, high),
                "negative": after < 0,
            }
        )
    negative = [item for item in items if item["negative"]]
    return {
        "items": items,
        "count": len(items),
        "tea_fee_cents": int(tea_fee_cents),
        "tea_total_cents": int(tea_fee_cents) * len(items),
        "negative_count": len(negative),
        "negative_players": [item["game_id"] for item in negative],
        "tea_free_removed": removed,
    }


def open_session(
    session: Session,
    actor: Actor,
    *,
    name: str = "",
    played_at: str | None = None,
    note: str = "",
    tea_fee_cents: int = 0,
    player_ids: list[int] | None = None,
    ip: str = "",
) -> dict:
    if tea_fee_cents < 0:
        raise AppError("茶水不能为负")
    ids = _unique_ids(player_ids or [])
    if not ids:
        raise AppError("请选择玩家")
    if len(ids) > MAX_PLAYERS:
        raise AppError(f"一局最多 {MAX_PLAYERS} 个人")

    merchant_id = actor.merchant_id

    try:
        moment = normalize_played_at(played_at)
    except ValueError as exc:
        raise AppError("场次时间格式不正确") from exc

    players = [get_player(session, player_id, merchant_id) for player_id in ids]
    blocked = [player.game_id for player in players if player.is_blacklisted]
    if blocked:
        raise AppError("黑名单玩家不能开局：" + "、".join(blocked))

    tea_free = tea_free_name_keys(session, merchant_id)
    kept: list[Player] = []
    removed: list[str] = []
    for player in players:
        if base_name(player.game_id) in tea_free:
            removed.append(player.game_id)
        else:
            kept.append(player)
    if not kept:
        raise AppError("选中的玩家都在免茶水名单里，不能开局")
    players = kept

    title = clean_text(name, "场次名称", 64) or default_name(session, moment, merchant_id)
    note_text = clean_text(note, "备注", 200)
    stamp = now_text()

    game = GameSession(
        merchant_id=merchant_id,
        name=title,
        played_at=moment,
        tea_fee_cents=int(tea_fee_cents),
        note=note_text,
        operator_id=actor.id,
        player_count=len(players),
        created_at=stamp,
    )
    session.add(game)
    session.flush()
    game_id = game.id

    members: list[SessionPlayer] = []
    for player in players:
        player_id = player.id
        (
            cash_before,
            cash_after,
            bonus_before,
            bonus_after,
            bonus_used,
        ) = apply_tea_deduction(
            session,
            player_id,
            int(tea_fee_cents),
            merchant_id=merchant_id,
        )
        entry = _write_entry(
            session,
            actor=actor,
            player_id=player_id,
            reason="normal_deduct",
            amount_cents=int(tea_fee_cents),
            deposit_before=cash_before,
            deposit_after=cash_after,
            bonus_before=bonus_before,
            bonus_after=bonus_after,
            bonus_amount_cents=bonus_used,
            batch_id=None,
            session_id=game_id,
            note=note_text,
        )
        member = SessionPlayer(
            session_id=game_id,
            player_id=player_id,
            tea_fee_cents=int(tea_fee_cents),
            balance_before_cents=cash_before + bonus_before,
            balance_after_cents=cash_after + bonus_after,
            ledger_id=entry.id,
        )
        session.add(member)
        members.append(member)

    options.set_int(session, merchant_id, "last_tea_cents", int(tea_fee_cents), actor.id)
    session.flush()

    write_audit(
        session,
        merchant_id=merchant_id,
        user_id=actor.id,
        action="open_session",
        target_type="session",
        target_id=game_id,
        detail=f"开局 {title}，{len(players)} 人，每人 {tea_fee_cents} 分",
        ip=ip,
    )

    refreshed = get_session_model(session, game_id, merchant_id)
    data = session_row(refreshed, members)
    data["tea_free_removed"] = removed
    data["voidable"] = True
    data["void_block_reason"] = None
    data["restorable"] = False
    return data


def _live_salary_windows(
    session: Session, merchant_id: int, operator_ids: set[int]
) -> dict[int, list[tuple[str, str]]]:
    """查询指定操作人所有未撤销发薪记录的统计区间（归一化到秒前缀，便于闭区间比较）。"""
    if not operator_ids:
        return {}
    windows: dict[int, list[tuple[str, str]]] = {}
    rows = session.execute(
        select(
            SalaryPayment.user_id,
            SalaryPayment.period_start,
            SalaryPayment.period_end,
        ).where(
            SalaryPayment.merchant_id == merchant_id,
            SalaryPayment.voided_at.is_(None),
            SalaryPayment.user_id.in_(operator_ids),
        )
    ).all()
    for user_id, period_start, period_end in rows:
        start = bound_start_text_safe(period_start)
        end = bound_end_text_safe(period_end)
        if start and end:
            windows.setdefault(int(user_id), []).append((start[:19], end[:19]))
    return windows


def _in_salary_window(played_at: str, windows: list[tuple[str, str]]) -> bool:
    key = (played_at or "")[:19]
    if not key:
        return False
    return any(start <= key <= end for start, end in windows)


def void_session(
    session: Session,
    actor: Actor,
    session_id: int,
    *,
    note: str = "",
    ip: str = "",
) -> dict:
    """撤回未发薪的一局：软标记场次已撤回，并写正向 session_void 流水把押金/赠金原路退回、局数 -1。

    不删除任何历史流水，余额链与对账恒等式始终成立，且不计入操作人现金差额。
    护栏：
    - 只有开局本人或门店管理员可操作；
    - 不能重复撤回；
    - 场次时间落在操作人未撤销发薪区间内的，禁止撤回；
    - 参与玩家已被软删除的，禁止撤回。
    """
    merchant_id = actor.merchant_id
    game = get_session_model(session, session_id, merchant_id)
    game_id = int(game.id)
    game_name = game.name or str(game_id)
    game_operator_id = int(game.operator_id)
    game_played_at = game.played_at

    if not (actor.is_admin or game_operator_id == int(actor.id)):
        raise ForbiddenError("只有开局本人或管理员能撤回这一局")

    if game.voided_at is not None:
        raise AppError("这一局已经撤回过了")

    salary_windows = _live_salary_windows(session, merchant_id, {game_operator_id})
    if _in_salary_window(game_played_at, salary_windows.get(game_operator_id, [])):
        raise AppError("这一局所在时段已发工资，不能撤回；如需撤回请先在「发薪记录」撤销对应批次。")

    members = list(
        session.scalars(
            select(SessionPlayer).where(SessionPlayer.session_id == game_id)
        )
    )
    member_count = len(members)

    deleted_names: list[str] = []
    reversals: list[tuple[int, int, int, int]] = []
    for member in members:
        player = session.get(Player, int(member.player_id))
        if player is None or int(player.merchant_id) != merchant_id or player.deleted_at is not None:
            deleted_names.append(player.game_id if player else f"#{member.player_id}")
            continue
        entry = (
            session.get(LedgerEntry, int(member.ledger_id)) if member.ledger_id else None
        )
        if entry is None or int(entry.session_id or 0) != game_id:
            raise AppError("找不到这一局的扣费流水，无法撤回")
        amount_cents = int(entry.amount_cents)
        bonus_used = int(entry.bonus_amount_cents)
        reversals.append(
            (int(member.player_id), int(entry.id), amount_cents - bonus_used, bonus_used)
        )

    if deleted_names:
        raise AppError(
            "玩家 " + "、".join(sorted(set(deleted_names))) + " 已被删除，无法撤回这一局"
        )

    clean_note = clean_text(note, "备注", 200)
    entry_note = f"撤回 {game_name}：{clean_note}" if clean_note else f"撤回 {game_name}"
    entry_note = entry_note[:200]
    stamp = now_text()

    for player_id, orig_entry_id, cash_used, bonus_used in reversals:
        cash_before, cash_after, bonus_before, bonus_after = apply_cash_delta(
            session, player_id, cash_used, merchant_id=merchant_id, games_delta=-1
        )
        if bonus_used:
            _, cash_after, _, bonus_after = apply_bonus_delta(
                session, player_id, bonus_used, merchant_id=merchant_id
            )
        amount_cents = cash_used + bonus_used
        before_total = cash_before + bonus_before
        after_total = cash_after + bonus_after
        session.add(
            LedgerEntry(
                merchant_id=merchant_id,
                player_id=player_id,
                batch_id=None,
                session_id=game_id,
                reason="session_void",
                amount_cents=amount_cents,
                balance_before_cents=before_total,
                balance_after_cents=after_total,
                bonus_amount_cents=bonus_used,
                deposit_after_cents=cash_after,
                bonus_after_cents=bonus_after,
                reverses_ledger_id=orig_entry_id,
                counterparty_player_id=None,
                transfer_group_id=None,
                operator_id=actor.id,
                note=entry_note,
                created_at=stamp,
            )
        )

    # apply_cash_delta / apply_bonus_delta 会调用 expire_all()，重新加载后再标软撤回
    game = get_session_model(session, game_id, merchant_id)
    game.voided_at = stamp
    game.voided_by = actor.id
    game.void_note = clean_note
    session.flush()

    detail = f"撤回场次 {game_name}，退回 {member_count} 人押金"
    if clean_note:
        detail = f"{detail}（{clean_note}）"
    write_audit(
        session,
        merchant_id=merchant_id,
        user_id=actor.id,
        action="void_session",
        target_type="session",
        target_id=game_id,
        detail=detail[:200],
        ip=ip,
    )
    return {
        "voided": True,
        "session_id": game_id,
        "restored_player_count": member_count,
        "voided_at": stamp,
        "void_note": clean_note,
    }


def restore_session(
    session: Session,
    actor: Actor,
    session_id: int,
    *,
    note: str = "",
    ip: str = "",
) -> dict:
    """管理员恢复误撤回的场次：清除软撤回标记，并按原茶水为每位参与者重扣茶水（新写 normal_deduct 流水）、局数 +1。

    不删除或修改任何历史流水，保留原场次操作人与开局时间，对账恒等式始终成立。
    护栏（与撤回对称）：
    - 仅门店管理员可操作；
    - 场次必须处于已撤回状态；
    - 场次时间不能落入原操作人未撤销的发薪区间；
    - 参与玩家均未被软删除。
    """
    if not actor.is_admin:
        raise ForbiddenError("只有管理员能恢复已撤回的场次")

    merchant_id = actor.merchant_id
    game = get_session_model(session, session_id, merchant_id)
    game_id = int(game.id)
    game_name = game.name or str(game_id)
    game_operator_id = int(game.operator_id)
    game_played_at = game.played_at

    if game.voided_at is None:
        raise AppError("这一局未被撤回，无需恢复")

    salary_windows = _live_salary_windows(session, merchant_id, {game_operator_id})
    if _in_salary_window(game_played_at, salary_windows.get(game_operator_id, [])):
        raise AppError(
            "这一局所在时段已发工资，不能恢复；如需恢复请先在「发薪记录」撤销对应批次。"
        )

    members = list(
        session.scalars(
            select(SessionPlayer).where(SessionPlayer.session_id == game_id)
        )
    )
    if not members:
        raise AppError("这一局没有参与玩家记录，无法恢复")

    deleted_names: list[str] = []
    targets: list[tuple[int, int, int, int | None]] = []
    for member in members:
        player = session.get(Player, int(member.player_id))
        if (
            player is None
            or int(player.merchant_id) != merchant_id
            or player.deleted_at is not None
        ):
            deleted_names.append(player.game_id if player else f"#{member.player_id}")
            continue
        last_void_id = session.scalar(
            select(LedgerEntry.id)
            .where(
                LedgerEntry.merchant_id == merchant_id,
                LedgerEntry.session_id == game_id,
                LedgerEntry.player_id == int(member.player_id),
                LedgerEntry.reason == "session_void",
            )
            .order_by(LedgerEntry.id.desc())
            .limit(1)
        )
        targets.append(
            (
                int(member.id),
                int(member.player_id),
                int(member.tea_fee_cents),
                int(last_void_id) if last_void_id is not None else None,
            )
        )

    if deleted_names:
        raise AppError(
            "玩家 " + "、".join(sorted(set(deleted_names))) + " 已被删除，无法恢复这一局"
        )

    clean_note = clean_text(note, "备注", 200)
    entry_note = (
        f"恢复误撤回 {game_name}：{clean_note}"
        if clean_note
        else f"恢复误撤回 {game_name}"
    )[:200]

    for member_id, player_id, tea_fee_cents, last_void_id in targets:
        (
            cash_before,
            cash_after,
            bonus_before,
            bonus_after,
            bonus_used,
        ) = apply_tea_deduction(
            session,
            player_id,
            tea_fee_cents,
            merchant_id=merchant_id,
        )
        entry = _write_entry(
            session,
            actor=actor,
            player_id=player_id,
            reason="normal_deduct",
            amount_cents=tea_fee_cents,
            deposit_before=cash_before,
            deposit_after=cash_after,
            bonus_before=bonus_before,
            bonus_after=bonus_after,
            bonus_amount_cents=bonus_used,
            batch_id=None,
            session_id=game_id,
            reverses_ledger_id=last_void_id,
            note=entry_note,
        )
        member_row = session.get(SessionPlayer, member_id)
        if member_row is not None:
            member_row.ledger_id = entry.id

    game = get_session_model(session, game_id, merchant_id)
    game.voided_at = None
    game.voided_by = None
    game.void_note = ""
    session.flush()

    detail = f"恢复场次 {game_name}，重扣 {len(targets)} 人茶水"
    if clean_note:
        detail = f"{detail}（{clean_note}）"
    write_audit(
        session,
        merchant_id=merchant_id,
        user_id=actor.id,
        action="restore_session",
        target_type="session",
        target_id=game_id,
        detail=detail[:200],
        ip=ip,
    )
    return {
        "restored": True,
        "session_id": game_id,
        "charged_player_count": len(targets),
    }


def get_session_model(session: Session, session_id: int, merchant_id: int) -> GameSession:
    return scoped_get(session, GameSession, session_id, merchant_id, "找不到这个场次")


def list_sessions(
    session: Session,
    merchant_id: int,
    *,
    keyword: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    operator_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    actor_id: int | None = None,
    is_admin: bool = False,
    include_voided: bool = False,
) -> dict:
    page = max(1, int(page))
    page_size = min(200, max(1, int(page_size)))

    conditions = [GameSession.merchant_id == merchant_id]
    if not include_voided:
        conditions.append(GameSession.voided_at.is_(None))
    if operator_id is not None:
        conditions.append(GameSession.operator_id == int(operator_id))
    text = (keyword or "").strip()
    if text:
        like = f"%{text}%"
        matched_players = (
            select(SessionPlayer.session_id)
            .join(Player, Player.id == SessionPlayer.player_id)
            .where(Player.game_id.like(like), Player.merchant_id == merchant_id)
        )
        conditions.append(
            or_(GameSession.name.like(like), GameSession.id.in_(matched_players))
        )
    try:
        if date_from:
            conditions.append(GameSession.played_at >= bound_start_text(date_from))
        if date_to:
            conditions.append(GameSession.played_at <= bound_end_text(date_to))
    except ValueError as exc:
        raise AppError("时间格式不正确，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM") from exc

    total = int(
        session.scalar(
            select(func.count()).select_from(GameSession).where(*conditions)
        )
        or 0
    )
    games = list(
        session.scalars(
            select(GameSession)
            .where(*conditions)
            .order_by(GameSession.played_at.desc(), GameSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    members: dict[int, list[SessionPlayer]] = {}
    if games:
        ids = [game.id for game in games]
        for item in session.scalars(
            select(SessionPlayer).where(SessionPlayer.session_id.in_(ids))
        ):
            members.setdefault(item.session_id, []).append(item)

    void_status = _void_status_map(
        session, merchant_id, games, members, actor_id=actor_id, is_admin=is_admin
    )
    items = []
    for game in games:
        row = session_row(game, members.get(game.id, []))
        can_void, block_reason, can_restore = void_status.get(
            int(game.id), (False, None, False)
        )
        row["voidable"] = can_void
        row["void_block_reason"] = block_reason
        row["restorable"] = can_restore
        items.append(row)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _void_status_map(
    session: Session,
    merchant_id: int,
    games: list[GameSession],
    members: dict[int, list[SessionPlayer]],
    *,
    actor_id: int | None,
    is_admin: bool,
) -> dict[int, tuple[bool, str | None, bool]]:
    """计算每个场次当前能否撤回、不可撤回原因，以及管理员能否恢复已撤回场次。"""
    result: dict[int, tuple[bool, str | None, bool]] = {}
    if not games:
        return result

    operator_ids = {int(game.operator_id) for game in games}
    salary_windows = _live_salary_windows(session, merchant_id, operator_ids)

    player_ids = {int(m.player_id) for rows in members.values() for m in rows}
    deleted_players: set[int] = set()
    if player_ids:
        deleted_players = set(
            int(pid)
            for pid in session.scalars(
                select(Player.id).where(
                    Player.merchant_id == merchant_id,
                    Player.id.in_(player_ids),
                    Player.deleted_at.is_not(None),
                )
            )
        )

    for game in games:
        gid = int(game.id)
        rows = members.get(gid, [])
        in_salary = _in_salary_window(
            game.played_at, salary_windows.get(int(game.operator_id), [])
        )
        has_deleted_or_empty = not rows or any(
            int(m.player_id) in deleted_players for m in rows
        )
        if game.voided_at is not None:
            can_restore = (
                bool(is_admin) and not in_salary and not has_deleted_or_empty
            )
            result[gid] = (False, "already_voided", can_restore)
            continue
        allowed = bool(is_admin) or (
            actor_id is not None and int(game.operator_id) == int(actor_id)
        )
        if not allowed:
            result[gid] = (False, "no_permission", False)
            continue
        if in_salary:
            result[gid] = (False, "salary_paid", False)
            continue
        if has_deleted_or_empty:
            result[gid] = (False, "player_deleted", False)
            continue
        result[gid] = (True, None, False)
    return result


def get_session_detail(
    session: Session,
    session_id: int,
    merchant_id: int,
    *,
    actor_id: int | None = None,
    is_admin: bool = False,
) -> dict:
    game = get_session_model(session, session_id, merchant_id)
    players = list(
        session.scalars(select(SessionPlayer).where(SessionPlayer.session_id == session_id))
    )
    data = session_row(game, players)
    can_void, block_reason, can_restore = _void_status_map(
        session,
        merchant_id,
        [game],
        {int(game.id): players},
        actor_id=actor_id,
        is_admin=is_admin,
    ).get(int(game.id), (False, None, False))
    data["voidable"] = can_void
    data["void_block_reason"] = block_reason
    data["restorable"] = can_restore
    return data


def session_preview_rows(
    session: Session, session_id: int, merchant_id: int
) -> list[dict]:
    get_session_model(session, session_id, merchant_id)
    rows = list(
        session.scalars(select(SessionPlayer).where(SessionPlayer.session_id == session_id))
    )
    return [session_player_row(item) for item in rows]
