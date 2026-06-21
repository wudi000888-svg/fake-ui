import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_package_code_excludes_runtime_data_and_macos_pax_headers(tmp_path):
    archive = tmp_path / "fake-ui-code.tar"

    subprocess.run(
        ["python3", "scripts/package-code.py", str(archive)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    with tarfile.open(archive, "r") as tar:
        names = set(tar.getnames())
        pax_headers = {}
        for member in tar.getmembers():
            pax_headers.update(member.pax_headers)

    assert "baseline/app_version.py" in names
    assert "docs/releases/v3.0.0.md" in names
    assert "docs/releases/v3.0.1.md" in names
    assert not any(name == ".env" or name.startswith("data/") for name in names)
    assert not any(name.startswith("generated/") or name.startswith(".git/") for name in names)
    assert not any(name.startswith("artifacts/") or name.startswith(".demo-runtime/") for name in names)
    assert not any(key.startswith("LIBARCHIVE.xattr") or key.startswith("SCHILY.") for key in pax_headers)


def test_package_code_works_from_source_tree_without_git_metadata(tmp_path):
    source = tmp_path / "source"
    archive = tmp_path / "fake-ui-code.tar"
    source.mkdir()
    (source / "scripts").mkdir()
    (source / "baseline").mkdir()
    (source / "data").mkdir()
    (source / "generated").mkdir()
    (source / ".git").mkdir()
    (source / "artifacts").mkdir()
    (source / ".demo-runtime").mkdir()
    (source / ".superpowers").mkdir()
    (source / "__pycache__").mkdir()
    (source / "scripts" / "package-code.py").write_text((ROOT / "scripts" / "package-code.py").read_text(encoding="utf-8"), encoding="utf-8")
    (source / "baseline" / "app_version.py").write_text("APP_VERSION = 'test'\n", encoding="utf-8")
    (source / "data" / "fake-ui.db").write_text("secret", encoding="utf-8")
    (source / "generated" / "cert.pem").write_text("secret", encoding="utf-8")
    (source / "artifacts" / "screenshot.png").write_bytes(b"png")
    (source / ".demo-runtime" / "fake-ui.db").write_text("runtime", encoding="utf-8")
    (source / ".superpowers" / "local.json").write_text("local", encoding="utf-8")
    (source / ".env").write_text("secret=value\n", encoding="utf-8")
    (source / "__pycache__" / "x.pyc").write_bytes(b"cached")

    subprocess.run(
        ["python3", "scripts/package-code.py", str(archive)],
        cwd=source,
        check=True,
        text=True,
        capture_output=True,
    )

    with tarfile.open(archive, "r") as tar:
        names = set(tar.getnames())

    assert "baseline/app_version.py" in names
    assert "scripts/package-code.py" in names
    assert ".env" not in names
    assert "data/fake-ui.db" not in names
    assert "generated/cert.pem" not in names
    assert "artifacts/screenshot.png" not in names
    assert ".demo-runtime/fake-ui.db" not in names
    assert ".superpowers/local.json" not in names
    assert "__pycache__/x.pyc" not in names
