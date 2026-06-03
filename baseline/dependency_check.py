import shutil

from panel_config import QR_CMD, XRAY_BIN


def check_dependencies(require_xray=False, require_qr=False, require_docker=False):
    missing = []
    if require_xray and not shutil.which(XRAY_BIN):
        missing.append(XRAY_BIN)
    if require_qr and not shutil.which(QR_CMD):
        missing.append(QR_CMD)
    if require_docker and not shutil.which("docker"):
        missing.append("docker")
    if missing:
        raise RuntimeError("缺少依赖命令：" + ", ".join(missing))
    return True

