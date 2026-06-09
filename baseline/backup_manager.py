import shutil
import sqlite3
import tarfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import store_facade
from panel_config import BACKUP_DIR, PANEL_DIR
from json_store import save_json


BACKUP_FILES = [
    "auth.json",
    "sub_token.txt",
    "audit.log",
    "subscription_access.log",
    "fake-ui.db",
    "fake-ui.db-wal",
    "fake-ui.db-shm",
]
BACKUP_NAMES = BACKUP_FILES
REQUIRED_META = "backup.json"
MAX_RESTORE_BYTES = 128 * 1024 * 1024


def now_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def create_backup(reason="manual", keep=20):
    if store_facade.use_sqlite():
        store_facade.ensure_sqlite()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    work = BACKUP_DIR / f"panel-backup-{now_stamp()}"
    work.mkdir(parents=True, exist_ok=False)
    meta = {"reason": reason, "created_at": datetime.now(timezone.utc).isoformat(), "files": []}
    for name in BACKUP_FILES:
        src = PANEL_DIR / name
        if src.exists():
            dst = work / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            meta["files"].append(name)
    save_json(work / "backup.json", meta, mode=0o600)
    archive = BACKUP_DIR / f"{work.name}.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(work, arcname=work.name)
    shutil.rmtree(work)
    prune_backups(keep)
    return {"name": archive.name, "path": str(archive), "size": archive.stat().st_size, "meta": meta}


def list_backups(limit=50):
    if not BACKUP_DIR.exists():
        return []
    items = sorted(BACKUP_DIR.glob("panel-backup-*.tgz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "path": str(p), "size": p.stat().st_size, "mtime": p.stat().st_mtime} for p in items[: int(limit or 50)]]


def backup_path(name):
    name = Path(str(name or "")).name
    if not name.startswith("panel-backup-") or not name.endswith(".tgz"):
        raise RuntimeError("backup name is invalid")
    path = (BACKUP_DIR / name).resolve()
    root = BACKUP_DIR.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise RuntimeError("backup path is invalid")
    if not path.exists():
        raise RuntimeError("backup not found")
    return path


def read_backup_bytes(name):
    return backup_path(name).read_bytes()


def _safe_member_name(member):
    name = str(member.name or "").replace("\\", "/")
    parts = [part for part in name.split("/") if part]
    if len(parts) < 2:
        return ""
    if any(part in (".", "..") for part in parts):
        raise RuntimeError("backup archive contains unsafe paths")
    return parts[-1]


def _extract_backup_files(raw):
    if len(raw) > MAX_RESTORE_BYTES:
        raise RuntimeError("backup archive is too large")
    allowed = set(BACKUP_FILES + [REQUIRED_META])
    found_meta = False
    archive_root = ""
    files = {}
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not archive_root:
                    archive_root = str(member.name or "").replace("\\", "/").split("/", 1)[0]
                if member.isdir():
                    continue
                name = _safe_member_name(member)
                if not name:
                    continue
                if name not in allowed:
                    continue
                if name == REQUIRED_META:
                    found_meta = True
                source = tar.extractfile(member)
                if source is not None:
                    content = source.read(MAX_RESTORE_BYTES + 1)
                    if len(content) > MAX_RESTORE_BYTES:
                        raise RuntimeError("backup file is too large")
                    files[name] = content
    except tarfile.TarError as exc:
        raise RuntimeError("backup archive is invalid") from exc
    if not found_meta:
        raise RuntimeError("backup metadata missing")
    return archive_root, files


def _chmod_restored_file(path, name):
    if name in {"fake-ui.db", "fake-ui.db-wal", "fake-ui.db-shm"}:
        path.chmod(0o600)
    elif name.endswith(".json") or name.endswith(".txt") or name.endswith(".log"):
        path.chmod(0o600)


def _check_sqlite_integrity(path):
    if not path.exists():
        return
    try:
        with sqlite3.connect(path) as conn:
            result = conn.execute("pragma integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("backup database integrity check failed") from exc
    if not result or str(result[0]).lower() != "ok":
        raise RuntimeError("backup database integrity check failed")


def restore_backup_archive(raw, operator="admin"):
    if not raw:
        raise RuntimeError("backup archive is empty")
    create_backup(reason=f"pre-restore by {operator}", keep=30)
    archive_root, files = _extract_backup_files(raw)
    restored = []
    for name, content in files.items():
        if name == REQUIRED_META:
            continue
        if name not in BACKUP_FILES:
            continue
        target = PANEL_DIR / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        _chmod_restored_file(target, name)
        restored.append(name)
    _check_sqlite_integrity(PANEL_DIR / "fake-ui.db")
    marker = BACKUP_DIR / f"imported-{now_stamp()}.tgz"
    marker.write_bytes(raw)
    archive_name = f"{archive_root}.tgz" if archive_root else marker.name
    if store_facade.use_sqlite():
        store_facade.ensure_sqlite()
    return {
        "restored": {"name": archive_name, "path": str(marker), "size": marker.stat().st_size},
        "files": restored,
        "safety_backup": list_backups(1)[0] if list_backups(1) else None,
    }


def prune_backups(keep=20):
    items = sorted(BACKUP_DIR.glob("panel-backup-*.tgz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in items[int(keep or 20):]:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
