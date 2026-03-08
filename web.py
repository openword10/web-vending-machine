from flask import Flask, render_template, request, session, redirect, abort, url_for, jsonify
import sqlite3, json
import os
import uuid
import datetime
import re
import io
import hashlib
import urllib.request
import threading
import queue
from datetime import timedelta
from werkzeug.utils import secure_filename
from util import funcs as fc, licensing
from discord_webhook import DiscordEmbed, DiscordWebhook

curdir = os.path.dirname(__file__) + "/"

app = Flask(__name__)
app.secret_key = os.environ.get("VENEX_SECRET_KEY", "venex-dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
_auto_approve_queue = queue.Queue()
_auto_approve_worker_started = False
_auto_approve_worker_lock = threading.Lock()


def _allowed_image_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _save_uploaded_product_image(file_storage):
    if file_storage is None or file_storage.filename == "":
        return None, None
    if not _allowed_image_file(file_storage.filename):
        return None, "?��?지 ?�일 ?�식?� png, jpg, jpeg, webp, gif �?가?�합?�다."

    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(curdir, "static", "uploads", "products")
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, new_name))
    return f"/static/uploads/products/{new_name}", None


def _save_uploaded_charge_image(file_storage):
    if file_storage is None or file_storage.filename == "":
        return None, None
    if not _allowed_image_file(file_storage.filename):
        return None, "이미지 파일 형식은 png, jpg, jpeg, webp, gif만 가능합니다."

    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(curdir, "static", "uploads", "charges")
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, new_name))
    return f"/static/uploads/charges/{new_name}", None


def _save_uploaded_shop_image(file_storage):
    if file_storage is None or file_storage.filename == "":
        return None, None
    if not _allowed_image_file(file_storage.filename):
        return None, "이미지 파일 형식은 png, jpg, jpeg, webp, gif만 가능합니다."

    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(curdir, "static", "uploads", "shops")
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, new_name))
    return f"/static/uploads/shops/{new_name}", None


def _compute_image_hash(image_url):
    raw = _load_image_bytes(image_url)
    if not raw:
        return ""
    return hashlib.sha256(raw).hexdigest()


def _save_uploaded_profile_image(file_storage):
    if file_storage is None or file_storage.filename == "":
        return None, None
    if not _allowed_image_file(file_storage.filename):
        return None, "이미지 파일 형식은 png, jpg, jpeg, webp, gif만 가능합니다."

    try:
        from PIL import Image
    except Exception:
        return None, "이미지 처리 모듈(Pillow)이 필요합니다."

    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(curdir, "static", "uploads", "profiles")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, new_name)
    file_storage.save(file_path)

    try:
        with Image.open(file_path) as img:
            w, h = img.size
            if w > 360 or h > 360:
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                return None, "360곱하기360초과하는 크기입니다"
    except Exception:
        try:
            os.remove(file_path)
        except Exception:
            pass
        return None, "이미지 파일을 읽을 수 없습니다."

    return f"/static/uploads/profiles/{new_name}", None


def get_server_db_path(server_id=None):
    server_id = server_id or session.get("id")
    if not server_id:
        return None
    return os.path.join(curdir, "db", f"{server_id}.db")


def ensure_server_schema(con):
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'shop';")
    if cur.fetchone() is None:
        cur.execute("""
                    CREATE TABLE shop (
                        name TEXT,
                        slug TEXT,
                        description TEXT,
                        logo_url TEXT,
                        banner_url TEXT,
                        theme_color TEXT,
                        is_public INTEGER,
                        bank_account TEXT,
                        bank_owner TEXT,
                        bank_name TEXT,
                        auto_charge_approve INTEGER
                    );
                    """)
        cur.execute(
            "INSERT INTO shop VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            ("VENDIX SHOP", "", "", "", "", "#4f7cff", 0, "", "", "", 0)
        )

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'shop_member';")
    if cur.fetchone() is None:
        cur.execute("""
                    CREATE TABLE shop_member (
                        id TEXT PRIMARY KEY,
                        password TEXT,
                        discord_id TEXT,
                        gmail TEXT,
                        created_at TEXT,
                        profile_image TEXT DEFAULT ''
                    );
                    """)
    else:
        cur.execute("PRAGMA table_info(shop_member);")
        shop_member_columns = {row[1] for row in cur.fetchall()}
        if "profile_image" not in shop_member_columns:
            cur.execute("ALTER TABLE shop_member ADD COLUMN profile_image TEXT DEFAULT '';")
        cur.execute("UPDATE shop_member SET profile_image = '' WHERE profile_image IS NULL;")

    cur.execute("PRAGMA table_info(product);")
    product_columns = {row[1] for row in cur.fetchall()}
    if "description" not in product_columns:
        cur.execute("ALTER TABLE product ADD COLUMN description TEXT DEFAULT '';")
    if "image_url" not in product_columns:
        cur.execute("ALTER TABLE product ADD COLUMN image_url TEXT DEFAULT '';")

    cur.execute("SELECT COUNT(*) FROM shop;")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO shop VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            ("VENDIX SHOP", "", "", "", "", "#4f7cff", 0, "", "", "", 0)
        )

    # Keep old schema but enforce initial visibility as private when value is missing.
    cur.execute("UPDATE shop SET is_public = 0 WHERE is_public IS NULL;")
    cur.execute("UPDATE shop SET is_public = 0 WHERE slug IS NULL OR slug = '';")
    cur.execute("PRAGMA table_info(shop);")
    shop_columns = {row[1] for row in cur.fetchall()}
    if "bank_account" not in shop_columns:
        cur.execute("ALTER TABLE shop ADD COLUMN bank_account TEXT DEFAULT '';")
    if "bank_owner" not in shop_columns:
        cur.execute("ALTER TABLE shop ADD COLUMN bank_owner TEXT DEFAULT '';")
    if "bank_name" not in shop_columns:
        cur.execute("ALTER TABLE shop ADD COLUMN bank_name TEXT DEFAULT '';")
    if "auto_charge_approve" not in shop_columns:
        cur.execute("ALTER TABLE shop ADD COLUMN auto_charge_approve INTEGER DEFAULT 0;")
    cur.execute("UPDATE shop SET bank_account = '' WHERE bank_account IS NULL;")
    cur.execute("UPDATE shop SET bank_owner = '' WHERE bank_owner IS NULL;")
    cur.execute("UPDATE shop SET bank_name = '' WHERE bank_name IS NULL;")
    cur.execute("UPDATE shop SET auto_charge_approve = 0 WHERE auto_charge_approve IS NULL;")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'chargereq';")
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE chargereq (
                created_at TEXT,
                nickname TEXT,
                id TEXT,
                depositor TEXT,
                amount INTEGER,
                image_url TEXT DEFAULT '',
                auto_checked INTEGER DEFAULT 0,
                auto_result TEXT DEFAULT '',
                image_hash TEXT DEFAULT '',
                ocr_fingerprint TEXT DEFAULT ''
            );
            """
        )
    cur.execute("PRAGMA table_info(chargereq);")
    chargereq_columns = {row[1] for row in cur.fetchall()}
    if "auto_checked" not in chargereq_columns:
        cur.execute("ALTER TABLE chargereq ADD COLUMN auto_checked INTEGER DEFAULT 0;")
    if "auto_result" not in chargereq_columns:
        cur.execute("ALTER TABLE chargereq ADD COLUMN auto_result TEXT DEFAULT '';")
    if "image_hash" not in chargereq_columns:
        cur.execute("ALTER TABLE chargereq ADD COLUMN image_hash TEXT DEFAULT '';")
    if "ocr_fingerprint" not in chargereq_columns:
        cur.execute("ALTER TABLE chargereq ADD COLUMN ocr_fingerprint TEXT DEFAULT '';")
    cur.execute("UPDATE chargereq SET auto_checked = 0 WHERE auto_checked IS NULL;")
    cur.execute("UPDATE chargereq SET auto_result = '' WHERE auto_result IS NULL;")
    cur.execute("UPDATE chargereq SET image_hash = '' WHERE image_hash IS NULL;")
    cur.execute("UPDATE chargereq SET ocr_fingerprint = '' WHERE ocr_fingerprint IS NULL;")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'chargelog';")
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE chargelog (
                log_id TEXT,
                method TEXT,
                id TEXT,
                amount INTEGER,
                created_at TEXT,
                nickname TEXT
            );
            """
        )

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'buylog';")
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE buylog (
                log_id TEXT,
                product_name TEXT,
                id TEXT,
                nickname TEXT,
                quantity INTEGER,
                created_at TEXT
            );
            """
        )

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'purchase_delivery';")
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE purchase_delivery (
                order_code TEXT PRIMARY KEY,
                member_id TEXT,
                product_name TEXT,
                quantity INTEGER,
                items_text TEXT,
                created_at TEXT
            );
            """
        )
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'receipt_guard';")
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE receipt_guard (
                image_hash TEXT,
                ocr_fingerprint TEXT,
                approved_at TEXT,
                member_id TEXT,
                amount INTEGER
            );
            """
        )
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'admin_audit_log';")
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE admin_audit_log (
                id TEXT,
                admin_id TEXT,
                action TEXT,
                target TEXT,
                before_json TEXT,
                after_json TEXT,
                ip TEXT,
                created_at TEXT
            );
            """
        )
    con.commit()


