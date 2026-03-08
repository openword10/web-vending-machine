import argparse
import datetime as dt
import os
import shutil
import sys
import zipfile
from pathlib import Path


def find_db_files(db_dir: Path):
    if not db_dir.exists():
        return []
    return sorted([p for p in db_dir.glob("*.db") if p.is_file()])


def backup_databases(db_dir: Path, out_dir: Path, compress: bool) -> Path:
    now = dt.datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    backup_root = out_dir / now.strftime("%Y-%m-%d")
    backup_root.mkdir(parents=True, exist_ok=True)

    staging = backup_root / f"backup_{stamp}"
    staging.mkdir(parents=True, exist_ok=True)

    db_files = find_db_files(db_dir)
    if not db_files:
        raise RuntimeError(f"No .db files found in {db_dir}")

    for db_file in db_files:
        shutil.copy2(db_file, staging / db_file.name)

    if not compress:
        return staging

    zip_path = backup_root / f"backup_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for copied in sorted(staging.glob("*.db")):
            zf.write(copied, arcname=copied.name)
    shutil.rmtree(staging, ignore_errors=True)
    return zip_path


def parse_args():
    parser = argparse.ArgumentParser(description="Backup Venex SQLite DB files.")
    parser.add_argument("--db-dir", default="db", help="Directory containing *.db files")
    parser.add_argument("--out-dir", default="backups", help="Backup output directory")
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Store as a plain folder instead of .zip",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    db_dir = Path(args.db_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = backup_databases(db_dir=db_dir, out_dir=out_dir, compress=not args.no_compress)
    except Exception as exc:
        print(f"[backup_db] failed: {exc}")
        return 1
    print(f"[backup_db] ok: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
