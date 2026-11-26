"""发工资：金额=区间分红、不触发充值活动、每人每工资日防重、撤销受限、仅管理员。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db as dbmod
from app.models import SalaryPayment
from app.services import salary as salary_service
from tests.conftest import create_merchant_direct, create_user_direct
from tests.test_bonus import add_campaign
from tests.test_players import new_player
from tests.test_sessions import create_session

CN = timezone(timedelta(hours=8))
TODAY = datetime.now(CN).date().isoformat()


def _preview(client, headers, date_from=TODAY, date_to=TODAY):
    return client.get(
        "/api/v1/salary/preview",
        params={"date_from": date_from, "date_to": date_to},
        headers=headers,
    )


def _pay(client, headers, user_ids, date_from=TODAY, date_to=TODAY, note=""):
    return client.post(
        "/api/v1/salary/pay",
        json={"date_from": date_from, "date_to": date_to, "user_ids": user_ids, "note": note},
        headers=headers,
    )


def _bind(client, headers, user_id, player_id):
    return client.post(
        "/api/v1/salary/bind",
        json={"user_id": user_id, "player_id": player_id},
        headers=headers,
    )


def _wallet_balance(client, headers, game_id: str) -> tuple[int, int]:
    body = client.get(
        "/api/v1/players", params={"keyword": game_id}, headers=headers
    ).json()
    row = next((item for item in body["items"] if item["game_id"] == game_id), None)
    assert row is not None, body
    return int(row["deposit_cents"]), int(row["bonus_cents"])


def _staff_with_dividend(client, staff_headers) -> int:
    """让 staff 开一局（tea=300，2 人）→ 分红 300 分。返回该员工 id。"""
    a = new_player(client, staff_headers, "客A")
    b = new_player(client, staff_headers, "客B")
    create_session(client, staff_headers, [a["id"], b["id"]], tea=300)
    return None


def test_pay_amount_equals_dividend_and_campaign_off(client, admin_headers, admin, staff) -> None:
    _staff_with_dividend(client, staff["headers"])
    wallet = new_player(client, admin_headers, "小美钱包")
    # 若发工资走了充值活动，300 分会命中满 100 送 50；关掉后不应产生赠金
    add_campaign(client, admin_headers, 100, 50)

    assert _bind(client, admin_headers, staff["id"], wallet["id"]).status_code == 200

    preview = _preview(client, admin_headers).json()
    item = next(x for x in preview["items"] if x["user_id"] == staff["id"])
    assert item["amount_cents"] == 300
    assert item["salary_player_game_id"] == "小美钱包"
    assert item["paid"] is False

    paid = _pay(client, admin_headers, [staff["id"]])
    assert paid.status_code == 201, paid.text
    assert paid.json()["lines"][0]["amount_cents"] == 300

    deposit, bonus = _wallet_balance(client, admin_headers, "小美钱包")
    assert deposit == 300
    assert bonus == 0  # apply_campaign=False：发工资不触发充值活动赠金

    # 再预览：本工资日已发
    preview2 = _preview(client, admin_headers).json()
    item2 = next(x for x in preview2["items"] if x["user_id"] == staff["id"])
    assert item2["paid"] is True
    assert item2["paid_amount_cents"] == 300


def test_dedup_same_person_same_wage_day(client, admin_headers, staff) -> None:
    _staff_with_dividend(client, staff["headers"])
    wallet = new_player(client, admin_headers, "钱包1")
    _bind(client, admin_headers, staff["id"], wallet["id"])

    assert _pay(client, admin_headers, [staff["id"]]).status_code == 201
    again = _pay(client, admin_headers, [staff["id"]])
    assert again.status_code == 400
    assert "已发过" in again.json()["detail"]


def test_pay_requires_binding(client, admin_headers, staff) -> None:
    _staff_with_dividend(client, staff["headers"])
    resp = _pay(client, admin_headers, [staff["id"]])
    assert resp.status_code == 400
    assert "还没有绑定" in resp.json()["detail"]


def test_pay_zero_dividend_not_listed(client, admin_headers, staff) -> None:
    # 没有任何局，工资为 0，预览里不该出现，pay 也不该发
    preview = _preview(client, admin_headers).json()
    assert not any(x["user_id"] == staff["id"] for x in preview["items"])
    assert _pay(client, admin_headers, [staff["id"]]).status_code == 400


def test_void_batch_restores_and_allows_repay(client, admin_headers, staff) -> None:
    _staff_with_dividend(client, staff["headers"])
    wallet = new_player(client, admin_headers, "钱包2")
    _bind(client, admin_headers, staff["id"], wallet["id"])

    paid = _pay(client, admin_headers, [staff["id"]]).json()
    assert _wallet_balance(client, admin_headers, "钱包2") == (300, 0)

    voided = client.post(
        "/api/v1/salary/void", json={"batch_id": paid["batch_id"]}, headers=admin_headers
    )
    assert voided.status_code == 201, voided.text
    assert _wallet_balance(client, admin_headers, "钱包2") == (0, 0)

    # 冲销后可重新发
    assert _pay(client, admin_headers, [staff["id"]]).status_code == 201


def test_void_blocked_when_wage_consumed(client, admin_headers, staff) -> None:
    _staff_with_dividend(client, staff["headers"])
    wallet = new_player(client, admin_headers, "钱包3")
    _bind(client, admin_headers, staff["id"], wallet["id"])
    paid = _pay(client, admin_headers, [staff["id"]]).json()

    # 把工资花掉（开一局扣茶水），余额不足以退，撤销应被拒
    create_session(client, admin_headers, [wallet["id"]], tea=300)
    voided = client.post(
        "/api/v1/salary/void", json={"batch_id": paid["batch_id"]}, headers=admin_headers
    )
    assert voided.status_code == 400


def test_staff_cannot_pay(client, staff_headers) -> None:
    assert _preview(client, staff_headers).status_code == 403
    assert _pay(client, staff_headers, [1]).status_code == 403


def test_cross_merchant_bind_rejected(client, admin_headers) -> None:
    other_merchant = create_merchant_direct("隔壁店")
    other_user = create_user_direct("other-boss", "admin", merchant_id=other_merchant)
    resp = _bind(client, admin_headers, other_user["id"], 1)
    assert resp.status_code == 404


def _insert_payment(
    merchant_id: int,
    user_id: int,
    player_id: int,
    period_end: str,
    wage_date: str,
    batch_id: str,
    voided: bool = False,
) -> None:
    with dbmod.write_session() as session:
        session.add(
            SalaryPayment(
                merchant_id=merchant_id,
                user_id=user_id,
                player_id=player_id,
                amount_cents=300,
                wage_date=wage_date,
                period_start="2026-11-18T07:00:00+08:00",
                period_end=period_end,
                batch_id=batch_id,
                created_at="2026-11-19T07:04:00+08:00",
                voided_at="2026-11-19T09:00:00+08:00" if voided else None,
            )
        )


def test_next_window_defaults_without_history(client, admin) -> None:
    now_dt = datetime(2026, 11, 20, 9, 0, tzinfo=CN)
    with dbmod.write_session() as session:
        window = salary_service.next_window(session, admin["merchant_id"], now_dt)
    assert window["source"] == "default"
    assert window["start"] == "2026-11-19T08:00:00"
    assert window["end"] == "2026-11-20T08:00:00"


def test_next_window_continues_from_last_paid(client, admin) -> None:
    wallet = new_player(client, admin["headers"], "工资钱包")
    _insert_payment(
        admin["merchant_id"], admin["id"], wallet["id"],
        "2026-11-19T07:03:59+08:00", "2026-11-19", "b1",
    )
    now_dt = datetime(2026, 11, 20, 9, 0, tzinfo=CN)
    with dbmod.write_session() as session:
        window = salary_service.next_window(session, admin["merchant_id"], now_dt)
    assert window["source"] == "last_paid"
    # 上次结束在 07:03:59，续接从 07:04:00 起，无缝不重叠
    assert window["start"] == "2026-11-19T07:04:00"
    assert window["end"] == "2026-11-20T08:00:00"


def test_next_window_ignores_voided_batch(client, admin) -> None:
    wallet = new_player(client, admin["headers"], "工资钱包2")
    _insert_payment(
        admin["merchant_id"], admin["id"], wallet["id"],
        "2026-11-19T07:03:59+08:00", "2026-11-19", "b2", voided=True,
    )
    now_dt = datetime(2026, 11, 20, 9, 0, tzinfo=CN)
    with dbmod.write_session() as session:
        window = salary_service.next_window(session, admin["merchant_id"], now_dt)
    assert window["source"] == "default"


def test_next_window_uses_now_when_anchor_past_morning(client, admin) -> None:
    wallet = new_player(client, admin["headers"], "工资钱包3")
    _insert_payment(
        admin["merchant_id"], admin["id"], wallet["id"],
        "2026-11-20T12:00:00+08:00", "2026-11-20", "b3",
    )
    now_dt = datetime(2026, 11, 20, 14, 48, 30, tzinfo=CN)
    with dbmod.write_session() as session:
        window = salary_service.next_window(session, admin["merchant_id"], now_dt)
    assert window["source"] == "last_paid"
    assert window["start"] == "2026-11-20T12:00:01"
    assert window["end"] == "2026-11-20T14:48:30"


def test_next_window_endpoint(client, admin_headers, staff_headers) -> None:
    body = client.get("/api/v1/salary/next-window", headers=admin_headers)
    assert body.status_code == 200
    data = body.json()
    assert data["source"] == "default"
    assert data["end"] == f"{TODAY}T08:00:00"
    assert (
        client.get("/api/v1/salary/next-window", headers=staff_headers).status_code == 403
    )


def test_records_list_filters_void_and_isolation(
    client, admin_headers, admin, staff, staff_headers
) -> None:
    # 店员无权查看发薪记录
    assert client.get("/api/v1/salary/records", headers=staff_headers).status_code == 403

    # 初始为空
    empty = client.get("/api/v1/salary/records", headers=admin_headers)
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []
    assert empty.json()["summary"]["live_total_cents"] == 0

    # 让 staff 与 admin 各开一局（各自产生 300 分分红）
    p1 = new_player(client, admin_headers, "发薪客A")
    p2 = new_player(client, admin_headers, "发薪客B")
    create_session(client, staff["headers"], [p1["id"], p2["id"]], tea=300)
    create_session(client, admin_headers, [p1["id"], p2["id"]], tea=300)
    w_staff = new_player(client, admin_headers, "员工钱包")
    w_admin = new_player(client, admin_headers, "店长钱包")
    _bind(client, admin_headers, staff["id"], w_staff["id"])
    _bind(client, admin_headers, admin["id"], w_admin["id"])

    # 第一批：同时给两个人发今天工资，然后整批撤销
    batch1 = _pay(
        client, admin_headers, [staff["id"], admin["id"]], note="首批发错"
    ).json()
    assert (
        client.post(
            "/api/v1/salary/void",
            json={"batch_id": batch1["batch_id"], "note": "时间选错"},
            headers=admin_headers,
        ).status_code
        == 201
    )

    # 第二批：只给 staff 重发今天工资
    batch2 = _pay(client, admin_headers, [staff["id"]], note="重发正确").json()

    # 另一家商家也插入一条记录，确保跨商家隔离
    other_merchant = create_merchant_direct("其他店")
    other_user = create_user_direct("other-a", "admin", merchant_id=other_merchant)
    other_player = new_player(client, other_user["headers"], "他店钱包")
    _insert_payment(
        other_merchant,
        other_user["id"],
        other_player["id"],
        f"{TODAY}T23:59:59+08:00",
        TODAY,
        "other-batch",
    )

    all_resp = client.get("/api/v1/salary/records", headers=admin_headers).json()
    assert all_resp["total"] == 2
    assert all_resp["summary"]["live_total_cents"] == 300
    assert all_resp["summary"]["live_batch_count"] == 1
    assert all_resp["summary"]["live_payment_count"] == 1
    assert all_resp["summary"]["voided_total_cents"] == 600
    assert all_resp["summary"]["voided_payment_count"] == 2

    # 最新批次在前
    first, second = all_resp["items"]
    assert first["batch_id"] == batch2["batch_id"]
    assert first["status"] == "live"
    assert first["people_count"] == 1
    assert first["total_cents"] == 300
    assert first["paid_by"]["id"] == admin["id"]
    assert first["lines"][0]["player"]["game_id"] == "员工钱包"

    assert second["batch_id"] == batch1["batch_id"]
    assert second["status"] == "voided"
    assert second["people_count"] == 2
    assert second["total_cents"] == 600
    assert second["voided_by"]["id"] == admin["id"]

    # 按状态、按店员、按日期筛选
    live_only = client.get(
        "/api/v1/salary/records", params={"status": "live"}, headers=admin_headers
    ).json()
    assert live_only["total"] == 1
    assert live_only["items"][0]["batch_id"] == batch2["batch_id"]

    admin_only = client.get(
        "/api/v1/salary/records", params={"user_id": admin["id"]}, headers=admin_headers
    ).json()
    assert admin_only["total"] == 1
    assert admin_only["items"][0]["batch_id"] == batch1["batch_id"]
    assert admin_only["summary"]["voided_total_cents"] == 300

    future_only = client.get(
        "/api/v1/salary/records",
        params={"date_from": "2099-01-01", "date_to": "2099-12-31"},
        headers=admin_headers,
    ).json()
    assert future_only["total"] == 0

    # 分页
    p1 = client.get(
        "/api/v1/salary/records",
        params={"page": 1, "page_size": 1},
        headers=admin_headers,
    ).json()
    assert p1["total"] == 2
    assert len(p1["items"]) == 1
    assert p1["items"][0]["batch_id"] == batch2["batch_id"]
