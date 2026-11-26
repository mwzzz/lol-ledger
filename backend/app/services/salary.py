"""发工资：把某位店员某「工资日」的分红，加押金到其绑定的工资账户。

口径完全复用操作人汇总：工资额 = 该区间本人分红（dividend_cents），与「生成工资汇总」
文字里的数字一致。金额一律由服务端按区间重算，前端只决定「给谁发 / 发到哪个账户」。

安全约束：
- 只有门店管理员可操作（接口层 require_admin）。
- 加押金 apply_campaign=False，发工资不触发充值活动赠金。
- 每人每「工资日」只能有一条未冲销发放记录（DB 唯一索引兜底 + 这里先判重）。
- 撤销 = 对每个账户退押金，受退押金规则限制（余额不足或有赠金则拒绝），整批同事务。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import String, case, cast, desc, func, select
from sqlalchemy.orm import Session

from app.deps import Actor
from app.errors import AppError, NotFoundError
from app.models import LedgerEntry, Player, SalaryPayment, User
from app.services import deposits
from app.services import summary as summary_service
from app.services.players import clean_text, get_player
from app.timeutil import CN_TZ, now_cn, now_text, parse_text


def _dividend_by_user(session: Session, merchant_id: int, start_text: str, end_text: str) -> dict[int, int]:
    data = summary_service.operator_summary(session, merchant_id, start_text, end_text)
    out: dict[int, int] = {}
    for row in data["rows"]:
        user = row["user"]
        if user and int(row["dividend_cents"]) > 0:
            out[int(user["id"])] = int(row["dividend_cents"])
    return out


def preview(session: Session, merchant_id: int, date_from: str | None, date_to: str | None) -> dict:
    """列出该区间工资>0 的店员，附绑定账户与「本工资日是否已发」。"""
    start_text, end_text = summary_service.parse_bounds(date_from, date_to)
    wage_date = start_text[:10]
    dividends = _dividend_by_user(session, merchant_id, start_text, end_text)

    users = {
        user.id: user
        for user in session.scalars(select(User).where(User.merchant_id == merchant_id))
    }
    players = {
        player.id: player
        for player in session.scalars(select(Player).where(Player.merchant_id == merchant_id))
    }
    paid: dict[int, dict] = {
        int(row[0]): {"amount_cents": int(row[1]), "batch_id": row[2]}
        for row in session.execute(
            select(
                SalaryPayment.user_id,
                SalaryPayment.amount_cents,
                SalaryPayment.batch_id,
            ).where(
                SalaryPayment.merchant_id == merchant_id,
                SalaryPayment.wage_date == wage_date,
                SalaryPayment.voided_at.is_(None),
            )
        )
    }

    items: list[dict] = []
    for user_id, amount_cents in dividends.items():
        user = users.get(user_id)
        if user is None:
            continue
        bound_player = players.get(int(user.salary_player_id)) if user.salary_player_id else None
        paid_row = paid.get(user_id)
        items.append(
            {
                "user_id": user_id,
                "display_name": user.display_name or user.username,
                "amount_cents": amount_cents,
                "salary_player_id": int(user.salary_player_id) if user.salary_player_id else None,
                "salary_player_game_id": bound_player.game_id if bound_player else None,
                "paid": paid_row is not None,
                "paid_amount_cents": paid_row["amount_cents"] if paid_row else 0,
                "paid_batch_id": paid_row["batch_id"] if paid_row else None,
            }
        )
    items.sort(key=lambda item: -item["amount_cents"])
    return {
        "wage_date": wage_date,
        "start_text": start_text,
        "end_text": end_text,
        "items": items,
        "total_cents": sum(item["amount_cents"] for item in items),
    }


def next_window(
    session: Session, merchant_id: int, now_dt: datetime | None = None
) -> dict:
    """「续接上次发薪」建议区间：起点接上次发薪结束后的下一秒，终点默认今天 08:00。

    若上次结束已晚于今天 08:00，则终点顺延到当前时间（避免夹成 0 秒空区间）。
    没有未冲销发放记录时，回落到汇总默认「今天-1天 08:00 ～ 今天 08:00」。
    """
    now_cn_dt = (now_dt or now_cn()).astimezone(CN_TZ).replace(microsecond=0)
    today = now_cn_dt.date()
    end_dt = datetime(today.year, today.month, today.day, 8, 0, tzinfo=CN_TZ)

    anchor_end = session.scalar(
        select(func.max(SalaryPayment.period_end)).where(
            SalaryPayment.merchant_id == merchant_id,
            SalaryPayment.voided_at.is_(None),
        )
    )

    start_dt: datetime | None = None
    source = "default"
    if anchor_end:
        try:
            start_dt = parse_text(anchor_end) + timedelta(seconds=1)
        except ValueError:
            start_dt = None
        else:
            source = "last_paid"
            if start_dt > end_dt:
                end_dt = max(start_dt, now_cn_dt)
    if start_dt is None:
        start_dt = end_dt - timedelta(days=1)
        source = "default"

    return {
        "start": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "end": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": source,
        "anchor_end": anchor_end,
    }


def bind(session: Session, actor: Actor, user_id: int, player_id: int | None) -> dict:
    """把店员的工资账户绑定到某个玩家（player_id 为空表示解绑）。"""
    merchant_id = actor.merchant_id
    user = session.get(User, int(user_id))
    if user is None or int(user.merchant_id) != merchant_id:
        raise NotFoundError("找不到该店员")
    if player_id is not None:
        get_player(session, int(player_id), merchant_id)
        user.salary_player_id = int(player_id)
    else:
        user.salary_player_id = None
    session.flush()
    return {"user_id": user_id, "salary_player_id": user.salary_player_id}


def pay(
    session: Session,
    actor: Actor,
    date_from: str | None,
    date_to: str | None,
    user_ids: list[int],
    note: str = "",
) -> dict:
    """给选定店员按区间分红加押金发工资；整批同事务，任一校验不过则全部回滚。"""
    merchant_id = actor.merchant_id
    start_text, end_text = summary_service.parse_bounds(date_from, date_to)
    wage_date = start_text[:10]
    dividends = _dividend_by_user(session, merchant_id, start_text, end_text)

    clean_note = clean_text(note, "备注", 200) or f"工资 {wage_date}"
    batch_id = uuid4().hex
    paid_lines: list[dict] = []
    seen: set[int] = set()

    for raw_id in user_ids:
        user_id = int(raw_id)
        if user_id in seen:
            continue
        seen.add(user_id)

        amount_cents = dividends.get(user_id, 0)
        if amount_cents <= 0:
            raise AppError("选中的人里有该区间工资为 0 的，请刷新后重试")

        user = session.get(User, user_id)
        if user is None or int(user.merchant_id) != merchant_id:
            raise NotFoundError("找不到该店员")
        name = user.display_name or user.username
        if not user.salary_player_id:
            raise AppError(f"{name} 还没有绑定工资账户，请先绑定")

        player_id = int(user.salary_player_id)
        get_player(session, player_id, merchant_id)

        already = session.scalar(
            select(SalaryPayment.id).where(
                SalaryPayment.merchant_id == merchant_id,
                SalaryPayment.user_id == user_id,
                SalaryPayment.wage_date == wage_date,
                SalaryPayment.voided_at.is_(None),
            )
        )
        if already is not None:
            raise AppError(f"{name} 在 {wage_date} 已发过工资，如需重发请先撤销那笔")

        result = deposits.add_deposit(
            session, actor, player_id, amount_cents, clean_note, apply_campaign=False
        )
        entry_id = int(result["entry"]["id"])
        session.add(
            SalaryPayment(
                merchant_id=merchant_id,
                user_id=user_id,
                player_id=player_id,
                amount_cents=amount_cents,
                wage_date=wage_date,
                period_start=start_text,
                period_end=end_text,
                batch_id=batch_id,
                ledger_entry_id=entry_id,
                note=clean_note,
                created_at=now_text(),
            )
        )
        paid_lines.append(
            {
                "user_id": user_id,
                "display_name": name,
                "player_id": player_id,
                "amount_cents": amount_cents,
                "ledger_entry_id": entry_id,
            }
        )

    if not paid_lines:
        raise AppError("没有需要发放的工资")

    session.flush()
    return {
        "batch_id": batch_id,
        "wage_date": wage_date,
        "lines": paid_lines,
        "total_cents": sum(line["amount_cents"] for line in paid_lines),
    }


def void_batch(session: Session, actor: Actor, batch_id: str, note: str = "") -> dict:
    """整批撤销：对每笔发放退押金并标记冲销。受退押金规则限制，任一失败整批回滚。"""
    merchant_id = actor.merchant_id
    payments = list(
        session.scalars(
            select(SalaryPayment).where(
                SalaryPayment.merchant_id == merchant_id,
                SalaryPayment.batch_id == batch_id,
                SalaryPayment.voided_at.is_(None),
            )
        )
    )
    if not payments:
        raise AppError("这批工资没有可撤销的记录（可能已撤销或不存在）")

    clean_note = clean_text(note, "备注", 200)
    voided: list[dict] = []
    for sp in payments:
        amount_cents = int(sp.amount_cents)
        label = f"撤销工资 {sp.wage_date}"
        if clean_note:
            label = f"{label}：{clean_note}"
        deposits.refund(session, actor, int(sp.player_id), amount_cents, label)
        sp.voided_at = now_text()
        sp.voided_by = actor.id
        voided.append(
            {
                "user_id": int(sp.user_id),
                "player_id": int(sp.player_id),
                "amount_cents": amount_cents,
            }
        )

    session.flush()
    return {
        "batch_id": batch_id,
        "voided": voided,
        "total_cents": sum(item["amount_cents"] for item in voided),
    }


def _user_brief(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": int(user.id),
        "username": user.username,
        "display_name": user.display_name or user.username,
    }


def list_records(
    session: Session,
    merchant_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str = "all",
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """按发薪批次分页查询历史发工资记录，附带当前筛选条件下的汇总。"""
    clean_status = status if status in ("all", "live", "voided") else "all"
    from_day = (date_from or "").strip()[:10]
    to_day = (date_to or "").strip()[:10]

    conds = [SalaryPayment.merchant_id == merchant_id]
    if clean_status == "live":
        conds.append(SalaryPayment.voided_at.is_(None))
    elif clean_status == "voided":
        conds.append(SalaryPayment.voided_at.is_not(None))
    if user_id is not None:
        conds.append(SalaryPayment.user_id == int(user_id))
    if from_day:
        conds.append(SalaryPayment.wage_date >= from_day)
    if to_day:
        conds.append(SalaryPayment.wage_date <= to_day)

    batch_key = case(
        (SalaryPayment.batch_id != "", SalaryPayment.batch_id),
        else_=cast(SalaryPayment.id, String),
    )

    summary_row = session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (SalaryPayment.voided_at.is_(None), SalaryPayment.amount_cents),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (SalaryPayment.voided_at.is_not(None), SalaryPayment.amount_cents),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((SalaryPayment.voided_at.is_(None), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((SalaryPayment.voided_at.is_not(None), 1), else_=0)),
                0,
            ),
            func.count(
                func.distinct(
                    case((SalaryPayment.voided_at.is_(None), batch_key), else_=None)
                )
            ),
            func.count(func.distinct(batch_key)),
        ).where(*conds)
    ).one()

    total_batches = int(summary_row[5] or 0)
    summary = {
        "live_total_cents": int(summary_row[0] or 0),
        "voided_total_cents": int(summary_row[1] or 0),
        "live_payment_count": int(summary_row[2] or 0),
        "voided_payment_count": int(summary_row[3] or 0),
        "live_batch_count": int(summary_row[4] or 0),
    }

    if total_batches == 0:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "summary": summary,
        }

    offset = (page - 1) * page_size
    page_keys = list(
        session.scalars(
            select(batch_key)
            .where(*conds)
            .group_by(batch_key)
            .order_by(
                desc(func.max(SalaryPayment.created_at)),
                desc(func.max(SalaryPayment.id)),
            )
            .offset(offset)
            .limit(page_size)
        )
    )
    if not page_keys:
        return {
            "items": [],
            "total": total_batches,
            "page": page,
            "page_size": page_size,
            "summary": summary,
        }

    rows = list(
        session.scalars(
            select(SalaryPayment)
            .where(
                SalaryPayment.merchant_id == merchant_id,
                batch_key.in_(page_keys),
            )
            .order_by(desc(SalaryPayment.amount_cents), SalaryPayment.id)
        )
    )

    user_ids: set[int] = set()
    player_ids: set[int] = set()
    ledger_ids: set[int] = set()
    for sp in rows:
        user_ids.add(int(sp.user_id))
        player_ids.add(int(sp.player_id))
        if sp.voided_by:
            user_ids.add(int(sp.voided_by))
        if sp.ledger_entry_id:
            ledger_ids.add(int(sp.ledger_entry_id))

    ledger_operators: dict[int, int] = {}
    if ledger_ids:
        for entry_id, op_id in session.execute(
            select(LedgerEntry.id, LedgerEntry.operator_id).where(
                LedgerEntry.merchant_id == merchant_id,
                LedgerEntry.id.in_(ledger_ids),
            )
        ):
            if op_id is not None:
                ledger_operators[int(entry_id)] = int(op_id)
                user_ids.add(int(op_id))

    users = (
        {
            int(u.id): u
            for u in session.scalars(
                select(User).where(User.merchant_id == merchant_id, User.id.in_(user_ids))
            )
        }
        if user_ids
        else {}
    )
    players = (
        {
            int(p.id): p
            for p in session.scalars(
                select(Player).where(
                    Player.merchant_id == merchant_id, Player.id.in_(player_ids)
                )
            )
        }
        if player_ids
        else {}
    )

    grouped: dict[str, list[SalaryPayment]] = {key: [] for key in page_keys}
    for sp in rows:
        key = sp.batch_id if sp.batch_id else str(sp.id)
        if key in grouped:
            grouped[key].append(sp)

    items: list[dict] = []
    for key in page_keys:
        group = grouped.get(key) or []
        if not group:
            continue
        first = group[0]
        is_voided = all(sp.voided_at is not None for sp in group)
        paid_by_id = (
            ledger_operators.get(int(first.ledger_entry_id))
            if first.ledger_entry_id
            else None
        )
        voided_at = next((sp.voided_at for sp in group if sp.voided_at), None)
        voided_by_id = next((int(sp.voided_by) for sp in group if sp.voided_by), None)

        lines: list[dict] = []
        for sp in group:
            player = players.get(int(sp.player_id))
            lines.append(
                {
                    "id": int(sp.id),
                    "user": _user_brief(users.get(int(sp.user_id))),
                    "player": {
                        "id": int(sp.player_id),
                        "game_id": player.game_id if player else f"#{sp.player_id}",
                    },
                    "amount_cents": int(sp.amount_cents),
                    "ledger_entry_id": int(sp.ledger_entry_id) if sp.ledger_entry_id else None,
                }
            )

        items.append(
            {
                "batch_id": first.batch_id or str(first.id),
                "wage_date": first.wage_date,
                "period_start": first.period_start,
                "period_end": first.period_end,
                "created_at": first.created_at,
                "note": first.note,
                "status": "voided" if is_voided else "live",
                "total_cents": sum(int(sp.amount_cents) for sp in group),
                "people_count": len(group),
                "paid_by": _user_brief(users.get(paid_by_id)) if paid_by_id else None,
                "voided_at": voided_at,
                "voided_by": _user_brief(users.get(voided_by_id)) if voided_by_id else None,
                "lines": lines,
            }
        )

    return {
        "items": items,
        "total": total_batches,
        "page": page,
        "page_size": page_size,
        "summary": summary,
    }
