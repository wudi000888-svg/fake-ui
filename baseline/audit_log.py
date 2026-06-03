import json
from datetime import datetime, timezone

from panel_config import AUDIT_LOG_FILE


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def write(actor, action, target="", detail=None, ip=""):
    entry = {
        "time": now_iso(),
        "actor": actor or "system",
        "action": action,
        "target": target,
        "detail": detail or {},
        "ip": ip,
    }
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return entry


def tail(limit=200):
    if not AUDIT_LOG_FILE.exists():
        return []
    lines = AUDIT_LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    result = []
    for line in lines[-int(limit or 200):]:
        try:
            result.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(result))