def connect_server_db(server_id=None):
    db_path = get_server_db_path(server_id)
    if not db_path or not os.path.isfile(db_path):
        return None
    con = sqlite3.connect(db_path)
    ensure_server_schema(con)
    return con


def fetch_rows_if_table_exists(cur, table_name, query):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?;", (table_name,))
    if cur.fetchone() is None:
        return []
    cur.execute(query)
    return cur.fetchall()


def get_shop_info(cur):
    cur.execute("SELECT * FROM shop LIMIT 1;")
    shop = cur.fetchone()
    if shop is None:
        return ("VENDIX SHOP", "", "", "", "", "#4f7cff", 0, "", "", "", 0)
    if len(shop) < 11:
        shop = tuple(shop) + ("",) * (11 - len(shop))
    return shop


def _table_exists(cur, table_name):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1;", (table_name,))
    return cur.fetchone() is not None


def compute_admin_kpi(cur):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    kpi = {
        "daily_sales": 0,
        "charge_approve_rate": 0.0,
        "blocked_users": 0,
        "top_product_name": "-",
        "top_product_qty": 0,
        "kpi_date": today,
    }

    if _table_exists(cur, "buylog") and _table_exists(cur, "product"):
        cur.execute(
            """
            SELECT COALESCE(SUM(COALESCE(p.money, 0) * COALESCE(b.quantity, 1)), 0)
            FROM buylog b
            LEFT JOIN product p ON p.name = b.product_name
            WHERE substr(COALESCE(b.created_at, ''), 1, 10) = ?;
            """,
            (today,),
        )
        row = cur.fetchone()
        kpi["daily_sales"] = int(row[0] or 0) if row else 0

        cur.execute(
            """
            SELECT b.product_name, COALESCE(SUM(COALESCE(b.quantity, 1)), 0) AS qty_sum
            FROM buylog b
            WHERE substr(COALESCE(b.created_at, ''), 1, 10) = ?
            GROUP BY b.product_name
            ORDER BY qty_sum DESC, b.product_name ASC
            LIMIT 1;
            """,
            (today,),
        )
        top_row = cur.fetchone()
        if top_row is not None:
            kpi["top_product_name"] = str(top_row[0] or "-")
            kpi["top_product_qty"] = int(top_row[1] or 0)

    if _table_exists(cur, "user"):
        cur.execute("SELECT COALESCE(COUNT(*), 0) FROM user WHERE CAST(COALESCE(ban, 0) AS INTEGER) = 1;")
        row = cur.fetchone()
        kpi["blocked_users"] = int(row[0] or 0) if row else 0

    pending_today = 0
    approved_today = 0
    if _table_exists(cur, "chargereq"):
        cur.execute(
            "SELECT COALESCE(COUNT(*), 0) FROM chargereq WHERE substr(COALESCE(created_at, ''), 1, 10) = ?;",
            (today,),
        )
        row = cur.fetchone()
        pending_today = int(row[0] or 0) if row else 0
    if _table_exists(cur, "chargelog"):
        cur.execute(
            "SELECT COALESCE(COUNT(*), 0) FROM chargelog WHERE substr(COALESCE(created_at, ''), 1, 10) = ?;",
            (today,),
        )
        row = cur.fetchone()
        approved_today = int(row[0] or 0) if row else 0

    total_review_base = pending_today + approved_today
    if total_review_base > 0:
        kpi["charge_approve_rate"] = round((approved_today / total_review_base) * 100, 1)

    return kpi


def _normalize_digits(text):
    return re.sub(r"[^0-9]", "", str(text or ""))


def _extract_relative_minutes(text):
    text = str(text or "")
    m = re.search(r"(\d{1,2})\s*분\s*전", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,2})\s*min", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _extract_absolute_datetime(text, now_dt):
    # YYYY-MM-DD HH:MM or YYYY.MM.DD HH:MM
    m = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\D+(\d{1,2}):(\d{2})", text)
    if m:
        try:
            return datetime.datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
            )
        except ValueError:
            pass

    # MM-DD HH:MM (assume current year)
    m = re.search(r"(\d{1,2})[./-](\d{1,2})\D+(\d{1,2}):(\d{2})", text)
    if m:
        try:
            return datetime.datetime(
                now_dt.year,
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
            )
        except ValueError:
            pass

    # HH:MM (assume today)
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        try:
            return now_dt.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        except ValueError:
            pass
    return None


def _load_image_bytes(image_url):
    if not image_url:
        return None
    src = str(image_url).strip()
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=8) as r:
            return r.read()
    if src.startswith("/static/"):
        local_path = os.path.join(curdir, src.lstrip("/").replace("/", os.sep))
    else:
        local_path = src
    if not os.path.isfile(local_path):
        return None
    with open(local_path, "rb") as f:
        return f.read()


def _run_receipt_ocr(image_url):
    global _easyocr_reader
    try:
        import numpy as np
        from PIL import Image
        import easyocr
    except Exception:
        return None, "ocr_module_missing"

    try:
        reader = _easyocr_reader
    except NameError:
        _easyocr_reader = None
        reader = None

    raw = _load_image_bytes(image_url)
    if not raw:
        return None, "image_not_found"
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image_np = np.array(image)
    except Exception:
        return None, "image_open_failed"

    try:
        if reader is None:
            # Python-only OCR engine (no external tesseract binary required).
            _easyocr_reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
            reader = _easyocr_reader
        result = reader.readtext(image_np, detail=0, paragraph=True)
        text = "\n".join([str(x) for x in result if str(x).strip()])
    except Exception:
        return None, "ocr_failed"
    return str(text or ""), None


def _evaluate_auto_approve(ocr_text, bank_account):
    now_dt = datetime.datetime.now()
    text = str(ocr_text or "")
    if not text.strip():
        return False, "ocr_empty"

    # Time validation (within 5 minutes)
    rel_mins = _extract_relative_minutes(text)
    if rel_mins is not None:
        if rel_mins > 5:
            return False, "time_over_5m"
    else:
        abs_dt = _extract_absolute_datetime(text, now_dt)
        if abs_dt is None:
            return False, "time_not_found"
        delta_sec = (now_dt - abs_dt).total_seconds()
        if delta_sec < -60 or delta_sec > 300:
            return False, "time_over_5m"

    # Account number validation
    expected = _normalize_digits(bank_account)
    if not expected:
        return False, "shop_bank_not_set"
    got_digits = _normalize_digits(text)
    if expected not in got_digits:
        return False, "account_not_match"

    return True, "ok"


def _build_ocr_fingerprint(ocr_text, depositor, amount, bank_account):
    text_digits = _normalize_digits(ocr_text)[:120]
    bank_digits = _normalize_digits(bank_account)
    dep = re.sub(r"[^0-9a-zA-Z가-힣]", "", str(depositor or "")).lower()
    base = f"{bank_digits}|{int(amount)}|{dep}|{text_digits}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _is_duplicate_receipt(cur, image_hash, ocr_fingerprint):
    if image_hash:
        cur.execute("SELECT 1 FROM receipt_guard WHERE image_hash = ? LIMIT 1;", (image_hash,))
        if cur.fetchone() is not None:
            return True
    if ocr_fingerprint:
        cur.execute("SELECT 1 FROM receipt_guard WHERE ocr_fingerprint = ? LIMIT 1;", (ocr_fingerprint,))
        if cur.fetchone() is not None:
            return True
    return False


def _approve_charge_request_row(cur, req):
    try:
        amount = int(req[5])
    except (TypeError, ValueError, IndexError):
        return False, "invalid_amount"

    user_id = str(req[3])
    cur.execute("SELECT * FROM user WHERE CAST(id AS TEXT) == ?;", (user_id,))
    user_row = cur.fetchone()
    if user_row is None:
        cur.execute(
            "INSERT INTO user (id, money, warnings, ban) VALUES (?, ?, 0, 0);",
            (user_id, amount),
        )
    else:
        new_balance = int(user_row[1]) + amount
        cur.execute(
            "UPDATE user SET money = ? WHERE CAST(id AS TEXT) == ?;",
            (new_balance, user_id),
        )

    cur.execute(
        "INSERT INTO chargelog VALUES(?, ?, ?, ?, ?, ?);",
        (
            uuid.uuid4().hex,
            "계좌이체",
            user_id,
            amount,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(req[2]),
        ),
    )
    image_hash = ""
    ocr_fingerprint = ""
    if len(req) > 9:
        image_hash = str(req[9] or "").strip()
    if len(req) > 10:
        ocr_fingerprint = str(req[10] or "").strip()
    cur.execute(
        "INSERT INTO receipt_guard VALUES(?, ?, ?, ?, ?);",
        (
            image_hash,
            ocr_fingerprint,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
            amount,
        ),
    )
    cur.execute("DELETE FROM chargereq WHERE rowid == ?;", (int(req[0]),))
    return True, "ok"


