import json
import re
import subprocess
import urllib.error
import urllib.request

from panel_config import HY2_TRAFFIC_SECRET_FILE, XRAY_API_SERVER, XRAY_BIN


def run(cmd, timeout=30):
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def to_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def query_xray_stats():
    code, out = run([
        XRAY_BIN,
        "api",
        "statsquery",
        f"--server={XRAY_API_SERVER}",
        "-pattern",
        "user>>>"
    ], timeout=30)

    if code != 0:
        print("WARNING: xray statsquery failed:")
        print(out)
        return {}

    stats = {}

    try:
        data = json.loads(out)
        for item in data.get("stat", []):
            name = item.get("name")
            value = item.get("value", 0)
            if name:
                stats[name] = int(value)
    except Exception:
        pass

    for name, value in re.findall(r'name:\s*"([^"]+)".*?value:\s*(\d+)', out, re.S):
        stats[name] = int(value)

    for name, value in re.findall(r'([A-Za-z0-9:_>\-\.]+traffic>>>[A-Za-z]+)\s+(\d+)', out):
        stats[name] = int(value)

    return stats


def query_hy2_stats():
    if not HY2_TRAFFIC_SECRET_FILE.exists():
        return {}

    secret = HY2_TRAFFIC_SECRET_FILE.read_text(encoding="utf-8").strip()
    if not secret:
        return {}

    req = urllib.request.Request(
        "http://127.0.0.1:9999/traffic",
        headers={"Authorization": secret},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"WARNING: hysteria2 traffic query failed: {e}")
        return {}

    stats = {}

    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            stats[str(key)] = {
                "tx": to_int(value.get("tx", value.get("upload", 0))),
                "rx": to_int(value.get("rx", value.get("download", 0))),
            }

    return stats
