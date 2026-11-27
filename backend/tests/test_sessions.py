"""开局：扣费、去重、负数、上限、事务回滚。"""

from __future__ import annotations

from sqlalchemy import text

from app import db as dbmod
from tests.test_players import add_money, new_player


def create_session(
    client,
    headers,
    player_ids: list[int],
    tea: int = 200,
    **extra,
) -> dict:
    payload = {
        "name": extra.pop("name", ""),
        "played_at": extra.pop("played_at", None),
        "note": extra.pop("note", ""),
        "tea_fee_cents": tea,
        "player_ids": player_ids,
    }
    response = client.post("/api/v1/sessions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def void_session(client, headers, session_id: int):
    return client.post(f"/api/v1/sessions/{session_id}/void", headers=headers)


def restore_session(client, headers, session_id: int, note: str = ""):
    payload = {"note": note} if note else None
    return client.post(
        f"/api/v1/sessions/{session_id}/restore", json=payload, headers=headers
    )


def test_open_session_deducts_and_counts(client, admin_headers) -> None:
    ids = [new_player(client, admin_headers, f"队员{i}")["id"] for i in range(3)]
    for pid in ids:
        add_money(client, admin_headers, pid, 1000)

    body = create_session(client, admin_headers, ids, tea=300)
    assert body["player_count"] == 3
    assert body["tea_total_cents"] == 900
    assert body["name"].endswith("第1局")

    for pid in ids:
        detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
        assert detail["deposit_cents"] == 700
        assert detail["games_played"] == 1


def test_open_session_dedup_players(client, admin_headers) -> None:
    first = new_player(client, admin_headers, "重复甲")["id"]
    second = new_player(client, admin_headers, "重复乙")["id"]
    body = create_session(client, admin_headers, [first, first, second], tea=100)
    assert body["player_count"] == 2


def test_open_session_allows_negative(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "余额不足")["id"]
    add_money(client, admin_headers, pid, 100)
    create_session(client, admin_headers, [pid], tea=300)
    detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
    assert detail["deposit_cents"] == -200
    assert detail["deposit_level"] == "low"


def test_zero_tea_writes_zero_entry(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "免单")["id"]
    add_money(client, admin_headers, pid, 500)
    body = create_session(client, admin_headers, [pid], tea=0)
    assert body["tea_total_cents"] == 0
    ledger = client.get(f"/api/v1/players/{pid}/ledger", headers=admin_headers).json()
    assert ledger["items"][0]["reason"] == "normal_deduct"
    assert ledger["items"][0]["amount_cents"] == 0
    detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
    assert detail["deposit_cents"] == 500
    assert detail["games_played"] == 1


def test_session_player_limits(client, admin_headers) -> None:
    players = [new_player(client, admin_headers, f"人{i}")["id"] for i in range(11)]

    empty = client.post(
        "/api/v1/sessions",
        json={"tea_fee_cents": 100, "player_ids": []},
        headers=admin_headers,
    )
    assert empty.status_code == 400

    too_many = client.post(
        "/api/v1/sessions",
        json={"tea_fee_cents": 100, "player_ids": players},
        headers=admin_headers,
    )
    assert too_many.status_code == 400
    assert "10" in too_many.json()["detail"]


def test_bad_player_rolls_back_whole_session(client, admin_headers) -> None:
    good = new_player(client, admin_headers, "好人")["id"]
    add_money(client, admin_headers, good, 1000)

    response = client.post(
        "/api/v1/sessions",
        json={"tea_fee_cents": 300, "player_ids": [good, 999999]},
        headers=admin_headers,
    )
    assert response.status_code == 404
    detail = client.get(f"/api/v1/players/{good}", headers=admin_headers).json()
    assert detail["deposit_cents"] == 1000
    assert detail["games_played"] == 0
    with dbmod.read_session() as db:
        assert db.execute(text("SELECT COUNT(*) FROM sessions")).scalar_one() == 0

    listed = client.get("/api/v1/sessions", headers=admin_headers).json()
    assert listed["total"] == 0


def test_session_players_link_ledger(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "查流水")["id"]
    add_money(client, admin_headers, pid, 1000)
    body = create_session(client, admin_headers, [pid], tea=200)

    assert body["players"][0]["balance_before_cents"] == 1000
    assert body["players"][0]["balance_after_cents"] == 800
    with dbmod.read_session() as db:
        linked = db.execute(
            text(
                "SELECT ledger_id FROM session_players WHERE session_id = :sid"
            ),
            {"sid": body["id"]},
        ).scalar_one()
        reason = db.execute(
            text("SELECT reason FROM ledger WHERE id = :lid"), {"lid": linked}
        ).scalar_one()
    assert reason == "normal_deduct"


def test_open_session_updates_last_tea(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "记茶水")["id"]
    create_session(client, admin_headers, [pid], tea=350)
    settings = client.get("/api/v1/settings", headers=admin_headers).json()
    assert settings["last_tea_cents"] == 350


def test_sessions_sorted_by_played_at_desc(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "排序哥")["id"]
    create_session(
        client, admin_headers, [pid], tea=100, played_at="2026-10-30T10:00:00+08:00"
    )
    create_session(
        client, admin_headers, [pid], tea=100, played_at="2026-10-30T15:00:00+08:00"
    )
    listed = client.get("/api/v1/sessions", headers=admin_headers).json()
    played = [item["played_at"] for item in listed["items"]]
    assert played == sorted(played, reverse=True)


def test_preview_shows_negative_players(client, admin_headers) -> None:
    poor = new_player(client, admin_headers, "穷鬼")["id"]
    add_money(client, admin_headers, poor, 100)
    body = client.post(
        "/api/v1/sessions/preview",
        json={"player_ids": [poor], "tea_fee_cents": 300},
        headers=admin_headers,
    ).json()
    assert body["negative_count"] == 1
    assert body["negative_players"] == ["穷鬼"]
    assert body["items"][0]["after_cents"] == -200


def test_default_session_name_increments_same_day(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "连开哥")["id"]
    first = create_session(
        client,
        admin_headers,
        [pid],
        tea=100,
        played_at="2026-11-13T10:00:00+08:00",
    )
    second = create_session(
        client,
        admin_headers,
        [pid],
        tea=100,
        played_at="2026-11-13T11:00:00+08:00",
    )
    assert first["name"].endswith("第1局")
    assert second["name"].endswith("第2局")


def _tea_free_list_id(client, headers) -> int:
    lists = client.get("/api/v1/tools/name-lists", headers=headers).json()["lists"]
    return next(item for item in lists if item["name"] == "免茶水")["id"]


def test_tea_free_players_are_removed(client, admin_headers) -> None:
    free = new_player(client, admin_headers, "免茶哥#123")
    paid = new_player(client, admin_headers, "正常哥")
    list_id = _tea_free_list_id(client, admin_headers)
    created = client.post(
        f"/api/v1/tools/name-lists/{list_id}/items",
        json={"content": "免茶哥"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text

    body = create_session(
        client,
        admin_headers,
        [free["id"], paid["id"]],
        tea=100,
    )
    assert body["player_count"] == 1
    assert body["players"][0]["game_id"] == "正常哥"
    assert body["tea_free_removed"] == ["免茶哥#123"]

    free_detail = client.get(
        f"/api/v1/players/{free['id']}", headers=admin_headers
    ).json()
    assert free_detail["deposit_cents"] == 0
    assert free_detail["games_played"] == 0


def test_all_tea_free_players_rejected(client, admin_headers) -> None:
    free = new_player(client, admin_headers, "只免茶")["id"]
    list_id = _tea_free_list_id(client, admin_headers)
    client.post(
        f"/api/v1/tools/name-lists/{list_id}/items",
        json={"content": "只免茶"},
        headers=admin_headers,
    )
    response = client.post(
        "/api/v1/sessions",
        json={"tea_fee_cents": 100, "player_ids": [free]},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "免茶水" in response.json()["detail"]


def test_blacklisted_player_cannot_open_session(client, admin_headers) -> None:
    blocked = new_player(client, admin_headers, "黑名单哥", is_blacklisted=True)["id"]
    response = client.post(
        "/api/v1/sessions",
        json={"tea_fee_cents": 100, "player_ids": [blocked]},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "黑名单" in response.json()["detail"]


def test_void_session_restores_cash_and_writes_reversal(client, admin_headers) -> None:
    ids = [new_player(client, admin_headers, f"撤回队{i}")["id"] for i in range(3)]
    for pid in ids:
        add_money(client, admin_headers, pid, 1000)
    game = create_session(client, admin_headers, ids, tea=300)
    for pid in ids:
        detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
        assert detail["deposit_cents"] == 700
        assert detail["games_played"] == 1

    response = client.post(
        f"/api/v1/sessions/{game['id']}/void",
        json={"note": "选错人"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["restored_player_count"] == 3
    assert response.json()["void_note"] == "选错人"

    for pid in ids:
        detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
        assert detail["deposit_cents"] == 1000
        assert detail["games_played"] == 0
        assert detail["total_out_cents"] == 0
        entries = client.get(
            f"/api/v1/players/{pid}/ledger", headers=admin_headers
        ).json()["items"]
        assert [item["reason"] for item in entries] == [
            "session_void",
            "normal_deduct",
            "add_deposit",
        ]
        assert entries[0]["signed_amount_cents"] == 300
        assert entries[0]["reverses_ledger_id"] == entries[1]["id"]

    # /sessions 默认隐藏已撤回局；/records/sessions 保留并标 voided=True
    listed = client.get("/api/v1/sessions", headers=admin_headers).json()["items"]
    assert all(item["id"] != game["id"] for item in listed)
    records = client.get("/api/v1/records/sessions", headers=admin_headers).json()["items"]
    rec = next(item for item in records if item["id"] == game["id"])
    assert rec["voided"] is True
    assert rec["voidable"] is False
    assert rec["void_block_reason"] == "already_voided"
    assert rec["void_note"] == "选错人"

    # 汇总与对账均不计入已撤回局，且差额不受影响
    summary = client.get("/api/v1/summary/operators", headers=admin_headers).json()
    assert summary["totals"]["session_count"] == 0
    assert summary["totals"]["tea_cents"] == 0
    assert summary["totals"]["cash_diff_cents"] == 3000
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True

    # 不可重复撤回
    again = void_session(client, admin_headers, game["id"])
    assert again.status_code == 400
    assert "已经撤回" in again.json()["detail"]


def test_void_session_restores_bonus_first(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "撤赠金哥")["id"]
    add_money(client, admin_headers, pid, 1000)
    client.post(
        f"/api/v1/players/{pid}/bonus", json={"amount_cents": 500}, headers=admin_headers
    )
    game = create_session(client, admin_headers, [pid], tea=600)
    detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
    assert detail["deposit_cents"] == 900
    assert detail["bonus_cents"] == 0

    response = void_session(client, admin_headers, game["id"])
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
    assert detail["deposit_cents"] == 1000
    assert detail["bonus_cents"] == 500
    assert detail["bonus_used_cents"] == 0
    assert detail["games_played"] == 0
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True


def test_void_session_allows_negative_to_recover(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "扣成负")["id"]
    add_money(client, admin_headers, pid, 100)
    game = create_session(client, admin_headers, [pid], tea=300)
    assert client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()[
        "deposit_cents"
    ] == -200

    assert void_session(client, admin_headers, game["id"]).status_code == 200
    detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
    assert detail["deposit_cents"] == 100
    assert detail["games_played"] == 0
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True


def test_void_session_zero_tea(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "免单撤回")["id"]
    add_money(client, admin_headers, pid, 500)
    game = create_session(client, admin_headers, [pid], tea=0)
    assert client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()[
        "games_played"
    ] == 1

    assert void_session(client, admin_headers, game["id"]).status_code == 200
    detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
    assert detail["deposit_cents"] == 500
    assert detail["games_played"] == 0
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True


def test_void_allowed_after_later_deposit_and_new_session(client, admin_headers) -> None:
    """玩家在这局之后又充值、又开新局，仍允许红冲撤回早期未发薪的局，且对账通过。"""
    pid = new_player(client, admin_headers, "后又充值")["id"]
    add_money(client, admin_headers, pid, 1000)
    client.post(
        f"/api/v1/players/{pid}/bonus", json={"amount_cents": 200}, headers=admin_headers
    )
    game1 = create_session(client, admin_headers, [pid], tea=300)  # 扣 200 赠金 + 100 现金 -> 现金 900 赠金 0
    add_money(client, admin_headers, pid, 500)  # 现金 1400 赠金 0
    game2 = create_session(client, admin_headers, [pid], tea=200)  # 现金 1200 赠金 0

    response = void_session(client, admin_headers, game1["id"])
    assert response.status_code == 200, response.text

    detail = client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()
    assert detail["deposit_cents"] == 1300
    assert detail["bonus_cents"] == 200
    assert detail["games_played"] == 1
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True

    # 第 2 局依然健在
    listed = client.get("/api/v1/sessions", headers=admin_headers).json()["items"]
    assert [item["id"] for item in listed] == [game2["id"]]


def test_void_blocked_after_salary_paid_and_restored_after_salary_void(
    client, admin_headers, admin
) -> None:
    pid = new_player(client, admin_headers, "已发薪局")["id"]
    wallet = new_player(client, admin_headers, "店长钱包")["id"]
    add_money(client, admin_headers, pid, 1000)
    game = create_session(client, admin_headers, [pid], tea=300)
    day = game["played_at"][:10]

    assert (
        client.post(
            "/api/v1/salary/bind",
            json={"user_id": admin["id"], "player_id": wallet},
            headers=admin_headers,
        ).status_code
        == 200
    )
    paid = client.post(
        "/api/v1/salary/pay",
        json={"date_from": day, "date_to": day, "user_ids": [admin["id"]]},
        headers=admin_headers,
    )
    assert paid.status_code == 201, paid.text

    # 发完工资后，场次标为 salary_paid，撤回被拦截
    records = client.get("/api/v1/records/sessions", headers=admin_headers).json()["items"]
    rec = next(item for item in records if item["id"] == game["id"])
    assert rec["voidable"] is False
    assert rec["void_block_reason"] == "salary_paid"

    blocked = void_session(client, admin_headers, game["id"])
    assert blocked.status_code == 400
    assert "已发工资" in blocked.json()["detail"]

    # 撤销这批工资后，恢复可撤回
    assert (
        client.post(
            "/api/v1/salary/void",
            json={"batch_id": paid.json()["batch_id"]},
            headers=admin_headers,
        ).status_code
        == 201
    )
    records2 = client.get("/api/v1/records/sessions", headers=admin_headers).json()["items"]
    rec2 = next(item for item in records2 if item["id"] == game["id"])
    assert rec2["voidable"] is True
    assert rec2["void_block_reason"] is None

    assert void_session(client, admin_headers, game["id"]).status_code == 200
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True


def test_void_blocked_when_player_deleted(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "将被删玩家")["id"]
    add_money(client, admin_headers, pid, 300)
    game = create_session(client, admin_headers, [pid], tea=300)
    # 押金已清零，管理员删除该玩家
    assert client.delete(f"/api/v1/players/{pid}", headers=admin_headers).status_code == 204

    records = client.get("/api/v1/records/sessions", headers=admin_headers).json()["items"]
    rec = next(item for item in records if item["id"] == game["id"])
    assert rec["voidable"] is False
    assert rec["void_block_reason"] == "player_deleted"

    blocked = void_session(client, admin_headers, game["id"])
    assert blocked.status_code == 400
    assert "已被删除" in blocked.json()["detail"]


def test_void_requires_owner_or_admin(client, admin_headers, staff_headers, staff) -> None:
    pid = new_player(client, admin_headers, "越权撤回")["id"]
    add_money(client, admin_headers, pid, 1000)
    game = create_session(client, admin_headers, [pid], tea=300)

    blocked = void_session(client, staff_headers, game["id"])
    assert blocked.status_code == 403

    staff_game = create_session(client, staff_headers, [pid], tea=100)
    assert void_session(client, admin_headers, staff_game["id"]).status_code == 200


def test_void_is_tenant_isolated(client, admin_headers, admin_b_headers) -> None:
    pid = new_player(client, admin_headers, "别家撤回")["id"]
    add_money(client, admin_headers, pid, 1000)
    game = create_session(client, admin_headers, [pid], tea=300)

    other = void_session(client, admin_b_headers, game["id"])
    assert other.status_code == 404
    assert client.get(f"/api/v1/players/{pid}", headers=admin_headers).json()[
        "deposit_cents"
    ] == 700


def test_voidable_flag_in_session_list(client, admin_headers) -> None:
    pid = new_player(client, admin_headers, "标记哥")["id"]
    add_money(client, admin_headers, pid, 1000)
    game = create_session(client, admin_headers, [pid], tea=300)

    def _flag(session_id: int) -> bool:
        items = client.get("/api/v1/records/sessions", headers=admin_headers).json()["items"]
        return next(item for item in items if item["id"] == session_id)["voidable"]

    assert _flag(game["id"]) is True
    # 之后再充值也不影响撤回
    add_money(client, admin_headers, pid, 200)
    assert _flag(game["id"]) is True
    assert void_session(client, admin_headers, game["id"]).status_code == 200
    assert _flag(game["id"]) is False


def test_restore_session_recharges_tea_preserves_operator_and_allows_revoid(
    client, admin_headers, staff_headers, staff
) -> None:
    p_cash = new_player(client, admin_headers, "恢复现金哥")["id"]
    p_bonus = new_player(client, admin_headers, "恢复赠金哥")["id"]
    add_money(client, admin_headers, p_cash, 1000)
    add_money(client, admin_headers, p_bonus, 1000)
    client.post(
        f"/api/v1/players/{p_bonus}/bonus",
        json={"amount_cents": 200},
        headers=admin_headers,
    )

    game = create_session(client, staff_headers, [p_cash, p_bonus], tea=300)
    orig_played_at = game["played_at"]

    assert void_session(client, admin_headers, game["id"]).status_code == 200

    # 管理员看到 restorable=True，店员看到 restorable=False
    admin_recs = client.get("/api/v1/records/sessions", headers=admin_headers).json()["items"]
    admin_rec = next(item for item in admin_recs if item["id"] == game["id"])
    assert admin_rec["voided"] is True
    assert admin_rec["restorable"] is True

    staff_recs = client.get("/api/v1/records/sessions", headers=staff_headers).json()["items"]
    staff_rec = next(item for item in staff_recs if item["id"] == game["id"])
    assert staff_rec["restorable"] is False

    # 撤回后操作人汇总为 0
    summary_voided = client.get("/api/v1/summary/operators", headers=admin_headers).json()
    assert summary_voided["totals"]["session_count"] == 0

    # 管理员恢复场次
    res = restore_session(client, admin_headers, game["id"], note="误撤回恢复")
    assert res.status_code == 200, res.text
    assert res.json()["restored"] is True
    assert res.json()["charged_player_count"] == 2

    # 余额、赠金、局数、流水链全部还原
    d_cash = client.get(f"/api/v1/players/{p_cash}", headers=admin_headers).json()
    assert d_cash["deposit_cents"] == 700
    assert d_cash["games_played"] == 1
    assert d_cash["total_out_cents"] == 300

    d_bonus = client.get(f"/api/v1/players/{p_bonus}", headers=admin_headers).json()
    assert d_bonus["deposit_cents"] == 900
    assert d_bonus["bonus_cents"] == 0
    assert d_bonus["games_played"] == 1
    assert d_bonus["bonus_used_cents"] == 200

    entries = client.get(f"/api/v1/players/{p_cash}/ledger", headers=admin_headers).json()["items"]
    assert [e["reason"] for e in entries[:3]] == [
        "normal_deduct",
        "session_void",
        "normal_deduct",
    ]
    assert entries[0]["reverses_ledger_id"] == entries[1]["id"]
    assert "恢复误撤回" in entries[0]["note"]

    # 原操作人与时间完整保留，汇总归位回 staff
    detail = client.get(f"/api/v1/sessions/{game['id']}", headers=admin_headers).json()
    assert detail["voided"] is False
    assert detail["voidable"] is True
    assert detail["restorable"] is False
    assert detail["operator"]["id"] == staff["id"]
    assert detail["played_at"] == orig_played_at

    summary_restored = client.get("/api/v1/summary/operators", headers=admin_headers).json()
    assert summary_restored["totals"]["session_count"] == 1
    assert summary_restored["totals"]["tea_cents"] == 600
    staff_row = next(r for r in summary_restored["rows"] if r["user"]["id"] == staff["id"])
    assert staff_row["session_count"] == 1
    assert staff_row["tea_cents"] == 600
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True

    # 恢复后可以再次正常撤回，且能按最新扣费精确退回赠金与现金
    assert void_session(client, admin_headers, game["id"]).status_code == 200
    d_bonus2 = client.get(f"/api/v1/players/{p_bonus}", headers=admin_headers).json()
    assert d_bonus2["deposit_cents"] == 1000
    assert d_bonus2["bonus_cents"] == 200
    assert d_bonus2["games_played"] == 0
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True


def test_restore_requires_admin_and_is_tenant_isolated(
    client, admin_headers, staff_headers, admin_b_headers
) -> None:
    pid = new_player(client, admin_headers, "权限恢复哥")["id"]
    add_money(client, admin_headers, pid, 1000)
    game = create_session(client, staff_headers, [pid], tea=300)
    assert void_session(client, staff_headers, game["id"]).status_code == 200

    # 店员本人不能恢复
    assert restore_session(client, staff_headers, game["id"]).status_code == 403
    # 别家管理员 404
    assert restore_session(client, admin_b_headers, game["id"]).status_code == 404


def test_restore_blocked_when_not_voided_salary_paid_or_player_deleted(
    client, admin_headers, admin
) -> None:
    pid = new_player(client, admin_headers, "护栏恢复哥")["id"]
    wallet = new_player(client, admin_headers, "恢复工资钱包")["id"]
    add_money(client, admin_headers, pid, 1000)

    # 未撤回场次不能恢复
    game1 = create_session(client, admin_headers, [pid], tea=300)
    not_voided = restore_session(client, admin_headers, game1["id"])
    assert not_voided.status_code == 400
    assert "未被撤回" in not_voided.json()["detail"]

    # 撤回 game1，再开同日 game2 并发薪覆盖该日 -> game1 不可恢复
    game2 = create_session(client, admin_headers, [pid], tea=300)
    assert void_session(client, admin_headers, game1["id"]).status_code == 200
    day = game1["played_at"][:10]
    assert (
        client.post(
            "/api/v1/salary/bind",
            json={"user_id": admin["id"], "player_id": wallet},
            headers=admin_headers,
        ).status_code
        == 200
    )
    paid = client.post(
        "/api/v1/salary/pay",
        json={"date_from": day, "date_to": day, "user_ids": [admin["id"]]},
        headers=admin_headers,
    )
    assert paid.status_code == 201, paid.text

    recs = client.get("/api/v1/records/sessions", headers=admin_headers).json()["items"]
    rec1 = next(item for item in recs if item["id"] == game1["id"])
    assert rec1["restorable"] is False

    blocked_salary = restore_session(client, admin_headers, game1["id"])
    assert blocked_salary.status_code == 400
    assert "已发工资" in blocked_salary.json()["detail"]

    # 撤销发薪后恢复可用
    assert (
        client.post(
            "/api/v1/salary/void",
            json={"batch_id": paid.json()["batch_id"]},
            headers=admin_headers,
        ).status_code
        == 201
    )
    assert restore_session(client, admin_headers, game1["id"]).status_code == 200

    # 参与玩家被软删除后不可恢复
    pid_del = new_player(client, admin_headers, "撤后被删哥")["id"]
    game_del = create_session(client, admin_headers, [pid_del], tea=0)
    assert void_session(client, admin_headers, game_del["id"]).status_code == 200
    assert client.delete(f"/api/v1/players/{pid_del}", headers=admin_headers).status_code == 204
    blocked_del = restore_session(client, admin_headers, game_del["id"])
    assert blocked_del.status_code == 400
    assert "已被删除" in blocked_del.json()["detail"]
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True


def test_restore_after_later_deposit_and_bonus_spend_passes_reconcile(
    client, admin_headers
) -> None:
    """撤回后玩家又充值、或把退回的赠金在别的局花掉了，恢复仍能正确扣费并过对账。"""
    p_a = new_player(client, admin_headers, "撤后充值哥")["id"]
    p_b = new_player(client, admin_headers, "撤后花赠金哥")["id"]
    add_money(client, admin_headers, p_a, 1000)
    add_money(client, admin_headers, p_b, 100)
    client.post(
        f"/api/v1/players/{p_b}/bonus",
        json={"amount_cents": 300},
        headers=admin_headers,
    )

    game1 = create_session(client, admin_headers, [p_a, p_b], tea=300)
    assert void_session(client, admin_headers, game1["id"]).status_code == 200

    # 期间 p_a 新充值 6600，p_b 开新局把退回的 300 赠金用完了
    add_money(client, admin_headers, p_a, 6600)
    create_session(client, admin_headers, [p_b], tea=300)

    assert restore_session(client, admin_headers, game1["id"]).status_code == 200
    d_a = client.get(f"/api/v1/players/{p_a}", headers=admin_headers).json()
    d_b = client.get(f"/api/v1/players/{p_b}", headers=admin_headers).json()
    assert d_a["deposit_cents"] == 7300
    assert d_a["games_played"] == 1
    assert d_b["deposit_cents"] == -200
    assert d_b["bonus_cents"] == 0
    assert d_b["games_played"] == 2
    assert client.get("/api/v1/reconcile", headers=admin_headers).json()["ok"] is True

