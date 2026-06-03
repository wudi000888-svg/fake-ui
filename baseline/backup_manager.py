import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from panel_config import BACKUP_DIR, PANEL_DIR
from json_store import save_json


BACKUP_NAMES = [
    "auth.json",
    "users.json",
    "plans.json",
    "orders.json",
    "nodes.json",
    "admin_profile.json",
    "registrations.json",
    "link_settings.json",
    "sub_token.txt",
    "audit.log",
    "subscription_access.log",
]


def now_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def create_backup(reason="manual", keep=20):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    work = BACKUP_DIR / f"panel-backup-{now_stamp()}"
    work.mkdir(parents=True, exist_ok=False)
    meta = {"reason": reason, "created_at": datetime.now(timezone.utc).isoformat(), "files": []}
    for name in BACKUP_NAMES:
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
    return {"path": str(archive), "meta": meta}


def list_backups(limit=50):
    if not BACKUP_DIR.exists():
        return []
    items = sorted(BACKUP_DIR.glob("panel-backup-*.tgz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "path": str(p), "size": p.stat().st_size, "mtime": p.stat().st_mtime} for p in items[: int(limit or 50)]]


def prune_backups(keep=20):
    items = sorted(BACKUP_DIR.glob("panel-backup-*.tgz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in items[int(keep or 20):]:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
