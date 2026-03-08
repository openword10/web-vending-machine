import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import web


SERVER_ID = "1001"
ADMIN_PW = "adminpw"


def _create_base_server_db(base_dir: Path):
    db_dir = base_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    server_db = db_dir / f"{SERVER_ID}.db"

    con = sqlite3.connect(server_db)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE info (
            id INTEGER,
            pw TEXT,
            buyer INTEGER,
            expire TEXT,
            cultureid TEXT,
            culturepw TEXT,
            fee INTEGER,
            toss TEXT,
            hide INTEGER
        );
        """
    )
    future_expire = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    cur.execute(
        "INSERT INTO info VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
        (int(SERVER_ID), ADMIN_PW, 0, future_expire, "", "", 0, "", 0),
    )
    cur.execute("CREATE TABLE webhook (buylog TEXT, chargelog TEXT, profile TEXT);")
    cur.execute("INSERT INTO webhook VALUES('', '', '');")
    cur.execute("CREATE TABLE product (name TEXT, money INTEGER, stock TEXT, description TEXT, image_url TEXT);")
    cur.execute("CREATE TABLE user (id INTEGER, money INTEGER, warnings INTEGER, ban INTEGER);")
    con.commit()
    con.close()

    con = sqlite3.connect(server_db)
    web.ensure_server_schema(con)
    cur = con.cursor()
    cur.execute("UPDATE shop SET slug = ?, is_public = 1, name = 'TEST SHOP';", (SERVER_ID,))
    con.commit()
    con.close()

    charge_dir = base_dir / "static" / "uploads" / "charges"
    charge_dir.mkdir(parents=True, exist_ok=True)
    (charge_dir / "receipt.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    _create_base_server_db(tmp_path)
    monkeypatch.setattr(web, "curdir", str(tmp_path) + os.sep)
    web.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with web.app.test_client() as test_client:
        yield test_client, tmp_path


def test_e2e_admin_login_signup_buy_charge_approve(client):
    test_client, tmp_path = client

    resp = test_client.post("/login", data={"id": SERVER_ID, "pw": ADMIN_PW})
    assert resp.status_code == 200
    assert resp.data.decode("utf-8") == "Ok"

    resp = test_client.post(
        "/manage_product",
        data={
            "name": "coin",
            "price": "1000",
            "stock": "S1\nS2\nS3",
            "description": "test product",
            "image_url": "",
        },
    )
    assert resp.status_code == 200
    assert resp.data.decode("utf-8").strip().lower() == "ok"

    resp = test_client.post(
        f"/{SERVER_ID}/auth/signup",
        data={
            "member_id": "buyer1",
            "member_pw": "pw1",
            "discord_id": "buyer#0001",
            "gmail": "buyer@example.com",
        },
    )
    assert resp.status_code == 200
    assert resp.data.decode("utf-8").strip().lower() == "ok"

    resp = test_client.post(
        f"/{SERVER_ID}/charge",
        data={
            "amount": "5000",
            "depositor": "buyer1",
            "image_url": "/static/uploads/charges/receipt.png",
        },
    )
    assert resp.status_code == 200
    assert resp.data.decode("utf-8").strip().lower() == "ok"

    con = sqlite3.connect(tmp_path / "db" / f"{SERVER_ID}.db")
    cur = con.cursor()
    cur.execute("SELECT rowid FROM chargereq ORDER BY rowid DESC LIMIT 1;")
    req_id = cur.fetchone()[0]
    con.close()

    resp = test_client.post("/managereq", json={"type": "accept", "req_id": str(req_id)})
    assert resp.status_code == 200
    assert resp.data.decode("utf-8").strip().lower() == "ok"

    resp = test_client.post(
        f"/{SERVER_ID}/buy",
        data={"product_name": "coin", "qty": "2"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["result"] == "ok"
    assert payload["redirect_url"].startswith(f"/{SERVER_ID}/")

    detail_resp = test_client.get(payload["redirect_url"])
    assert detail_resp.status_code == 200

    con = sqlite3.connect(tmp_path / "db" / f"{SERVER_ID}.db")
    cur = con.cursor()
    cur.execute("SELECT money FROM user WHERE CAST(id AS TEXT) = 'buyer1';")
    balance = int(cur.fetchone()[0])
    cur.execute("SELECT stock FROM product WHERE name = 'coin';")
    stock = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM buylog;")
    buylog_count = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM chargelog;")
    chargelog_count = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM purchase_delivery;")
    delivery_count = int(cur.fetchone()[0])
    cur.execute("SELECT action FROM admin_audit_log;")
    actions = {row[0] for row in cur.fetchall()}
    con.close()

    assert balance == 3000
    assert stock.strip() == "S3"
    assert buylog_count == 1
    assert chargelog_count == 1
    assert delivery_count == 1
    assert "product.create" in actions
    assert "charge.request_accept" in actions
