import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path, timeout=10):
    path = Path(path)
    lock_path = path.with_name(path.name + ".lock")
    deadline = time.time() + float(timeout or 10)
    fd = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            break
        except FileExistsError:
            if time.time() >= deadline:
                raise RuntimeError(f"等待文件锁超时：{lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_json(path, default=None, create=False, mode=0o600):
    path = Path(path)
    if not path.exists():
        data = default() if callable(default) else default
        if create:
            save_json(path, data, mode=mode)
        return data
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    with file_lock(path):
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(raw)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
            os.chmod(path, mode)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
    return data

