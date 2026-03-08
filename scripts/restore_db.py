import argparse
import datetime as dt
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


def list_backup_candidates(backup_root: Path):
    if not backup_root.exists():
        return []
    zips = sorted([p for p in backup_root.rglob("*.zip") if p.is_file()], key=lambda p: p.stat().st_mtime)
    dirs = sorted(
        [
            p
            for p in backup_root.rglob("*")
            if p.is_dir() and p.name.startswith("backup_")
        ],
        key=lambda p: p.stat().st_mtime,
    )
    return zips + dirs


def create_safety_backup(db_dir: Path, safety_root: Path):
    safety_root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_dir = safety_root / f"pre_restore_{stamp}"
    safety_dir.mkdir(parents=True, exist_ok=True)
    for db_file in db_dir.glob("*.db"):
        if db_file.is_file():
            shutil.copy2(db_file, safety_dir / db_file.name)
    return safety_dir


def restore_from_folder(source_dir: Path, db_dir: Path):
    db_files = sorted([p for p in source_dir.glob("*.db") if p.is_file()])
    if not db_files:
        raise RuntimeError(f"No .db files in backup folder: {source_dir}")
    db_dir.mkdir(parents=True, exist_ok=True)
    for db_file in db_files:
        shutil.copy2(db_file, db_dir / db_file.name)
    return [db_file.name for db_file in db_files]


def restore_from_zip(zip_path: Path, db_dir: Path):
    with tempfile.TemporaryDirectory(prefix="venex_restore_") as td:
        temp_root = Path(td)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_root)
        return restore_from_folder(temp_root, db_dir)


def parse_args():
    parser = argparse.ArgumentParser(description="Restore Venex SQLite DB files from backup.")
    parser.add_argument("--db-dir", default="db", help="Live DB directory")
    parser.add_argument("--backup-root", default="backups", help="Backup root directory")
    parser.add_argument(
        "--source",
        default="latest",
        help="Backup source path (.zip/folder) or 'latest'",
    )
    parser.add_argument(
        "--safety-dir",
        default="backups/_safety",
        help="Safety backup output directory before restore",
    )
    return parser.parse_args()


def resolve_source(source_arg: str, backup_root: Path):
    if source_arg != "latest":
        return Path(source_arg).resolve()
    candidates = list_backup_candidates(backup_root)
    if not candidates:
        raise RuntimeError(f"No backups found in {backup_root}")
    return candidates[-1]


def main():
    args = parse_args()
    db_dir = Path(args.db_dir).resolve()
    backup_root = Path(args.backup_root).resolve()
    source = resolve_source(args.source, backup_root)
    safety_root = Path(args.safety_dir).resolve()

    if not source.exists():
        print(f"[restore_db] source not found: {source}")
        return 1

    safety_dir = create_safety_backup(db_dir, safety_root)
    print(f"[restore_db] safety backup saved: {safety_dir}")

    try:
        if source.is_file() and source.suffix.lower() == ".zip":
            restored = restore_from_zip(source, db_dir)
        elif source.is_dir():
            restored = restore_from_folder(source, db_dir)
        else:
            raise RuntimeError("Source must be a .zip file or backup folder.")
    except Exception as exc:
        print(f"[restore_db] failed: {exc}")
        return 1

    print(f"[restore_db] restored from: {source}")
    print(f"[restore_db] files: {', '.join(restored)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
