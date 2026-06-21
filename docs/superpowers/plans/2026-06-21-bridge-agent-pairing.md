# Bridge Agent Pairing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paired Bridge Agent packages that bootstrap from fake-ui and show a polished local fake-ui-style dashboard.

**Architecture:** The panel creates one-time pairing records and paired bundle endpoints. The local Agent reads `agent-profile.json`, calls `/api/agents/bootstrap`, writes config/state files, then runs a local-only dashboard with fake-ui styling. Future remote-control fields are stored but no remote command execution is implemented.

**Tech Stack:** Python stdlib backend, existing fake-ui JSON/SQLite settings patterns, native ES module frontend, pytest.

---

## File Structure

- Create `baseline/agent_pairing.py`: pairing token generation, hashing, validation, bootstrap response assembly.
- Create `baseline/api_agent_routes.py`: public bootstrap POST route.
- Modify `baseline/api_post_routes.py`: route `/api/agents/bootstrap` before admin-only routes.
- Modify `baseline/api_tunnel_routes.py`: paired bundle GET endpoints for dedicated/shared bridges.
- Modify `baseline/tunnel_bridge_bundle.py`: add `agent-profile.json`, bootstrap client helpers, enhanced dashboard UI.
- Modify `baseline/frontend/assets/js/pages/admin/tunnels.js`: add paired Agent actions.
- Modify `baseline/frontend/assets/js/actions/users_nodes.js`: call paired bundle endpoints.
- Modify `scripts/package-bridge-client.py`: include paired/client bootstrap helpers in standalone client assets.
- Test `tests/test_agent_pairing.py`: new pairing and bootstrap API tests.
- Modify `tests/test_tunnel_automation.py`: bundle/profile/dashboard assertions.
- Modify `tests/test_frontend_v2_structure.py`: frontend action visibility.

Use this Python for tests if the worktree has no venv:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest ...
```

---

### Task 1: Pairing Store And Bootstrap API

**Files:**
- Create: `baseline/agent_pairing.py`
- Create: `baseline/api_agent_routes.py`
- Modify: `baseline/api_post_routes.py`
- Test: `tests/test_agent_pairing.py`

- [ ] **Step 1: Write failing tests**

Add tests that verify pairing records hash tokens, bootstrap consumes a valid token once, expired tokens fail, and bootstrap returns `agent_id`, `capabilities`, `xray_config`, and `dashboard_metadata`.

- [ ] **Step 2: Run red tests**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_agent_pairing.py -q
```

Expected: fails because `agent_pairing` or `/api/agents/bootstrap` does not exist.

- [ ] **Step 3: Implement minimal pairing store**

Use `SQLiteSettingsRepository` with a key such as `agent_pairings`. Store only `token_hash`, never raw token. Include `create_pairing`, `consume_pairing`, `bootstrap_agent`, and helpers for dedicated/shared bridge config lookup.

- [ ] **Step 4: Add bootstrap route**

Route `POST /api/agents/bootstrap` without admin session requirement. Validate `schema`, `token_id`, and `pairing_token`; return HTTP 400 for expired/reused/invalid tokens.

- [ ] **Step 5: Run green tests and commit**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_agent_pairing.py -q
```

Expected: pass.

Commit:

```bash
git add baseline/agent_pairing.py baseline/api_agent_routes.py baseline/api_post_routes.py tests/test_agent_pairing.py
git commit -m "feat: add bridge agent pairing bootstrap"
```

### Task 2: Paired Agent Bundles And Local Bootstrap

**Files:**
- Modify: `baseline/api_tunnel_routes.py`
- Modify: `baseline/tunnel_bridge_bundle.py`
- Modify: `scripts/package-bridge-client.py`
- Test: `tests/test_tunnel_automation.py`

- [ ] **Step 1: Write failing bundle tests**

Add tests for dedicated and shared `*-agent-bundle` endpoints. Assert tar contents include `agent-profile.json`, `bootstrap-agent.py` or equivalent local bootstrap helper, enhanced dashboard files, and no raw token appears outside `agent-profile.json`.

- [ ] **Step 2: Run red tests**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_tunnel_automation.py -q
```

Expected: new tests fail because paired bundles are missing.

- [ ] **Step 3: Implement paired bundle endpoints**

Add:

- `/api/tunnels/{id}/{platform}-agent-bundle`
- `/api/tunnels/bridges/{bridge_id}/{platform}-agent-bundle`

