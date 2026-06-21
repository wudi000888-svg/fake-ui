from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_updates_existing_release_and_uploads_bridge_clients():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "scripts/package-bridge-client.py" in workflow
    assert "gh release upload" in workflow
    assert "--clobber" in workflow
    assert "gh release view \"$GITHUB_REF_NAME\"" in workflow
    assert "gh release edit" in workflow
    assert "gh release create" in workflow
    assert "fake-ui-bridge-client-v${GITHUB_REF_NAME#v}-macos.zip" in workflow
    assert "fake-ui-bridge-client-v${GITHUB_REF_NAME#v}-linux.tar.gz" in workflow
    assert "fake-ui-bridge-client-v${GITHUB_REF_NAME#v}-windows.zip" in workflow
