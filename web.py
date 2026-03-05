from flask import Flask, render_template, request, session, redirect, abort, url_for, jsonify
import sqlite3, json
import os
import uuid
import datetime
from datetime import timedelta
from werkzeug.utils import secure_filename
from util import funcs as fc, licensing
from discord_webhook import DiscordEmbed, DiscordWebhook

curdir = os.path.dirname(__file__) + "/"

app = Flask(__name__)
app.secret_key = os.environ.get("VENEX_SECRET_KEY", "venex-dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def _allowed_image_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _save_uploaded_product_image(file_storage):
    if file_storage is None or file_storage.filename == "":
        return None, None
    if not _allowed_image_file(file_storage.filename):
        return None, "이미지 파일 형식은 png, jpg, jpeg, webp, gif 만 가능합니다."

    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(curdir, "static", "uploads", "products")
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, new_name))
    return f"/static/uploads/products/{new_name}", None


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
                        is_public INTEGER
                    );
                    """)
        cur.execute(
            "INSERT INTO shop VALUES(?, ?, ?, ?, ?, ?, ?);",
            ("VENDIX SHOP", "", "", "", "", "#4f7cff", 0)
        )

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'shop_member';")
    if cur.fetchone() is None:
        cur.execute("""
                    CREATE TABLE shop_member (
                        id TEXT PRIMARY KEY,
                        password TEXT,
                        discord_id TEXT,
                        gmail TEXT,
                        created_at TEXT
                    );
                    """)

    cur.execute("PRAGMA table_info(product);")
    product_columns = {row[1] for row in cur.fetchall()}
    if "description" not in product_columns:
        cur.execute("ALTER TABLE product ADD COLUMN description TEXT DEFAULT '';")
    if "image_url" not in product_columns:
        cur.execute("ALTER TABLE product ADD COLUMN image_url TEXT DEFAULT '';")

    cur.execute("SELECT COUNT(*) FROM shop;")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO shop VALUES(?, ?, ?, ?, ?, ?, ?);",
            ("VENDIX SHOP", "", "", "", "", "#4f7cff", 0)
        )

    # Keep old schema but enforce initial visibility as private when value is missing.
    cur.execute("UPDATE shop SET is_public = 0 WHERE is_public IS NULL;")
    cur.execute("UPDATE shop SET is_public = 0 WHERE slug IS NULL OR slug = '';")
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
        return ("VENDIX SHOP", "", "", "", "", "#4f7cff", 0)
    return shop

def getip():
    return request.headers.get("CF-Connecting-IP", request.remote_addr)

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
                        eb = DiscordEmbed(title='웹패널 로그인 알림', description=f'[웹패널로 이동하기](http://127.0.0.1/)',
                                          color='#1454ff')
                        eb.add_embed_field(name='서버 아이디', value=session["id"], inline=False)
                        eb.add_embed_field(name='로그인 날짜', value=f"{licensing.nowstr()}", inline=False)
                        eb.add_embed_field(name='접속 IP', value=f"||{getip()}||", inline=False)
                        webhook.add_embed(eb)
                        webhook.execute()
                    except:
                        pass
                    return "Ok"
                else:
                    return "비밀번호가 틀렸습니다."
            else:
                return "아이디가 틀렸습니다."
        else:
            return "아이디가 틀렸습니다."

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
            cur.execute("SELECT * FROM webhook")
            webhook = cur.fetchone()
            shop = get_shop_info(cur)
            con.close()
            return render_template("manage.html", info=serverinfo, webhook=webhook, shop=shop, shop_url=f"/{serverinfo[0]}")
        else:
            return redirect(url_for("login"))
    else:
        if ("id" in session):
            if session["id"] == "495888018058510357":
                return "?섎せ???묎렐?낅땲??"
            if False and request.form.get("buyusernamehide") not in ("0", "1"):
                return "0 ?먮뒗 1?쇰줈留??낅젰?댁＜?몄슂."
            if False and (not request.form.get("roleid", "").isdigit()):
                return "??븷 ?꾩씠?붾뒗 ?レ옄濡쒕쭔 ?낅젰?댁＜?몄슂."
            if False and request.form.get("webhookprofile", "") == "":
                return "?뱁썒 ?꾨줈?꾩쓣 ?곸뼱二쇱꽭??"
            if request.form.get("shop_public", "0") not in ("0", "1"):
                return "怨듦컻 ?щ???0 ?먮뒗 1留??낅젰?댁＜?몄슂."

            con = connect_server_db()
            if con is None:
                return "?쒕쾭 ?곗씠?곕쿋?댁뒪瑜?李얠쓣 ???놁뒿?덈떎."
            cur = con.cursor()
            current_shop = get_shop_info(cur)
            cur.execute(
                "UPDATE info SET pw = ?, toss = ?;",
                (
                    request.form.get("webpanelpw", ""),
                    request.form.get("bankname", ""),
                ),
            )
            cur.execute(
                "UPDATE shop SET name = ?, slug = ?, description = ?, logo_url = ?, banner_url = ?, theme_color = ?, is_public = ?;",
                (
                    request.form.get("shop_name", current_shop[0]).strip() or current_shop[0],
                    str(session["id"]),
                    current_shop[2],
                    current_shop[3],
                    current_shop[4],
                    current_shop[5],
                    request.form.get("shop_public", "0"),
                ),
            )
            con.commit()
            con.close()
            return "ok"
            if (session["id"] != "495888018058510357"):
                if (request.form["buyusernamehide"] == "0" or request.form["buyusernamehide"] == "1"):
                        if (request.form["roleid"].isdigit()):
                                if request.form["webhookprofile"] != "":
                                        if True:
                                            return "샵 주소는 영어, 숫자, -, _ 만 사용할 수 있습니다."
                                            return "이미 사용 중인 샵 주소입니다."
                                        if request.form.get("shop_public", "0") not in ("0", "1"):
                                            return "공개 여부는 0 또는 1만 입력해주세요."
                                        con = connect_server_db()
                                        if con is None:
                                            return "서버 데이터베이스를 찾을 수 없습니다."
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
                                    return "웹훅 프로필을 적어주세요."
                        else:
                            return "역할 아이디는 숫자로만 입력해주세요."
                else:
                    return "0 또는 1으로만 입력해주세요."
            else:
                return "잘못된 접근입니다."
        else:
            return "로그인이 해제되었습니다. 다시 로그인해주세요."

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
                                    return "차단 여부는 0 또는 1만 입력해주세요."
                                con = connect_server_db()
                                if con is None:
                                    return "서버 데이터베이스를 찾을 수 없습니다."
                                cur = con.cursor()
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
                                con.commit()
                                con.close()
                                return "ok"
                        else:
                            return "문화상품권 충전 경고 수는 정수로만 적어주세요."
                else:
                    return "잔액은 정수로만 적어주세요."
            else:
                return "잘못된 접근입니다."
        else:
            return "로그인이 해제되었습니다. 다시 로그인해주세요."

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
                        return "서버 데이터베이스를 찾을 수 없습니다."
                    cur = con.cursor()
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
                        con.commit()
                        con.close()
                        return "ok"
                    else:
                        return "이미 존재하는 제품명입니다."
                else:
                    return "가격은 숫자로만 적어주세요."
            else:
                return "잘못된 접근입니다."
        else:
            return "로그인이 해제되었습니다. 다시 로그인해주세요."

@app.route("/manage_product", methods=["GET"])
def manage_product():
    if ("id" in session):
        con = connect_server_db()
        if con is None:
            session.clear()
            return redirect(url_for("login"))
        cur = con.cursor()
        cur.execute("SELECT * FROM product")
        products = cur.fetchall()
        con.close()
        return render_template("manage_prod.html", products=products)
    else:
        return redirect(url_for("login"))

@app.route("/delete_product", methods=["POST"])
def deleteprod():
    if ("id" in session):
        if ("name" in request.form):
            con = connect_server_db()
            if con is None:
                return "fail"
            cur = con.cursor()
            cur.execute("DELETE FROM product WHERE name == ?;", (request.form["name"],))
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
                        return "서버 데이터베이스를 찾을 수 없습니다."
                    cur = con.cursor()
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
                            return "이미 존재하는 제품명입니다."
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
                    con.commit()
                    con.close()
                    return "ok"
                else:
                    return "가격은 숫자로만 적어주세요."
            else:
                return "잘못된 접근입니다."
        else:
            return "로그인이 해제되었습니다. 다시 로그인해주세요."


@app.route("/user_result", methods=["POST"])
def user_result():
    if "id" not in session:
        return jsonify({"result": "no", "text": "로그인이 필요합니다."})
    user_id = request.form.get("user_id", "")
    if False:
        return jsonify({"result": "no", "text": "유저 ID는 숫자로만 입력해주세요."})
    con = connect_server_db()
    if con is None:
        return jsonify({"result": "no", "text": "서버 데이터베이스를 찾을 수 없습니다."})
    cur = con.cursor()
    cur.execute("SELECT id FROM shop_member WHERE id == ?;", (user_id,))
    user_info = cur.fetchone()
    if user_info is None:
        cur.execute("SELECT id FROM user WHERE CAST(id AS TEXT) == ?;", (user_id,))
        user_info = cur.fetchone()
    con.close()
    if user_info is None:
        return jsonify({"result": "no", "text": "존재하지 않는 유저입니다."})
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


@app.route("/managereq", methods=["GET", "POST"])
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
        return "유효하지 않은 요청입니다."
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'chargereq';")
    if cur.fetchone() is None:
        con.close()
        return "충전 신청 테이블이 없습니다."
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
            return "충전 신청을 찾을 수 없습니다."
        try:
            amount = int(req[4])
        except (TypeError, ValueError, IndexError):
            con.close()
            return "충전 금액이 올바르지 않습니다."
        cur.execute("SELECT * FROM user WHERE id == ?;", (user_id,))
        user_row = cur.fetchone()
        if user_row is None:
            con.close()
            return "유저를 찾을 수 없습니다."
        new_balance = int(user_row[1]) + amount
        cur.execute("UPDATE user SET money = ? WHERE id == ?;", (new_balance, user_id))
        cur.execute("DELETE FROM chargereq WHERE id == ?;", (user_id,))
        con.commit()
        con.close()
        return "ok"
    con.close()
    return "유효하지 않은 요청입니다."

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
            con.close()
            if (licensing.is_expired(serverinfo[3])):
                return render_template("manage_license.html", expire="0일 0시간 (만료됨)")
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
                            return "서버 데이터베이스를 찾을 수 없습니다."
                        cur = con.cursor()
                        cur.execute("SELECT * FROM info;")
                        server_info = cur.fetchone()
                        if (licensing.is_expired(server_info[3])):
                            new_expiretime = licensing.make_new_expiringdate(key_info[1])
                        else:
                            new_expiretime = licensing.add_time(server_info[3], key_info[1])
                        cur.execute("UPDATE info SET expire = ?;", (new_expiretime,))
                        con.commit()
                        con.close()
                        return f"{key_info[1]}"
                    else:
                        return "이미 사용된 라이센스입니다."
                else:
                    return "존재하지 않는 라이센스입니다."
            else:
                return "잘못된 접근입니다."
        else:
            return "로그인이 해제되었습니다. 다시 로그인해주세요."

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
        return "모든 항목을 입력해주세요."

    cur.execute("SELECT id FROM shop_member WHERE id = ?;", (member_id,))
    if cur.fetchone() is not None:
        con.close()
        return "이미 사용 중인 아이디입니다."

    cur.execute(
        "INSERT INTO shop_member VALUES(?, ?, ?, ?, ?);",
        (member_id, member_pw, discord_id, gmail, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
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
    shop = get_shop_info(cur)
    if str(shop[6]) != "1":
        con.close()
        abort(404)

    member_id = request.form.get("member_id", "").strip()
    member_pw = request.form.get("member_pw", "").strip()
    cur.execute("SELECT password FROM shop_member WHERE id = ?;", (member_id,))
    row = cur.fetchone()
    con.close()
    if row is None or row[0] != member_pw:
        return "아이디 또는 비밀번호가 올바르지 않습니다."

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
    cur.execute("SELECT * FROM product ORDER BY rowid DESC;")
    products = cur.fetchall()
    con.close()
    return render_template(
        "shop_public.html",
        shop=shop,
        products=products,
        server_id=server_id,
        logged_member=logged_member,
        server_info=server_info,
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
        host=os.environ.get("VENEX_HOST", "127.0.0.1"),
        port=int(os.environ.get("VENEX_PORT", "5000")),
    )