These create a pairing record and call a paired bundle builder with `agent-profile.json`.

- [ ] **Step 4: Implement local bootstrap helper**

Bundle a Python helper that reads `agent-profile.json`, POSTs to `/api/agents/bootstrap`, writes `xray-bridge.json`, `bridge-dashboard.json`, and `agent-state.json`, then removes or blanks `pairing_token` in the profile.

- [ ] **Step 5: Wire install scripts**

Update macOS/Linux/Windows install scripts so paired bundles run bootstrap before config validation. Keep existing non-paired bundle behavior.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_agent_pairing.py tests/test_tunnel_automation.py -q
```

Expected: pass.

Commit:

```bash
git add baseline/api_tunnel_routes.py baseline/tunnel_bridge_bundle.py scripts/package-bridge-client.py tests/test_tunnel_automation.py
git commit -m "feat: package paired bridge agents"
```

### Task 3: Local Dashboard Visual Upgrade

**Files:**
- Modify: `baseline/tunnel_bridge_bundle.py`
- Test: `tests/test_tunnel_automation.py`

- [ ] **Step 1: Write failing dashboard tests**

Add tests asserting `dashboard_script()` contains fake-ui style tokens such as `--bg`, `--surface`, `--primary`, `app-shell`, a side nav, overview/services/setup/log sections, `/status.json`, and redaction of sensitive terms.

- [ ] **Step 2: Run red tests**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_tunnel_automation.py::test_bridge_dashboard_serves_local_status_json -q
```

Expected: existing status test passes, but the new visual assertions fail.

- [ ] **Step 3: Implement dashboard UI**

Keep the local server Python-only. Redesign `render_dashboard` with fake-ui tokens, metric cards, service cards/table, setup panel, logs, and API section. Keep host locked to `127.0.0.1`.

- [ ] **Step 4: Add redaction**

Ensure rendered logs/config snippets redact UUIDs, private/public keys, short IDs, and pairing tokens before display.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_tunnel_automation.py -q
```

Expected: pass.

Commit:

```bash
git add baseline/tunnel_bridge_bundle.py tests/test_tunnel_automation.py
git commit -m "feat: polish bridge agent dashboard"
```

### Task 4: Panel Frontend Agent Actions

**Files:**
- Modify: `baseline/frontend/assets/js/pages/admin/tunnels.js`
- Modify: `baseline/frontend/assets/js/actions/users_nodes.js`
- Test: `tests/test_frontend_v2_structure.py`

- [ ] **Step 1: Write failing frontend tests**

Add tests that assert the tunnel page includes paired Agent buttons for dedicated and shared bridges and action handlers call the new `agent-bundle` endpoints.

- [ ] **Step 2: Run red tests**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_frontend_v2_structure.py -q
```

Expected: fails because paired Agent actions are not present.

- [ ] **Step 3: Implement UI actions**

Change labels from only "download backend install package" to include "Generate paired Agent". Keep existing plain bundle and JSON export available. For shared bridges, use bridge-level paired endpoint.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_frontend_v2_structure.py -q
```

Expected: pass.

Commit:

```bash
git add baseline/frontend/assets/js/pages/admin/tunnels.js baseline/frontend/assets/js/actions/users_nodes.js tests/test_frontend_v2_structure.py
git commit -m "feat: add paired agent panel actions"
```

### Task 5: Integration Verification And Release Notes

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/releases/v3.0.1.md` or create next release note if appropriate

- [ ] **Step 1: Update docs**

Document paired Agent setup, local dashboard, manual JSON fallback, and future remote-control boundary.

- [ ] **Step 2: Run focused tests**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest tests/test_agent_pairing.py tests/test_tunnel_automation.py tests/test_frontend_v2_structure.py -q
```

Expected: pass.

- [ ] **Step 3: Run full tests**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python -m pytest -q
```

Expected: pass.

- [ ] **Step 4: Package client assets**

Run:

```bash
/Users/wan/Documents/Codex/2026-06-21/record-and-replay-plugin-record-and/work/fake-ui/.venv/bin/python scripts/package-bridge-client.py /tmp/fake-ui-bridge-client-check --version 3.0.2
```

Expected: macOS, Linux, and Windows assets are generated.

- [ ] **Step 5: Commit docs**

Commit:

```bash
git add README.md CHANGELOG.md docs/releases
git commit -m "docs: describe paired bridge agents"
```
