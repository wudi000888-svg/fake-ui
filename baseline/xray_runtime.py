import json
import os
import shutil
import tempfile
import time

from panel_config import XRAY_BACKUP_DIR, XRAY_BIN, XRAY_CONFIG, XRAY_RESTART_CMD, XRAY_STATUS_CMD
from process_utils import run
from sync_utils import run_shell


def load_config():
    return json.loads(XRAY_CONFIG.read_text(encoding="utf-8"))


def backup_xray_config(prefix="panel-before-change"):
    XRAY_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    backup = XRAY_BACKUP_DIR / f"config.json.bak.{prefix}.{ts}"
    shutil.copy2(XRAY_CONFIG, backup)
    return backup


def validate_config_file(path):
    code, out = run([XRAY_BIN, "run", "-test", "-config", str(path)], timeout=60)
    if code != 0:
        raise RuntimeError("Xray 配置测试失败：\n" + out)
    return out


def write_temp_config(cfg):
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as temp:
        json.dump(cfg, temp, indent=2, ensure_ascii=False)
        return temp.name


def prepare_xray_permissions():
    run(["mkdir", "-p", "/var/log/xray"], timeout=10)
    run(["chown", "-R", "nobody:nogroup", "/var/log/xray"], timeout=10)
    run(["chmod", "755", "/var/log/xray"], timeout=10)
    run(["chown", "root:nogroup", str(XRAY_CONFIG)], timeout=10)
    os.chmod(XRAY_CONFIG, 0o640)


def restart_and_assert():
    code, out = run_shell(XRAY_RESTART_CMD, timeout=60)
    if code != 0:
        raise RuntimeError("Xray 重启失败：\n" + out)

    code, state = run_shell(XRAY_STATUS_CMD, timeout=10)
    if code != 0 or state.strip().lower() not in ("active", "true", "running"):
        raise RuntimeError("Xray 未保持 active。")
    return state


def write_and_restart_xray(cfg):
    temp_path = write_temp_config(cfg)
    try:
        validate_config_file(temp_path)
        backup = backup_xray_config()
        shutil.copy2(temp_path, XRAY_CONFIG)
        prepare_xray_permissions()
        try:
            restart_and_assert()
        except Exception:
            shutil.copy2(backup, XRAY_CONFIG)
            run_shell(XRAY_RESTART_CMD, timeout=60)
            raise RuntimeError("Xray 重启失败，已自动回滚。")
        return backup
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