def _process_auto_approve_for_request(server_id, req_rowid):
    try:
        con = connect_server_db(server_id)
        if con is None:
            return
        cur = con.cursor()
        _begin_write(con)
        shop = get_shop_info(cur)
        if str(shop[10]) != "1":
            con.close()
            return

        cur.execute(
            "SELECT rowid, created_at, nickname, id, depositor, amount, image_url, auto_checked, auto_result, image_hash, ocr_fingerprint FROM chargereq WHERE rowid = ?;",
            (int(req_rowid),),
        )
        req_row = cur.fetchone()
        if req_row is None:
            con.close()
            return

        image_url = str(req_row[6] or "").strip()
        if not image_url:
            cur.execute(
                "UPDATE chargereq SET auto_checked = 1, auto_result = ? WHERE rowid = ?;",
                ("image_required", int(req_rowid)),
            )
            con.commit()
            con.close()
            return

        ocr_text, ocr_err = _run_receipt_ocr(image_url)
        if ocr_err is not None:
            cur.execute(
                "UPDATE chargereq SET auto_checked = 1, auto_result = ? WHERE rowid = ?;",
                (ocr_err, int(req_rowid)),
            )
            con.commit()
            con.close()
            return

        bank_account = shop[7] if len(shop) > 7 else ""
        ok_auto, reason = _evaluate_auto_approve(ocr_text, bank_account)
        if ok_auto:
            image_hash = str(req_row[9] or "").strip()
            if not image_hash:
                image_hash = _compute_image_hash(image_url)
            ocr_fingerprint = _build_ocr_fingerprint(ocr_text, req_row[4], req_row[5], bank_account)
            cur.execute(
                "UPDATE chargereq SET image_hash = ?, ocr_fingerprint = ? WHERE rowid = ?;",
                (image_hash, ocr_fingerprint, int(req_rowid)),
            )
            if _is_duplicate_receipt(cur, image_hash, ocr_fingerprint):
                cur.execute(
                    "UPDATE chargereq SET auto_checked = 1, auto_result = ? WHERE rowid = ?;",
                    ("duplicate_receipt_detected", int(req_rowid)),
                )
                con.commit()
                con.close()
                return
            cur.execute(
                "SELECT rowid, created_at, nickname, id, depositor, amount, image_url, auto_checked, auto_result, image_hash, ocr_fingerprint FROM chargereq WHERE rowid = ?;",
                (int(req_rowid),),
            )
            req_row = cur.fetchone()
            ok_apply, apply_reason = _approve_charge_request_row(cur, req_row)
            if not ok_apply:
                cur.execute(
                    "UPDATE chargereq SET auto_checked = 1, auto_result = ? WHERE rowid = ?;",
                    (apply_reason, int(req_rowid)),
                )
        else:
            cur.execute(
                "UPDATE chargereq SET auto_checked = 1, auto_result = ? WHERE rowid = ?;",
                (reason, int(req_rowid)),
            )

        con.commit()
        con.close()
    except Exception:
        # Avoid breaking request flow on background OCR failures.
        return


def _auto_approve_worker_loop():
    while True:
        got_item = False
        try:
            server_id, req_rowid = _auto_approve_queue.get()
            got_item = True
            _process_auto_approve_for_request(server_id, req_rowid)
        except Exception:
            pass
        finally:
            if got_item:
                _auto_approve_queue.task_done()


def _start_auto_approve_worker():
    global _auto_approve_worker_started
    if _auto_approve_worker_started:
        return
    with _auto_approve_worker_lock:
        if _auto_approve_worker_started:
            return
        threading.Thread(target=_auto_approve_worker_loop, daemon=True).start()
        _auto_approve_worker_started = True


def enforce_shop_private_if_expired(con, server_info):
    if server_info is None:
        return
    if licensing.is_expired(server_info[3]):
        cur = con.cursor()
        cur.execute("UPDATE shop SET is_public = 0;")
        con.commit()

def getip():
    return request.headers.get("CF-Connecting-IP", request.remote_addr)


def _begin_write(con):
    con.execute("BEGIN IMMEDIATE;")


def _json_safe(value):
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return "{}"


