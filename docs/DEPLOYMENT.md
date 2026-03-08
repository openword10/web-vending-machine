# VENDIX Deployment Guide

## 1. Environment split

- Development: local DB, debug enabled only when needed.
- Production: isolated server/VM, debug off, dedicated domain and HTTPS.
- Never reuse development `VENEX_SECRET_KEY` in production.

## 2. Install dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For testing:

```powershell
pip install -r requirements-dev.txt
pytest -q
```

## 3. Runtime server

### Windows (Waitress)

```powershell
waitress-serve --listen=0.0.0.0:5000 wsgi:app
```

### Linux (Gunicorn)

```bash
gunicorn --workers 2 --threads 4 --bind 127.0.0.1:8000 wsgi:app
```

## 4. Reverse proxy / HTTPS

- Use `deploy/nginx.conf.example` as base config.
- Point static alias to your deployed project static directory.
- Enable TLS with certbot after domain DNS setup.

## 5. Environment variables

Use `deploy/.env.example` as template.

- `VENEX_SECRET_KEY`: required, long random value.
- `VENEX_HOST` / `VENEX_PORT`: used by direct Flask run mode.
- `FLASK_DEBUG`: keep `false` in production.

## 6. Daily DB backup

Manual backup:

```powershell
python scripts/backup_db.py --db-dir db --out-dir backups
```

Restore latest backup:

```powershell
python scripts/restore_db.py --db-dir db --backup-root backups --source latest
```

Restore from specific backup:

```powershell
python scripts/restore_db.py --db-dir db --source "C:\path\to\backup_YYYYMMDD_HHMMSS.zip"
```

`restore_db.py` always creates a safety snapshot first under `backups/_safety`.

## 7. Windows task scheduler example

Create daily task (02:00):

```powershell
schtasks /Create /SC DAILY /TN "VENDIX_DB_BACKUP" /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\backup_task.ps1" /ST 02:00
```

Example `backup_task.ps1`:

```powershell
Set-Location "C:\path\to\Venex-main"
python scripts/backup_db.py --db-dir db --out-dir backups
```

## 8. Operational checks

- Confirm `/login` reachable through domain.
- Confirm admin login, purchase flow, and charge approval on production DB.
- Run backup job once manually and verify restore on a staging copy.
