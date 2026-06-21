#!/usr/bin/env python3
import argparse
import subprocess
import tarfile
from pathlib import Path


SKIP_TOP_LEVEL = {".demo-runtime", ".env", ".git", ".superpowers", "artifacts", "data", "generated"}
SKIP_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tar", ".tgz", ".gz", ".zip"}


def root_dir():
    return Path(__file__).resolve().parents[1]


def git_files(root):
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        yield from source_tree_files(root)
        return
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        if should_skip(name):
            continue
        yield name


def should_skip(name):
    parts = Path(name).parts
    if not parts:
        return True
    if parts[0] in SKIP_TOP_LEVEL:
        return True
    if any(part in SKIP_NAMES for part in parts):
        return True
    if any(part.startswith("._") for part in parts):
        return True
    return Path(name).suffix in SKIP_SUFFIXES


def source_tree_files(root):
    for path in root.rglob("*"):
        if not path.is_file() and not path.is_symlink():
            continue
        name = path.relative_to(root).as_posix()
        if should_skip(name):
            continue
        yield name


def reset_tar_metadata(info):
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.pax_headers = {}
    return info


def create_archive(output):
    root = root_dir()
    output = Path(output).expanduser()
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output, "w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(git_files(root)):
            path = root / name
            if not path.exists():
                continue
            archive.add(path, arcname=name, recursive=True, filter=reset_tar_metadata)
    return output


def main():
    parser = argparse.ArgumentParser(description="Package fake-ui code without runtime data or macOS metadata.")
    parser.add_argument("output", help="Output .tar path")
    args = parser.parse_args()
    output = create_archive(args.output)
    print(output)


if __name__ == "__main__":
    main()
