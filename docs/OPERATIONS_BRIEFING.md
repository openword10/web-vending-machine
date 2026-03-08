# VENDIX Operations Briefing

## Scope

This briefing covers the production-hardening package:

1. Transaction/lock hardening for purchase and charge approval flows.
2. Admin audit logging.
3. Daily DB backup/restore scripts.
4. Minimal E2E automation.
5. Deployment baseline files.

## 1) Transaction and lock hardening

### Goal

Prevent race conditions such as:

- Double stock deduction
- Duplicate charge approval
- Partial write success when one query fails

### Method

- Use `BEGIN IMMEDIATE` before write-critical operations.
- Keep related writes in one transaction.
- `COMMIT` only after all checks and writes pass.
- `ROLLBACK` on validation failure or exception.

### Applied areas

- Admin setting updates
- User management updates
- Product create/update/delete
- Charge request approval/delete/toggle auto-approve
- Shop charge request creation
- Product purchase flow
- OCR auto-approval worker path

## 2) Admin audit logging

### Table

- `admin_audit_log`
- Columns:
  - `id`
  - `admin_id`
  - `action`
  - `target`
  - `before_json`
  - `after_json`
  - `ip`
  - `created_at`

### Logging strategy

- Before/after snapshot is serialized to JSON.
- Each write action records actor and target resource.
- Core actions now audited:
  - `setting.update`
  - `user.update`
  - `product.create`
  - `product.update`
  - `product.delete`
  - `charge.auto_toggle`
  - `charge.request_delete`
  - `charge.request_accept`

### Read path

- Route: `/audit_log`
- Template: `templates/admin_audit_log.html`
- Purpose: read-only admin activity trace.

## 3) DB backup and restore

### Files

- `scripts/backup_db.py`
- `scripts/restore_db.py`

### Backup algorithm

1. Discover `*.db` in target DB directory.
2. Copy files into timestamped backup folder.
3. Optionally zip output (default: zip).

### Restore algorithm

1. Resolve source backup (`latest` or explicit path).
2. Create automatic safety backup of current live DB first.
3. Restore all `*.db` files from selected backup source.

## 4) Minimal E2E automation

### File

- `tests/test_e2e_flow.py`

### Scenario coverage

1. Admin login
2. Product creation
3. Shop member signup
4. Charge request creation
5. Admin charge approval
6. Product purchase and delivery page check
7. DB post-conditions (balance/stock/log tables)
8. Audit action presence check

## 5) Deployment baseline

### Files

- `wsgi.py`
- `deploy/nginx.conf.example`
- `deploy/.env.example`
- `requirements.txt`
- `requirements-dev.txt`
- `DEPLOYMENT.md`

### Intent

- Make runtime entrypoint explicit (`wsgi:app`).
- Provide reverse-proxy skeleton.
- Separate runtime and dev dependencies.
- Provide setup/run/backup instructions for operations.