def _audit_log(cur, action, target="", before=None, after=None):
    admin_id = str(session.get("id", ""))
    if not admin_id:
        return
    cur.execute(
        "INSERT INTO admin_audit_log VALUES(?, ?, ?, ?, ?, ?, ?, ?);",
        (
            uuid.uuid4().hex,
            admin_id,
            str(action or ""),
            str(target or ""),
            _json_safe(before if before is not None else {}),
            _json_safe(after if after is not None else {}),
            str(getip() or ""),
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

@app.route("/discord")
def discord():
    return redirect("https://discord.gg/")

@app.route("/", methods=["GET"])
def index():
    if ("id" in session):
        return redirect(url_for("setting"))
    else:
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if (request.method == "GET"):
        if ("id" in session):
            return redirect(url_for("setting"))
        else:
            return render_template("login.html")
    else:
        if ("id" in request.form and "pw" in request.form):
            db_path = get_server_db_path(request.form["id"])
            if (request.form["id"].isdigit() and db_path and os.path.isfile(db_path)):
                con = sqlite3.connect(db_path)
                cur = con.cursor()
                cur.execute("SELECT * FROM info")
                serverinfo = cur.fetchone()
                if (request.form["pw"] == serverinfo[1]):
                    session.clear()
                    session["id"] = request.form["id"]
                    try:
                        cur.execute("SELECT * FROM webhook")
                        webhook = cur.fetchone()
                        webhook = DiscordWebhook(username='Venex System',
                                                 avatar_url='',
                                                 url=webhook[1])
                        eb = DiscordEmbed(title='?�패??로그???�림', description=f'[?�패?�로 ?�동?�기](http://127.0.0.1/)',
                                          color='#1454ff')
                        eb.add_embed_field(name='Server ID', value=session["id"], inline=False)
                        eb.add_embed_field(name='로그???�짜', value=f"{licensing.nowstr()}", inline=False)
                        eb.add_embed_field(name='?�속 IP', value=f"||{getip()}||", inline=False)
                        webhook.add_embed(eb)
                        webhook.execute()
                    except:
                        pass
                    return "Ok"
                else:
                    return "비�?번호가 ?�?�습?�다."
            else:
                return "?�이?��? ?�?�습?�다."
        else:
            return "?�이?��? ?�?�습?�다."

@app.route("/setting", methods=["GET", "POST"])
def setting():
    if (request.method == "GET"):
        if ("id" in session):
            con = connect_server_db()
            if con is None:
                session.clear()
                return redirect(url_for("login"))
            cur = con.cursor()
            cur.execute("SELECT * FROM info")
            serverinfo = cur.fetchone()
            license_expired = licensing.is_expired(serverinfo[3])
            if license_expired:
                enforce_shop_private_if_expired(con, serverinfo)
            cur.execute("SELECT * FROM webhook")
            webhook = cur.fetchone()
            shop = get_shop_info(cur)
            kpi = compute_admin_kpi(cur)
            con.close()
            return render_template(
                "manage.html",
                info=serverinfo,
                webhook=webhook,
                shop=shop,
                shop_url=f"/{serverinfo[0]}",
                license_expired=license_expired,
                kpi=kpi,
            )
        else:
            return redirect(url_for("login"))
    else:
        if ("id" in session):
            if session["id"] == "495888018058510357":
                return "??�せ???묎렐??�땲??"
            if False and request.form.get("buyusernamehide") not in ("0", "1"):
                return "0 ?�?�� 1??�줈�???�젰??�＜?몄슂."
            if False and (not request.form.get("roleid", "").isdigit()):
                return "??�??꾩씠?붾뒗 ??�옄濡쒕�???�젰??�＜?몄슂."
            if False and request.form.get("webhookprofile", "") == "":
                return "?뱁썒 ?꾨줈?꾩쓣 ?곸뼱二쇱�??"
            if request.form.get("shop_public", "0") not in ("0", "1"):
                return "?�듦�??????0 ?�?�� 1�???�젰??�＜?몄슂."

            con = connect_server_db()
            if con is None:
                return "??�쾭 ?곗씠?곕쿋??�뒪??李얠??????�뒿??�떎."
            cur = con.cursor()
            _begin_write(con)
            cur.execute("SELECT * FROM info")
            server_info = cur.fetchone()
            license_expired = licensing.is_expired(server_info[3])
            if license_expired:
                enforce_shop_private_if_expired(con, server_info)
            current_shop = get_shop_info(cur)
            requested_public = request.form.get("shop_public", "0")
            if requested_public not in ("0", "1"):
                requested_public = "0"
            if license_expired:
                requested_public = "0"
            shop_logo_url = request.form.get("shop_logo_url", "").strip()
            uploaded_logo_url, logo_error = _save_uploaded_shop_image(request.files.get("shop_logo_file"))
            if logo_error is not None:
                con.close()
                return logo_error
            if uploaded_logo_url:
                shop_logo_url = uploaded_logo_url
            if not shop_logo_url:
                shop_logo_url = current_shop[3]
            before_info = {
                "shop_name": current_shop[0],
                "shop_public": current_shop[6],
                "bank_account": current_shop[7],
                "bank_owner": current_shop[8],
                "bank_name": current_shop[9],
                "logo_url": current_shop[3],
            }
            cur.execute(
                "UPDATE info SET pw = ?, toss = ?;",
                (
                    request.form.get("webpanelpw", ""),
                    request.form.get("bankname", ""),
                ),
            )
            cur.execute(
                "UPDATE shop SET name = ?, slug = ?, description = ?, logo_url = ?, banner_url = ?, theme_color = ?, is_public = ?, bank_account = ?, bank_owner = ?, bank_name = ?;",
                (
                    request.form.get("shop_name", current_shop[0]).strip() or current_shop[0],
                    str(session["id"]),
                    current_shop[2],
                    shop_logo_url,
                    current_shop[4],
                    current_shop[5],
                    requested_public,
                    request.form.get("bankname", "").strip(),
                    request.form.get("bankowner", "").strip(),
                    request.form.get("bankbank", "").strip(),
                ),
            )
            after_info = {
                "shop_name": request.form.get("shop_name", current_shop[0]).strip() or current_shop[0],
                "shop_public": requested_public,
                "bank_account": request.form.get("bankname", "").strip(),
                "bank_owner": request.form.get("bankowner", "").strip(),
                "bank_name": request.form.get("bankbank", "").strip(),
                "logo_url": shop_logo_url,
            }
            _audit_log(cur, "setting.update", f"shop:{session.get('id','')}", before_info, after_info)
            con.commit()
            con.close()
            return "ok"
            if (session["id"] != "495888018058510357"):
                if (request.form["buyusernamehide"] == "0" or request.form["buyusernamehide"] == "1"):
                        if (request.form["roleid"].isdigit()):
                                if request.form["webhookprofile"] != "":
                                        if True:
                                            return "??주소???�어, ?�자, -, _ �??�용?????�습?�다."
                                            return "?��? ?�용 중인 ??주소?�니??"
                                        if request.form.get("shop_public", "0") not in ("0", "1"):
                                            return "공개 ?��???0 ?�는 1�??�력?�주?�요."
                                        con = connect_server_db()
                                        if con is None:
                                            return "?�버 ?�이?�베?�스�?찾을 ???�습?�다."
                                        cur = con.cursor()
                                        current_shop = get_shop_info(cur)
                                        cur.execute(
                                            "UPDATE info SET pw = ?, buyer = ?, toss = ?, hide = ?;",
                                            (request.form["webpanelpw"], request.form["roleid"],
                                                request.form['bankname'], request.form["buyusernamehide"],))
                                        con.commit()
                                        cur.execute(
                                            "UPDATE webhook SET buylog = ?, chargelog = ?, profile = ?;", (
                                                request.form.get("buylogwebhk", ""),
                                                request.form.get("logwebhk", ""),
                                                request.form["webhookprofile"]
                                            )
                                        )
                                        cur.execute(
                                            "UPDATE shop SET name = ?, slug = ?, description = ?, logo_url = ?, banner_url = ?, theme_color = ?, is_public = ?;",
                                            (
                                                current_shop[0],
                                                str(session["id"]),
                                                current_shop[2],
                                                current_shop[3],
                                                current_shop[4],
                                                current_shop[5],
                                                request.form.get("shop_public", "0"),
                                            )
                                        )
                                        con.commit()
                                        con.close()
                                        return "ok"
                                else:
                                    return "?�훅 ?�로?�을 ?�어주세??"
                        else:
                            return "??�� ?�이?�는 ?�자로만 ?�력?�주?�요."
                else:
                    return "0 ?�는 1?�로�??�력?�주?�요."
            else:
                return "?�못???�근?�니??"
        else:
            return "로그?�이 ?�제?�었?�니?? ?�시 로그?�해주세??"

@app.route("/manage_user", methods=["GET"])
def manage_user():
    if ("id" in session):
        con = connect_server_db()
        if con is None:
            session.clear()
            return redirect(url_for("login"))
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shop_member';")
        if cur.fetchone() is not None:
            cur.execute("""
                SELECT
                    sm.id,
                    sm.password,
                    COALESCE(u.money, 0) AS money,
                    COALESCE(u.warnings, 0) AS warnings,
                    COALESCE(u.ban, 0) AS ban
                FROM shop_member sm
                LEFT JOIN user u ON CAST(u.id AS TEXT) = sm.id
                ORDER BY sm.created_at DESC, sm.id ASC;
            """)
            users = cur.fetchall()
        else:
            cur.execute("SELECT CAST(id AS TEXT), '', money, warnings, ban FROM user")
            users = cur.fetchall()
        con.close()
        return render_template("manage_user.html", users=users)
    else:
        return redirect(url_for("login"))

@app.route("/manage_user_detail", methods=["GET", "POST"])
def manageuser_detail():
    if (request.method == "GET"):
        if ("id" in session):
            user_id = request.args.get("id", "")
            if (user_id != ""):
                con = connect_server_db()
                if con is None:
                    session.clear()
                    return redirect(url_for("login"))
                cur = con.cursor()
                cur.execute("SELECT password FROM shop_member WHERE id == ?;", (user_id,))
                member = cur.fetchone()
                if member is None:
                    con.close()
                    abort(404)
                cur.execute("SELECT money, warnings, ban FROM user WHERE CAST(id AS TEXT) == ?;", (user_id,))
                user_row = cur.fetchone()
                con.close()
                if user_row is None:
                    user_info = (user_id, member[0], 0, 0, 0)
                else:
                    user_info = (user_id, member[0], user_row[0], user_row[1], user_row[2])
                if (user_info != None):
                    return render_template("manage_user_detail.html", info=user_info)
                else:
                    abort(404)
            else:
                abort(404)
        else:
            return redirect(url_for("login"))
    else:
        if ("id" in session):
            if ("money" in request.form and "id" in request.form and "password" in request.form):
                if (request.form["money"].isdigit()):
                        if (request.form["warnings"].isdigit()):
                                if request.form.get("ban") not in ("0", "1"):
                                    return "차단 ?��???0 ?�는 1�??�력?�주?�요."
                                con = connect_server_db()
                                if con is None:
                                    return "?�버 ?�이?�베?�스�?찾을 ???�습?�다."
                                cur = con.cursor()
                                _begin_write(con)
                                cur.execute("SELECT password FROM shop_member WHERE id = ?;", (request.form["id"],))
                                before_member = cur.fetchone()
                                cur.execute("SELECT money, warnings, ban FROM user WHERE CAST(id AS TEXT) == ?;", (request.form["id"],))
                                before_user = cur.fetchone()
                                cur.execute("UPDATE shop_member SET password = ? WHERE id = ?;", (request.form["password"], request.form["id"]))
                                cur.execute("SELECT id FROM user WHERE CAST(id AS TEXT) == ?;", (request.form["id"],))
                                existing = cur.fetchone()
                                if existing is None:
                                    cur.execute(
                                        "INSERT INTO user (id, money, warnings, ban) VALUES (?, ?, ?, ?);",
                                        (request.form["id"], request.form["money"], request.form["warnings"], request.form["ban"])
                                    )
                                else:
                                    cur.execute(
                                        "UPDATE user SET money = ?, warnings = ?, ban = ? WHERE CAST(id AS TEXT) == ?;",
                                        (request.form["money"], request.form["warnings"], request.form["ban"], request.form["id"])
                                    )
                                _audit_log(
                                    cur,
                                    "user.update",
                                    f"user:{request.form['id']}",
                                    {
                                        "password": before_member[0] if before_member else "",
                                        "money": before_user[0] if before_user else 0,
                                        "warnings": before_user[1] if before_user else 0,
                                        "ban": before_user[2] if before_user else 0,
                                    },
                                    {
                                        "password": request.form["password"],
                                        "money": request.form["money"],
                                        "warnings": request.form["warnings"],
                                        "ban": request.form["ban"],
                                    },
                                )
                                con.commit()
                                con.close()
                                return "ok"
                        else:
                            return "문화?�품�?충전 경고 ?�는 ?�수로만 ?�어주세??"
                else:
                    return "?�액?� ?�수로만 ?�어주세??"
            else:
                return "?�못???�근?�니??"
        else:
            return "로그?�이 ?�제?�었?�니?? ?�시 로그?�해주세??"

@app.route("/createprod", methods=["GET", "POST"])
def createprod():
    if (request.method == "GET"):
        if ("id" in session):
            return render_template("create_prod.html")
        else:
            return redirect(url_for("login"))
    else:
        if ("id" in session):
            if ("price" in request.form and "name" in request.form):
                if (request.form["price"].isdigit()):
                    con = connect_server_db()
                    if con is None:
                        return "?�버 ?�이?�베?�스�?찾을 ???�습?�다."
                    cur = con.cursor()
                    _begin_write(con)
                    cur.execute("SELECT * FROM product WHERE name == ?;", (request.form["name"],))
                    prod = cur.fetchone()
                    if (prod == None):
                        image_url = request.form.get("image_url", "").strip()
                        uploaded_url, upload_error = _save_uploaded_product_image(request.files.get("image_file"))
                        if upload_error is not None:
                            con.close()
                            return upload_error
                        if uploaded_url:
                            image_url = uploaded_url
                        cur.execute("INSERT INTO product VALUES(?, ?, ?, ?, ?);",
                                    (
                                        request.form["name"],
                                        request.form["price"],
                                        "",
                                        request.form.get("description", ""),
                                        image_url
                                    ))
                        _audit_log(
                            cur,
                            "product.create",
                            f"product:{request.form['name']}",
                            {},
                            {
                                "name": request.form["name"],
                                "price": request.form["price"],
                                "stock": "",
                            },
                        )
                        con.commit()
                        con.close()
                        return "ok"
                    else:
                        return "?��? 존재?�는 ?�품명입?�다."
                else:
                    return "가격�? ?�자로만 ?�어주세??"
            else:
                return "?�못???�근?�니??"
        else:
            return "로그?�이 ?�제?�었?�니?? ?�시 로그?�해주세??"

@app.route("/manage_product", methods=["GET", "POST"])
def manage_product():
    if ("id" not in session):
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        if not name or not price or not price.isdigit():
            return "제품명/가격을 확인해주세요."

        con = connect_server_db()
        if con is None:
            return "서버 데이터베이스를 찾을 수 없습니다."
        cur = con.cursor()
        _begin_write(con)
        cur.execute("SELECT 1 FROM product WHERE name == ?;", (name,))
        if cur.fetchone() is not None:
            con.close()
            return "이미 존재하는 제품명입니다."

        image_url = request.form.get("image_url", "").strip()
        uploaded_url, upload_error = _save_uploaded_product_image(request.files.get("image_file"))
        if upload_error is not None:
            con.close()
            return upload_error
        if uploaded_url:
            image_url = uploaded_url

        cur.execute(
            "INSERT INTO product VALUES(?, ?, ?, ?, ?);",
            (
                name,
                int(price),
                request.form.get("stock", ""),
                request.form.get("description", ""),
                image_url,
            ),
        )
        _audit_log(
            cur,
            "product.create",
            f"product:{name}",
            {},
            {"name": name, "price": int(price), "stock": request.form.get("stock", "")},
        )
        con.commit()
        con.close()
        return "ok"

    con = connect_server_db()
    if con is None:
        session.clear()
        return redirect(url_for("login"))
    cur = con.cursor()
    cur.execute("SELECT * FROM product")
    products = cur.fetchall()
    con.close()
    return render_template("manage_prod.html", products=products)

@app.route("/delete_product", methods=["POST"])
def deleteprod():
    if ("id" in session):
        if ("name" in request.form):
            con = connect_server_db()
            if con is None:
                return "fail"
            cur = con.cursor()
            _begin_write(con)
            cur.execute("SELECT name, money, stock FROM product WHERE name == ?;", (request.form["name"],))
            before_prod = cur.fetchone()
            cur.execute("DELETE FROM product WHERE name == ?;", (request.form["name"],))
            _audit_log(
                cur,
                "product.delete",
                f"product:{request.form['name']}",
                {
                    "name": before_prod[0] if before_prod else request.form["name"],
                    "price": before_prod[1] if before_prod else "",
                },
                {},
            )
            con.commit()
            con.close()
            return "ok"
        else:
            return "fail"
    else:
        return "fail"

@app.route("/manage_product_detail", methods=["GET", "POST"])
def manage_product_detail():
    if (request.method == "GET"):
        if ("id" in session):
            product_name = request.args.get("id", "")
            if (product_name != ""):
                con = connect_server_db()
                if con is None:
                    session.clear()
                    return redirect(url_for("login"))
                cur = con.cursor()
                cur.execute("SELECT * FROM product WHERE name == ?;", (product_name,))
                prod_info = cur.fetchone()
                con.close()
                if (prod_info != None):
                    return render_template("manage_prod_detail.html", info=prod_info)
                else:
                    abort(404)
            else:
                abort(404)
        else:
            return redirect(url_for("login"))
    else:
        if ("id" in session):
            if ("price" in request.form and "stock" in request.form and "name" in request.form and "product_name" in request.form):
                if (request.form["price"].isdigit()):
                    con = connect_server_db()
                    if con is None:
                        return "?�버 ?�이?�베?�스�?찾을 ???�습?�다."
                    cur = con.cursor()
                    _begin_write(con)
                    cur.execute("SELECT name, money, stock, description, image_url FROM product WHERE name == ?;", (request.form["name"],))
                    before_product = cur.fetchone()
                    cur.execute("SELECT * FROM product WHERE name == ?;", (request.form["product_name"],))
                    renamed_product = cur.fetchone()
                    if renamed_product is None:
                        cur.execute("UPDATE product SET name = ? WHERE name == ?;", (
                            request.form["product_name"], request.form["name"]))
                        con.commit()
                        target_name = request.form["product_name"]
                    else:
                        if request.form["product_name"] != request.form["name"]:
                            con.close()
                            return "?��? 존재?�는 ?�품명입?�다."
                        target_name = request.form["name"]

                    image_url = request.form.get("image_url", "").strip()
                    uploaded_url, upload_error = _save_uploaded_product_image(request.files.get("image_file"))
                    if upload_error is not None:
                        con.close()
                        return upload_error
                    if uploaded_url:
                        image_url = uploaded_url

                    cur.execute("UPDATE product SET money = ?, stock = ?, description = ?, image_url = ? WHERE name == ?;", (
                        request.form["price"],
                        request.form["stock"],
                        request.form.get("description", ""),
                        image_url,
                        target_name
                    ))
                    _audit_log(
                        cur,
                        "product.update",
                        f"product:{target_name}",
                        {
                            "name": before_product[0] if before_product else request.form["name"],
                            "price": before_product[1] if before_product else "",
                            "stock": before_product[2] if before_product else "",
                        },
                        {
                            "name": target_name,
                            "price": request.form["price"],
                            "stock": request.form["stock"],
                        },
                    )
                    con.commit()
                    con.close()
                    return "ok"
                else:
                    return "가격�? ?�자로만 ?�어주세??"
            else:
                return "?�못???�근?�니??"
        else:
            return "로그?�이 ?�제?�었?�니?? ?�시 로그?�해주세??"


@app.route("/user_result", methods=["POST"])
def user_result():
    if "id" not in session:
        return jsonify({"result": "no", "text": "로그?�이 ?�요?�니??"})
    user_id = request.form.get("user_id", "")
    if False:
        return jsonify({"result": "no", "text": "?��? ID???�자로만 ?�력?�주?�요."})
    con = connect_server_db()
    if con is None:
        return jsonify({"result": "no", "text": "?�버 ?�이?�베?�스�?찾을 ???�습?�다."})
    cur = con.cursor()
    cur.execute("SELECT id FROM shop_member WHERE id == ?;", (user_id,))
    user_info = cur.fetchone()
    if user_info is None:
        cur.execute("SELECT id FROM user WHERE CAST(id AS TEXT) == ?;", (user_id,))
        user_info = cur.fetchone()
    con.close()
    if user_info is None:
        return jsonify({"result": "no", "text": "존재?��? ?�는 ?��??�니??"})
    return jsonify({"result": "ok"})


@app.route("/buy_log", methods=["GET"])
def buy_log():
    if "id" not in session:
        return redirect(url_for("login"))
    con = connect_server_db()
    if con is None:
        session.clear()
        return redirect(url_for("login"))
    cur = con.cursor()
    logs = fetch_rows_if_table_exists(cur, "buylog", "SELECT * FROM buylog ORDER BY rowid DESC;")
    con.close()
    return render_template("buy_log.html", logs=logs)


@app.route("/charge_log", methods=["GET"])
def charge_log():
    if "id" not in session:
        return redirect(url_for("login"))
    con = connect_server_db()
    if con is None:
        session.clear()
        return redirect(url_for("login"))
    cur = con.cursor()
    logs = fetch_rows_if_table_exists(cur, "chargelog", "SELECT * FROM chargelog ORDER BY rowid DESC;")
    con.close()
    return render_template("charge_log.html", logs=logs)


@app.route("/audit_log", methods=["GET"])
def audit_log():
    if "id" not in session:
        return redirect(url_for("login"))
    con = connect_server_db()
    if con is None:
        session.clear()
        return redirect(url_for("login"))
    cur = con.cursor()
    logs = fetch_rows_if_table_exists(
        cur,
        "admin_audit_log",
        "SELECT id, admin_id, action, target, before_json, after_json, ip, created_at FROM admin_audit_log ORDER BY created_at DESC;",
    )
    con.close()
    return render_template("admin_audit_log.html", logs=logs)


@app.route("/managereq_legacy", methods=["GET", "POST"])
def managereq():
    if "id" not in session:
        return redirect(url_for("login"))
    con = connect_server_db()
    if con is None:
        session.clear()
        return redirect(url_for("login"))
    cur = con.cursor()
    if request.method == "GET":
        reqs = fetch_rows_if_table_exists(cur, "chargereq", "SELECT * FROM chargereq ORDER BY rowid DESC;")
        con.close()
        return render_template("admin_managereq.html", reqs=reqs)

    payload = request.get_json(silent=True) or {}
    request_type = payload.get("type")
    user_id = str(payload.get("id", ""))
    if not user_id.isdigit():
        con.close()
        return "?�효?��? ?��? ?�청?�니??"
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'chargereq';")
    if cur.fetchone() is None:
        con.close()
        return "충전 ?�청 ?�이블이 ?�습?�다."
    if request_type == "delete":
        cur.execute("DELETE FROM chargereq WHERE id == ?;", (user_id,))
        con.commit()
        con.close()
        return "ok"
    if request_type == "accept":
        cur.execute("SELECT * FROM chargereq WHERE id == ?;", (user_id,))
        req = cur.fetchone()
        if req is None:
            con.close()
            return "충전 ?�청??찾을 ???�습?�다."
        try:
            amount = int(req[4])
        except (TypeError, ValueError, IndexError):
            con.close()
            return "충전 금액???�바르�? ?�습?�다."
        cur.execute("SELECT * FROM user WHERE id == ?;", (user_id,))
        user_row = cur.fetchone()
        if user_row is None:
            con.close()
            return "?��?�?찾을 ???�습?�다."
        new_balance = int(user_row[1]) + amount
        cur.execute("UPDATE user SET money = ? WHERE id == ?;", (new_balance, user_id))
        cur.execute("DELETE FROM chargereq WHERE id == ?;", (user_id,))
        con.commit()
        con.close()
        return "ok"
    con.close()
    return "?�효?��? ?��? ?�청?�니??"

@app.route("/managereq_old", methods=["GET", "POST"])
def managereq_v2():
    if "id" not in session:
        return redirect(url_for("login"))
    con = connect_server_db()
    if con is None:
        session.clear()
        return redirect(url_for("login"))
    cur = con.cursor()

    if request.method == "GET":
        reqs = fetch_rows_if_table_exists(
            cur,
            "chargereq",
            "SELECT rowid, created_at, nickname, id, depositor, amount, image_url FROM chargereq ORDER BY rowid DESC;",
        )
        con.close()
        return render_template("admin_managereq.html", reqs=reqs)

    payload = request.get_json(silent=True) or {}
    request_type = payload.get("type")
    req_id = str(payload.get("req_id", "")).strip()
    if not req_id.isdigit():
        con.close()
        return "유효하지 않은 요청입니다."

    if request_type == "delete":
        cur.execute("DELETE FROM chargereq WHERE rowid == ?;", (int(req_id),))
        con.commit()
        con.close()
        return "ok"

    if request_type == "accept":
        cur.execute(
            "SELECT rowid, created_at, nickname, id, depositor, amount, image_url FROM chargereq WHERE rowid == ?;",
            (int(req_id),),
        )
        req = cur.fetchone()
        if req is None:
            con.close()
            return "충전 신청을 찾을 수 없습니다."

        try:
            amount = int(req[5])
        except (TypeError, ValueError, IndexError):
            con.close()
            return "충전 금액이 올바르지 않습니다."

        user_id = str(req[3])
        cur.execute("SELECT * FROM user WHERE CAST(id AS TEXT) == ?;", (user_id,))
        user_row = cur.fetchone()
        if user_row is None:
            cur.execute(
                "INSERT INTO user (id, money, warnings, ban) VALUES (?, ?, 0, 0);",
                (user_id, amount),
            )
        else:
            new_balance = int(user_row[1]) + amount
            cur.execute(
                "UPDATE user SET money = ? WHERE CAST(id AS TEXT) == ?;",
                (new_balance, user_id),
            )

        cur.execute(
            "INSERT INTO chargelog VALUES(?, ?, ?, ?, ?, ?);",
            (
                uuid.uuid4().hex,
                "계좌이체",
                user_id,
                amount,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(req[2]),
            ),
        )
        cur.execute("DELETE FROM chargereq WHERE rowid == ?;", (int(req_id),))
        con.commit()
        con.close()
        return "ok"

    con.close()
    return "유효하지 않은 요청입니다."


@app.route("/managereq", methods=["GET", "POST"])
def managereq_v3():
    if "id" not in session:
        return redirect(url_for("login"))
    con = connect_server_db()
    if con is None:
        session.clear()
        return redirect(url_for("login"))
    cur = con.cursor()

    if request.method == "GET":
        shop = get_shop_info(cur)
        reqs = fetch_rows_if_table_exists(
            cur,
            "chargereq",
            "SELECT rowid, created_at, nickname, id, depositor, amount, image_url, auto_checked, auto_result, image_hash, ocr_fingerprint FROM chargereq ORDER BY rowid DESC;",
        )
        con.close()
        return render_template("admin_managereq.html", reqs=reqs, auto_approve=1 if str(shop[10]) == "1" else 0)

    payload = request.get_json(silent=True) or {}
    request_type = payload.get("type")

    if request_type == "toggle_auto":
        enabled = str(payload.get("enabled", "0"))
        if enabled not in ("0", "1"):
            con.close()
            return "invalid"
        _begin_write(con)
        cur.execute("SELECT auto_charge_approve FROM shop LIMIT 1;")
        before_row = cur.fetchone()
        cur.execute("UPDATE shop SET auto_charge_approve = ?;", (int(enabled),))
        _audit_log(
            cur,
            "charge.auto_toggle",
            f"shop:{session.get('id','')}",
            {"auto_charge_approve": int(before_row[0]) if before_row else 0},
            {"auto_charge_approve": int(enabled)},
        )
        con.commit()
        con.close()
        return "ok"

    req_id = str(payload.get("req_id", "")).strip()
    if not req_id.isdigit():
        con.close()
        return "invalid"

    if request_type == "delete":
        _begin_write(con)
        cur.execute(
            "SELECT rowid, id, amount, depositor, created_at FROM chargereq WHERE rowid == ?;",
            (int(req_id),),
        )
        before_req = cur.fetchone()
        cur.execute("DELETE FROM chargereq WHERE rowid == ?;", (int(req_id),))
        _audit_log(
            cur,
            "charge.request_delete",
            f"chargereq:{req_id}",
            {
                "id": before_req[1] if before_req else "",
                "amount": before_req[2] if before_req else "",
                "depositor": before_req[3] if before_req else "",
                "created_at": before_req[4] if before_req else "",
            },
            {},
        )
        con.commit()
        con.close()
        return "ok"

    if request_type == "accept":
        _begin_write(con)
        cur.execute(
            "SELECT rowid, created_at, nickname, id, depositor, amount, image_url, auto_checked, auto_result, image_hash, ocr_fingerprint FROM chargereq WHERE rowid == ?;",
            (int(req_id),),
        )
        req = cur.fetchone()
        if req is None:
            con.close()
            return "not_found"
        ok, reason = _approve_charge_request_row(cur, req)
        if not ok:
            con.rollback()
            con.close()
            return reason
        _audit_log(
            cur,
            "charge.request_accept",
            f"chargereq:{req_id}",
            {
                "id": req[3],
                "amount": req[5],
                "depositor": req[4],
                "created_at": req[1],
            },
            {"status": "approved"},
        )
        con.commit()
        con.close()
        return "ok"

    con.close()
    return "invalid"


@app.route("/license", methods=["GET", "POST"])
def managelicense():
    if (request.method == "GET"):
        if ("id" in session):
            con = connect_server_db()
            if con is None:
                session.clear()
                return redirect(url_for("login"))
            cur = con.cursor()
            cur.execute("SELECT * FROM info")
            serverinfo = cur.fetchone()
            enforce_shop_private_if_expired(con, serverinfo)
            con.close()
            if (licensing.is_expired(serverinfo[3])):
                return render_template("manage_license.html", expire="0??0?�간 (만료??")
            else:
                return render_template("manage_license.html", expire=licensing.get_remaining_string(serverinfo[3]))
        else:
            return redirect(url_for("login"))
    else:
        if ("id" in session):
            if ("code" in request.form):
                license_key = request.form["code"]
                con = sqlite3.connect("./db/" + "database.db")
                cur = con.cursor()
                cur.execute("SELECT * FROM license WHERE code == ?;", (license_key,))
                search_result = cur.fetchone()
                con.close()
                if (search_result != None):
                    if (search_result[2] == 0):
                        con = sqlite3.connect("./db/" + "database.db")
                        cur = con.cursor()
                        cur.execute("UPDATE license SET used = ? WHERE code == ?;", (1, license_key))
                        con.commit()
                        cur = con.cursor()
                        cur.execute("SELECT * FROM license WHERE code == ?;", (license_key,))
                        key_info = cur.fetchone()
                        con.close()
                        con = connect_server_db()
                        if con is None:
                            return "?�버 ?�이?�베?�스�?찾을 ???�습?�다."
                        cur = con.cursor()
                        cur.execute("SELECT * FROM info;")
                        server_info = cur.fetchone()
                        base_expire = server_info[3]
                        if licensing.is_expired(base_expire):
                            base_expire = licensing.make_new_expiringdate(0)
                        new_expiretime = licensing.add_time(base_expire, key_info[1])
                        cur.execute("UPDATE info SET expire = ?;", (new_expiretime,))
                        con.commit()
                        con.close()
                        return f"{key_info[1]}"
                    else:
                        return "?��? ?�용???�이?�스?�니??"
                else:
                    return "존재?��? ?�는 ?�이?�스?�니??"
            else:
                return "?�못???�근?�니??"
        else:
            return "로그?�이 ?�제?�었?�니?? ?�시 로그?�해주세??"

@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/<server_id>/auth/signup", methods=["POST"])
def public_shop_signup(server_id):
    if not str(server_id).isdigit():
        abort(404)
    con = connect_server_db(server_id)
    if con is None:
        abort(404)
    cur = con.cursor()
    cur.execute("SELECT * FROM info")
    server_info = cur.fetchone()
    enforce_shop_private_if_expired(con, server_info)
    shop = get_shop_info(cur)
    is_admin_preview = str(session.get("id", "")) == str(server_id)
    if str(shop[6]) != "1" and not is_admin_preview:
        con.close()
        abort(404)

    member_id = request.form.get("member_id", "").strip()
    member_pw = request.form.get("member_pw", "").strip()
    discord_id = request.form.get("discord_id", "").strip()
    gmail = request.form.get("gmail", "").strip()

    if not member_id or not member_pw or not discord_id or not gmail:
        con.close()
        return "모든 ??��???�력?�주?�요."

    cur.execute("SELECT id FROM shop_member WHERE id = ?;", (member_id,))
    if cur.fetchone() is not None:
        con.close()
        return "?��? ?�용 중인 ?�이?�입?�다."

    cur.execute(
        "INSERT INTO shop_member (id, password, discord_id, gmail, created_at, profile_image) VALUES(?, ?, ?, ?, ?, ?);",
        (member_id, member_pw, discord_id, gmail, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""),
    )
    cur.execute("SELECT id FROM user WHERE CAST(id AS TEXT) == ?;", (member_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO user (id, money, warnings, ban) VALUES (?, 0, 0, 0);", (member_id,))
    con.commit()
    con.close()
    session[f"shop_user_{server_id}"] = member_id
    return "ok"


@app.route("/<server_id>/auth/signin", methods=["POST"])
def public_shop_signin(server_id):
    if not str(server_id).isdigit():
        abort(404)
    con = connect_server_db(server_id)
    if con is None:
        abort(404)
    cur = con.cursor()
    cur.execute("SELECT * FROM info")
    server_info = cur.fetchone()
    enforce_shop_private_if_expired(con, server_info)
    shop = get_shop_info(cur)
    if str(shop[6]) != "1":
        con.close()
        abort(404)

    member_id = request.form.get("member_id", "").strip()
    member_pw = request.form.get("member_pw", "").strip()
    cur.execute("SELECT password FROM shop_member WHERE id = ?;", (member_id,))
    row = cur.fetchone()
    cur.execute("SELECT ban FROM user WHERE CAST(id AS TEXT) == ?;", (member_id,))
    ban_row = cur.fetchone()
    con.close()
    if row is None or row[0] != member_pw:
        return "?�이???�는 비�?번호가 ?�바르�? ?�습?�다."
    if ban_row is not None and str(ban_row[0]) == "1":
        return "\uc774 \uacc4\uc815\uc740 \ucc28\ub2e8\ub41c \uacc4\uc815\uc785\ub2c8\ub2e4."

    session[f"shop_user_{server_id}"] = member_id
    return "ok"


@app.route("/<server_id>/auth/logout", methods=["GET"])
def public_shop_logout(server_id):
    session.pop(f"shop_user_{server_id}", None)
    return redirect(url_for("public_shop_login_page", server_id=server_id))


def _load_public_shop(server_id):
    if not str(server_id).isdigit():
        return None, None, None
    con = connect_server_db(server_id)
    if con is None:
        return None, None, None
    cur = con.cursor()
    cur.execute("SELECT * FROM info")
    server_info = cur.fetchone()
    enforce_shop_private_if_expired(con, server_info)
    shop = get_shop_info(cur)
    is_admin_preview = str(session.get("id", "")) == str(server_id)
    if str(shop[6]) != "1" and not is_admin_preview:
        con.close()
        return None, None, None
    return con, server_info, shop


@app.route("/<server_id>/login", methods=["GET"])
def public_shop_login_page(server_id):
    con, server_info, shop = _load_public_shop(server_id)
    if con is None:
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    con.close()
    if logged_member:
        return redirect(url_for("public_shop", server_id=server_id))
    return render_template("shop_login.html", shop=shop, server_id=server_id)


@app.route("/<server_id>/signup", methods=["GET"])
def public_shop_signup_page(server_id):
    con, server_info, shop = _load_public_shop(server_id)
    if con is None:
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    con.close()
    if logged_member:
        return redirect(url_for("public_shop", server_id=server_id))
    return render_template("shop_signup.html", shop=shop, server_id=server_id)


@app.route("/<server_id>", methods=["GET"])
def public_shop(server_id):
    con, server_info, shop = _load_public_shop(server_id)
    if con is None:
        abort(404)

    logged_member = session.get(f"shop_user_{server_id}")
    if not logged_member:
        con.close()
        return redirect(url_for("public_shop_login_page", server_id=server_id))

    cur = con.cursor()
    cur.execute("SELECT ban FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
    ban_row = cur.fetchone()
    if ban_row is not None and str(ban_row[0]) == "1":
        session.pop(f"shop_user_{server_id}", None)
        con.close()
        return "\uc774 \uacc4\uc815\uc740 \ucc28\ub2e8\ub41c \uacc4\uc815\uc785\ub2c8\ub2e4."
    cur.execute("SELECT * FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
    user_row = cur.fetchone()
    member_balance = int(user_row[1]) if user_row is not None else 0

    cur.execute(
        "SELECT id, created_at, profile_image FROM shop_member WHERE id = ?;",
        (logged_member,),
    )
    member_info = cur.fetchone()

    cur.execute("SELECT * FROM product ORDER BY rowid DESC;")
    products = cur.fetchall()
    con.close()
    return render_template(
        "shop_public.html",
        shop=shop,
        products=products,
        server_id=server_id,
        logged_member=logged_member,
        member_balance=member_balance,
        member_info=member_info,
        server_info=server_info,
    )


@app.route("/<server_id>/settings", methods=["POST"])
def public_shop_settings(server_id):
    if not str(server_id).isdigit():
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    if not logged_member:
        return "로그인이 필요합니다."

    con = connect_server_db(server_id)
    if con is None:
        abort(404)
    cur = con.cursor()
    _begin_write(con)
    current_pw = request.form.get("current_pw", "").strip()
    new_pw = request.form.get("new_pw", "").strip()
    if current_pw == "" or new_pw == "":
        con.close()
        return "기존 비밀번호와 새 비밀번호를 모두 입력해주세요."

    cur.execute("SELECT password FROM shop_member WHERE id = ?;", (logged_member,))
    row = cur.fetchone()
    if row is None:
        con.close()
        return "회원 정보를 찾을 수 없습니다."
    if str(row[0]) != current_pw:
        con.close()
        return "기존 비밀번호가 일치하지 않습니다."

    cur.execute(
        "UPDATE shop_member SET password = ? WHERE id = ?;",
        (new_pw, logged_member),
    )
    con.commit()
    con.close()
    return "ok"


@app.route("/<server_id>/charge", methods=["GET", "POST"])
def public_shop_charge(server_id):
    con, server_info, shop = _load_public_shop(server_id)
    if con is None:
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    if not logged_member:
        con.close()
        return redirect(url_for("public_shop_login_page", server_id=server_id))

    cur = con.cursor()
    cur.execute("SELECT ban FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
    ban_row = cur.fetchone()
    if ban_row is not None and str(ban_row[0]) == "1":
        session.pop(f"shop_user_{server_id}", None)
        con.close()
        return "이 계정은 차단된 계정입니다."

    if request.method == "GET":
        cur.execute("SELECT money FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
        money_row = cur.fetchone()
        balance = int(money_row[0]) if money_row is not None else 0
        bank_account = shop[7] if shop and len(shop) > 7 else ""
        bank_owner = shop[8] if shop and len(shop) > 8 else ""
        bank_name = shop[9] if shop and len(shop) > 9 else ""
        con.close()
        return render_template(
            "shop_charge.html",
            shop=shop,
            server_id=server_id,
            logged_member=logged_member,
            member_balance=balance,
            bank_account=bank_account,
            bank_owner=bank_owner,
            bank_name=bank_name,
        )
    _begin_write(con)

    amount_text = request.form.get("amount", "").strip()
    depositor = request.form.get("depositor", "").strip()
    if not amount_text.isdigit() or int(amount_text) <= 0:
        con.close()
        return "충전 금액을 숫자로 입력해주세요."
    if depositor == "":
        con.close()
        return "입금자명을 입력해주세요."

    cur.execute("SELECT COUNT(*) FROM chargereq WHERE CAST(id AS TEXT) = ?;", (logged_member,))
    pending_count = int(cur.fetchone()[0] or 0)
    if pending_count >= 3:
        con.close()
        return "충전신청은 최대 3건까지 가능합니다. 기존 신청이 승인/처리된 후 다시 신청해주세요."

    image_url = request.form.get("image_url", "").strip()
    uploaded_url, upload_error = _save_uploaded_charge_image(request.files.get("receipt_file"))
    if upload_error is not None:
        con.close()
        return upload_error
    if uploaded_url:
        image_url = uploaded_url
    if not image_url:
        con.close()
        return "입금 이미지를 업로드하거나 이미지 URL을 입력해주세요."

    image_hash = _compute_image_hash(image_url)
    cur.execute(
        "INSERT INTO chargereq VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        (
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            logged_member,
            logged_member,
            depositor,
            int(amount_text),
            image_url,
            0,
            "",
            image_hash,
            "",
        ),
    )
    req_rowid = cur.lastrowid
    con.commit()
    con.close()

    # Respond immediately; OCR auto-approval runs asynchronously in a single worker.
    if str(shop[10]) == "1":
        _start_auto_approve_worker()
        _auto_approve_queue.put((server_id, int(req_rowid)))
    return "ok"


@app.route("/<server_id>/buy", methods=["POST"])
def public_shop_buy(server_id):
    if not str(server_id).isdigit():
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    if not logged_member:
        return jsonify({"result": "no", "text": "로그인이 필요합니다."})

    con = connect_server_db(server_id)
    if con is None:
        abort(404)
    cur = con.cursor()
    _begin_write(con)

    cur.execute("SELECT ban FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
    ban_row = cur.fetchone()
    if ban_row is not None and str(ban_row[0]) == "1":
        session.pop(f"shop_user_{server_id}", None)
        con.close()
        return jsonify({"result": "no", "text": "이 계정은 차단된 계정입니다."})

    product_name = request.form.get("product_name", "").strip()
    qty_text = request.form.get("qty", "1").strip()
    qty = int(qty_text) if qty_text.isdigit() else 1
    if qty <= 0:
        qty = 1

    cur.execute("SELECT name, money, stock FROM product WHERE name = ?;", (product_name,))
    product = cur.fetchone()
    if product is None:
        con.close()
        return jsonify({"result": "no", "text": "상품을 찾을 수 없습니다."})

    unit_price = int(product[1])
    total_price = unit_price * qty
    cur.execute("SELECT money FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
    user_row = cur.fetchone()
    if user_row is None:
        cur.execute("INSERT INTO user (id, money, warnings, ban) VALUES (?, 0, 0, 0);", (logged_member,))
        balance = 0
    else:
        balance = int(user_row[0])
    if balance < total_price:
        con.rollback()
        con.close()
        return jsonify({"result": "no", "text": "잔액이 부족합니다."})

    stock_lines = [line for line in str(product[2] or "").splitlines() if line.strip()]
    if len(stock_lines) < qty:
        con.close()
        return jsonify({"result": "no", "text": "재고가 부족합니다."})

    delivered = stock_lines[:qty]
    remaining_stock = "\n".join(stock_lines[qty:])
    cur.execute("UPDATE product SET stock = ? WHERE name = ?;", (remaining_stock, product_name))
    cur.execute("UPDATE user SET money = ? WHERE CAST(id AS TEXT) == ?;", (balance - total_price, logged_member))
    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO buylog VALUES(?, ?, ?, ?, ?, ?);",
        (
            uuid.uuid4().hex,
            product_name,
            logged_member,
            logged_member,
            qty,
            created_at,
        ),
    )

    order_code = None
    for _ in range(30):
        candidate = str(uuid.uuid4().int % 9000000 + 1000000)
        cur.execute("SELECT 1 FROM purchase_delivery WHERE order_code = ?;", (candidate,))
        if cur.fetchone() is None:
            order_code = candidate
            break
    if order_code is None:
        order_code = str(uuid.uuid4().int % 9000000 + 1000000)

    cur.execute(
        "INSERT INTO purchase_delivery VALUES(?, ?, ?, ?, ?, ?);",
        (
            order_code,
            logged_member,
            product_name,
            qty,
            "\n".join(delivered),
            created_at,
        ),
    )
    con.commit()
    con.close()
    return jsonify(
        {
            "result": "ok",
            "text": "구매가 완료되었습니다.",
            "redirect_url": f"/{server_id}/{order_code}",
        }
    )


@app.route("/<server_id>/charge-history", methods=["GET"])
def public_shop_charge_history(server_id):
    if not str(server_id).isdigit():
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    if not logged_member:
        return redirect(url_for("public_shop_login_page", server_id=server_id))

    con = connect_server_db(server_id)
    if con is None:
        abort(404)
    cur = con.cursor()
    cur.execute("SELECT ban FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
    ban_row = cur.fetchone()
    if ban_row is not None and str(ban_row[0]) == "1":
        session.pop(f"shop_user_{server_id}", None)
        con.close()
        return "이 계정은 차단된 계정입니다."

    cur.execute(
        "SELECT method, amount, created_at, nickname FROM chargelog WHERE CAST(id AS TEXT) == ? ORDER BY created_at DESC;",
        (logged_member,),
    )
    charge_logs = cur.fetchall()
    cur.execute("SELECT * FROM shop LIMIT 1;")
    shop = cur.fetchone()
    con.close()
    return render_template(
        "shop_charge_history.html",
        shop=shop,
        server_id=server_id,
        logged_member=logged_member,
        charge_logs=charge_logs,
    )


@app.route("/<server_id>/orders", methods=["GET"])
def public_shop_orders(server_id):
    if not str(server_id).isdigit():
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    if not logged_member:
        return redirect(url_for("public_shop_login_page", server_id=server_id))

    con = connect_server_db(server_id)
    if con is None:
        abort(404)
    cur = con.cursor()
    cur.execute("SELECT ban FROM user WHERE CAST(id AS TEXT) == ?;", (logged_member,))
    ban_row = cur.fetchone()
    if ban_row is not None and str(ban_row[0]) == "1":
        session.pop(f"shop_user_{server_id}", None)
        con.close()
        return "이 계정은 차단된 계정입니다."

    cur.execute(
        "SELECT order_code, product_name, quantity, created_at FROM purchase_delivery WHERE member_id = ? ORDER BY created_at DESC;",
        (logged_member,),
    )
    orders = cur.fetchall()
    cur.execute("SELECT * FROM shop LIMIT 1;")
    shop = cur.fetchone()
    con.close()
    return render_template(
        "shop_orders.html",
        shop=shop,
        server_id=server_id,
        logged_member=logged_member,
        orders=orders,
    )


@app.route("/<server_id>/<order_code>", methods=["GET"])
def public_shop_order_detail(server_id, order_code):
    if not str(server_id).isdigit():
        abort(404)
    if not str(order_code).isdigit() or len(str(order_code)) != 7:
        abort(404)
    logged_member = session.get(f"shop_user_{server_id}")
    if not logged_member:
        return redirect(url_for("public_shop_login_page", server_id=server_id))

    con = connect_server_db(server_id)
    if con is None:
        abort(404)
    cur = con.cursor()
    cur.execute(
        "SELECT order_code, member_id, product_name, quantity, items_text, created_at FROM purchase_delivery WHERE order_code = ?;",
        (order_code,),
    )
    order_row = cur.fetchone()
    cur.execute("SELECT * FROM shop LIMIT 1;")
    shop = cur.fetchone()
    con.close()
    if order_row is None:
        abort(404)
    if str(order_row[1]) != str(logged_member):
        abort(404)
    items = [line for line in str(order_row[4] or "").splitlines() if line.strip()]
    return render_template(
        "shop_order.html",
        shop=shop,
        server_id=server_id,
        logged_member=logged_member,
        order=order_row,
        items=items,
    )

@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=60)


@app.errorhandler(404)
def not_found_error(error):
    return render_template("404.html")

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "").lower() == "true",
        host=os.environ.get("VENEX_HOST", "0.0.0.0"),
        port=int(os.environ.get("VENEX_PORT", "5000")),
        use_reloader=False,
        threaded=True,
    )


