import json
import time
from collections import Counter

from panel_config import SUB_ACCESS_LOG_FILE


WINDOW_SECONDS = 300
MAX_REQUESTS_PER_WINDOW = 60


def now_ts():
    return int(time.time())


def client_ip(headers=None, fallback=""):
    headers = headers or {}
    for key in ("X-Forwarded-For", "x-forwarded-for", "X-Real-IP", "x-real-ip"):
        value = headers.get(key)
        if value:
            return value.split(",", 1)[0].strip()
    return fallback or ""


def log_access(username, token, path, ip="", ua="", status="ok"):
    entry = {
        "time": now_ts(),
        "username": username,
        "token": token[:10] + "..." if token else "",
        "path": path,
        "ip": ip,
        "ua": (ua or "")[:240],
        "status": status,
    }
    SUB_ACCESS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SUB_ACCESS_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return entry


def tail(limit=200):
    if not SUB_ACCESS_LOG_FILE.exists():
        return []
    lines = SUB_ACCESS_LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    result = []
    for line in lines[-int(limit or 200):]:
        try:
            result.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(result))


def too_many_requests(username, ip):
    if not SUB_ACCESS_LOG_FILE.exists():
        return False
    cutoff = now_ts() - WINDOW_SECONDS
    count = 0
    for item in tail(1000):
        try:
            if int(item.get("time", 0)) < cutoff:
                continue
        except Exception:
            continue
        if item.get("username") == username and item.get("ip") == ip and item.get("status") == "ok":
            count += 1
    return count >= MAX_REQUESTS_PER_WINDOW


def ip_summary(username=None, limit=100):
    counts = Counter()
    for item in tail(2000):
        if username and item.get("username") != username:
            continue
        if item.get("ip"):
            counts[item["ip"]] += 1
    return [{"ip": ip, "count": count} for ip, count in counts.most_common(limit)]
