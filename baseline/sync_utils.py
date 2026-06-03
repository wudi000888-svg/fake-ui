import shutil
import subprocess
import time


def run(cmd, timeout=60):
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def run_shell(cmd, timeout=60):
    p = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def backup_file(src, backup_dir, prefix):
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    dst = backup_dir / f"{src.name}.bak.{prefix}.{ts}"
    shutil.copy2(src, dst)
    return dst
