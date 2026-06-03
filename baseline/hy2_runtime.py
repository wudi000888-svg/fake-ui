import os
import shutil
import time

from panel_config import HY2_BACKUP_DIR, HY2_CONFIG_FILE, HY2_LOGS_CMD, HY2_RESTART_CMD, HY2_STATUS_CMD
from sync_utils import run_shell


def backup_config(prefix="panel-before-change"):
    HY2_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    backup = HY2_BACKUP_DIR / f"server.yaml.bak.{prefix}.{ts}"
    shutil.copy2(HY2_CONFIG_FILE, backup)
    return backup


def validate_config_text(text):
    if "listen:" not in text or "auth:" not in text or "outbounds:" not in text:
        raise RuntimeError("Hysteria2 配置生成不完整。")
    return True


def restart_with_rollback(new_config_text):
    if not HY2_CONFIG_FILE.exists():
        raise RuntimeError("未找到 /opt/hysteria2/server.yaml")

    validate_config_text(new_config_text)
    backup = backup_config()
    HY2_CONFIG_FILE.write_text(new_config_text, encoding="utf-8")
    os.chmod(HY2_CONFIG_FILE, 0o644)

    code, out = run_shell(HY2_RESTART_CMD, timeout=60)
    time.sleep(3)
    code2, running = run_shell(HY2_STATUS_CMD, timeout=20)
    code3, logs = run_shell(HY2_LOGS_CMD, timeout=20)

    if code != 0 or code2 != 0 or running.strip().lower() not in ("true", "active", "running"):
        shutil.copy2(backup, HY2_CONFIG_FILE)
        run_shell(HY2_RESTART_CMD, timeout=60)
        raise RuntimeError("Hysteria2 重启失败，已自动回滚。\n\n" + out + "\n\n" + logs)

    return backup, logs
