# Venex Project Guide

## 1. Security fixes applied

- Replaced dynamic SQL in product and balance-related paths with parameterized queries.
- Made the Flask secret key configurable through `VENEX_SECRET_KEY` instead of generating a new one on each start.
- Fixed the settings form mismatch so `logwebhk` and `buylogwebhk` are stored separately.
- Added basic validation for user ban values in the web panel.
- Moved the Flask runner behind `if __name__ == "__main__":` and made host/port configurable with environment variables.

## 2. Route map

### Flask web panel routes

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | Redirects logged-in users to settings and others to login |
| GET, POST | `/login` | Server web panel login |
| GET, POST | `/setting` | Server settings and webhook configuration |
| GET | `/manage_user` | User list |
| GET, POST | `/manage_user_detail` | User detail update |
| POST | `/user_result` | AJAX user lookup for the search form |
| GET, POST | `/createprod` | Product creation |
| GET | `/manage_product` | Product list |
| POST | `/delete_product` | Product deletion |
| GET, POST | `/manage_product_detail` | Product detail update |
| GET | `/buy_log` | Purchase log page |
| GET | `/charge_log` | Charge log page |
| GET, POST | `/managereq` | Charge request list and approval/delete actions |
| GET, POST | `/license` | License status and extension |
| GET | `/logout` | Clears session |
| GET | `/discord` | Redirects to Discord invite |

### Discord bot commands

| Type | Command | Purpose |
| --- | --- | --- |
| Message command | `.등록 <license>` | Registers a guild and creates its DB |
| Message command | `.백업` | Sends the guild DB file to an admin |
| Slash command | `/가입` | Adds a user to the guild DB |
| Slash command | `/내정보` | Shows user balance, warnings, ban status |
| Slash command | `/계좌이체` | Starts Toss-based auto-charge flow |

## 3. Database schema

### Shared database: `db/database.db`

| Table | Columns | Notes |
| --- | --- | --- |
| `license` | `code`, `date`, `used` | Master license inventory |

### Per-guild database: `db/<guild_id>.db`

Created by `util/database.py:create`.

| Table | Columns | Notes |
| --- | --- | --- |
| `info` | `id`, `pw`, `buyer`, `expire`, `cultureid`, `culturepw`, `fee`, `toss`, `hide` | Core guild configuration |
| `product` | `name`, `money`, `stock` | Product catalog and stock text |
| `user` | `id`, `money`, `warnings`, `ban` | User wallet and moderation state |
| `webhook` | `buylog`, `chargelog`, `profile` | Webhook URLs/profile image |

### Optional tables referenced by templates

These are not created in the current bootstrap flow, but the panel now handles them safely if they exist.

| Table | Used by |
| --- | --- |
| `buylog` | `/buy_log` |
| `chargelog` | `/charge_log` |
| `chargereq` | `/managereq` |

## 4. Local setup

### Python packages

Install the libraries used directly in the repository:

```powershell
pip install flask nextcord discord-webhook requests
```

### Required configuration

Edit `config.py`:

```python
token = 'DISCORD BOT TOKEN'
GUILD_ID = 123456789
```

Recommended environment variables for the web panel:

```powershell
$env:VENEX_SECRET_KEY = "change-this-secret"
$env:VENEX_HOST = "127.0.0.1"
$env:VENEX_PORT = "5000"
```

### Running the services

Initialize licenses if needed:

```powershell
python admin_gen.py
```

Run the Discord bot:

```powershell
python app.py
```

Run the web panel:

```powershell
python web.py
```

Open `http://127.0.0.1:5000/login`.

### Toss integration note

`util/toss.py` still expects a local API service at:

- `http://127.0.0.1:443/api/toss/request`
- `http://127.0.0.1:443/api/toss/confirm`

The request token is blank in the repository, so this integration is still incomplete until you supply the real service and secret.

## 5. Refactor priority

### Priority 1

- Move secrets out of source files into environment variables or a dedicated config layer.
- Replace raw SQLite access scattered across routes with a small repository/service layer.
- Add CSRF protection to all state-changing web routes.

### Priority 2

- Normalize the per-guild schema and formally create optional tables like `buylog`, `chargelog`, and `chargereq`.
- Remove duplicated template markup and shared navbar code into base templates.
- Clean up broken or mojibake text and enforce UTF-8 consistently.

### Priority 3

- Split `web.py` into auth, product, user, billing, and license blueprints.
- Replace the Flask development server with a production WSGI server such as Waitress or Gunicorn.
- Add automated tests around login, product updates, license extension, and charge approval flows.
