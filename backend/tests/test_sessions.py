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

