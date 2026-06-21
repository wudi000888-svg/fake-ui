# Bridge Agent Pairing Design

## Goal

Build a polished local Bridge Agent app that matches the fake-ui panel style and can be set up from fake-ui with one guided action. The first release implements one-way pairing and local control, while leaving data and API seams for a later two-way remote control release.

## Context

fake-ui v3.0.1 already supports tunnel nodes, dedicated bridge bundles, shared bridge bundles, and a local dashboard at `127.0.0.1:19090`. The current local dashboard is useful for diagnostics, but it is visually separate from fake-ui and still expects users to download or copy bridge configuration manually.

The new Agent flow should keep the safe network boundary: the customer machine does not expose a public management port. The Agent initiates every management request to the panel.

## Product Scope

### In Scope For This Release

- Add panel-side "pair Agent" actions for dedicated and shared tunnel bridges.
- Generate an Agent bundle that contains a non-secret pairing profile instead of only static instructions.
- Let the local Agent bootstrap itself from fake-ui by exchanging a short-lived pairing token for bridge configuration and dashboard metadata.
- Redesign the local `127.0.0.1:19090` app using the same fake-ui visual language: side navigation, top bar, metric cards, service list, logs, and compact action buttons.
- Keep manual JSON import for offline or restricted environments.
- Support macOS, Linux, and Windows packaging.

### Out Of Scope For This Release

- Remote command execution from the panel to the customer machine.
- Panel-side live log streaming from the Agent.
- Auto-update of the Agent binary.
- Public exposure of the local Agent dashboard.

## Recommended Flow

1. The admin creates or edits a tunnel in fake-ui.
2. The admin clicks "Generate Agent package" for a dedicated tunnel or shared bridge.
3. fake-ui creates a short-lived pairing token and includes it in `agent-profile.json`.
4. The customer downloads and runs the package on macOS, Linux, or Windows.
5. The local Agent reads `agent-profile.json`, calls the panel bootstrap endpoint, downloads its `xray-bridge.json`, writes `bridge-dashboard.json`, validates the Xray config, installs or restarts the system service, and opens the local dashboard.
6. The local dashboard shows panel pairing state, Xray runtime state, local service probes, public URLs, config status, and logs.

## Panel Data Model

Add an Agent pairing record store alongside tunnel data. A pairing record is not the long-lived Agent identity; it is a bootstrap credential.

Fields:

- `token_id`: public identifier included in `agent-profile.json`.
- `token_hash`: server-side hash of the raw token.
- `bridge_id`: dedicated tunnel id or shared bridge id.
- `bundle_kind`: `dedicated` or `shared`.
- `platform`: `macos`, `linux`, or `windows`.
- `expires_at`: default 30 minutes after creation.
- `used_at`: set after successful bootstrap.
- `created_at`: audit timestamp.
- `created_by`: admin username.
- `agent_id`: reserved for the future C-style managed Agent identity.
- `capabilities`: reserved list, initially empty or `["bootstrap", "local_status"]`.

The raw token is only returned once, during package generation. The repository and logs must never store raw tokens.

## Agent Profile

Every paired Agent bundle includes `agent-profile.json`.

Example shape:

```json
{
  "schema": 1,
  "panel_url": "https://panel.example.com",
  "token_id": "pair_abc123",
  "pairing_token": "shown-once-random-token",
  "bridge_id": "office-macbook",
  "bundle_kind": "shared",
  "platform": "macos",
  "agent_name": "office-macbook",
  "dashboard": {
    "host": "127.0.0.1",
    "port": 19090
  },
  "reserved": {
    "agent_id": "",
    "capabilities": ["bootstrap", "local_status"]
  }
}
```

The profile is sensitive because it contains a short-lived raw pairing token. The local dashboard may display the panel URL and bridge id, but must not display the token.

## Panel API

### Create Paired Bundle

Existing bundle endpoints remain available. Add paired variants:

- `GET /api/tunnels/{id}/{platform}-agent-bundle`
- `GET /api/tunnels/bridges/{bridge_id}/{platform}-agent-bundle`

These endpoints create a pairing token, build the Agent bundle, and include `agent-profile.json`.

### Bootstrap

Add:

`POST /api/agents/bootstrap`

Request:

```json
{
  "schema": 1,
  "token_id": "pair_abc123",
  "pairing_token": "shown-once-random-token",
  "platform": "macos",
  "agent_version": "3.0.2"
}
```

Response:

```json
{
  "ok": true,
  "agent": {
    "agent_id": "agent_abc123",
    "bridge_id": "office-macbook",
    "bundle_kind": "shared",
    "capabilities": ["bootstrap", "local_status"]
  },
  "xray_config": {},
  "dashboard_metadata": {},
  "install": {
    "service_name": "com.fakeui.bridge.office-macbook",
    "restart_command": "launchctl kickstart -k ..."
  }
}
```

The `agent_id` and `capabilities` fields are returned now so future C-style heartbeat and command APIs can reuse the same identity model. For this release, the local client stores them but does not send periodic heartbeats.

## Future C API Space

Reserve these endpoints for a later release:

- `POST /api/agents/{agent_id}/heartbeat`
- `GET /api/agents/{agent_id}/actions`
- `POST /api/agents/{agent_id}/action-results`

The first release should not implement remote actions, but it should avoid names and file formats that would block these endpoints later.

## Local Agent App

The local app stays bound to `127.0.0.1`. It should be a small Python app packaged with the bridge bundle so customers do not need Node or a browser framework.

Pages:

- Overview: runtime state, config state, panel pairing state, service count, public URL count.
- Services: local target, public URL, portal port, and probe result for each service.
- Setup: bootstrap from profile, manual JSON import, install or restart service.
- Logs: bridge logs and dashboard logs with copy/download controls.
- Settings: panel URL, bridge id, dashboard port, and reset pairing.

UI style:

- Reuse fake-ui color tokens and structure: pale background, white surfaces, 8px radius, restrained blue/teal accents, dense operational layout.
- Use a left side navigation on desktop and a compact top layout on small screens.
- Use status badges for `running`, `warning`, `missing config`, and `reachable`.
- Use icon-like compact controls where practical, with text labels for destructive or setup actions.

## Local Files

Paired bundles include:

- `agent-profile.json`: bootstrap metadata and short-lived token.
- `bridge-dashboard.py`: local app and API server.
- `bridge-dashboard.json`: current dashboard metadata, updated after bootstrap.
- `xray-bridge.example.json`: non-working sample config.
- `start-bridge.*`, `stop-bridge.*`, and platform install scripts.
- `README.md`: concise fallback instructions.

After bootstrap, the Agent writes:

- `xray-bridge.json`
- `bridge-dashboard.json`
- `agent-state.json`

`agent-state.json` stores non-secret durable state:

```json
{
  "schema": 1,
  "agent_id": "agent_abc123",
  "bridge_id": "office-macbook",
  "bundle_kind": "shared",
  "platform": "macos",
  "panel_url": "https://panel.example.com",
  "paired_at": "2026-06-21T00:00:00Z",
  "capabilities": ["bootstrap", "local_status"]
}
```

Do not store the raw pairing token after bootstrap succeeds.

## Security

- Pairing tokens are random, short-lived, hashed at rest, and one-time use by default.
- The local dashboard binds only to `127.0.0.1`.
- The Agent only pulls configuration from the panel. It does not expose an inbound management API.
- Manual JSON import remains available for air-gapped usage.
- The dashboard redacts UUIDs, private keys, public keys, short IDs, and pairing tokens from logs and rendered config snippets.
- Panel audit logs record token creation and bootstrap success without secrets.

## Error Handling

The local Setup page should show clear states:

- Profile missing.
- Pairing token expired.
- Panel unreachable.
- Bootstrap rejected.
- Xray missing.
- Xray config invalid.
- Service install failed.
- Local target unreachable.

Each state should include a concrete next action such as retry bootstrap, import JSON manually, install Xray, or open logs.

## Testing Strategy

Backend tests:

- Pairing token creation stores only a hash and returns the raw token once.
- Expired or reused tokens are rejected.
- Dedicated and shared bootstrap responses include the expected bridge config and metadata.
- Agent bundle contains `agent-profile.json` and dashboard assets for macOS, Linux, and Windows.
- Existing non-paired bundle endpoints still work.

Frontend tests:

- Tunnel page renders paired Agent actions for dedicated and shared bridges.
- Clicking paired Agent download calls the new endpoints.
- Existing export JSON, portal export, and apply actions still work.

Local Agent tests:

- Bootstrap client writes `xray-bridge.json`, `bridge-dashboard.json`, and `agent-state.json`.
- The raw token is removed or blanked after successful bootstrap.
- Dashboard status API reports runtime, config, services, and logs.
- Manual JSON import path still works without a panel.

Manual validation:

- Package a macOS Agent.
- Bootstrap from a local or test panel.
- Start the Agent service.
- Confirm `127.0.0.1:19090` renders the new UI.
- Confirm public HTTPS tunnel still returns HTTP 200 through the VPS.

## Acceptance Criteria

- A customer can download a paired Agent package from fake-ui and run one install command to get a working local bridge.
- The local app visually matches fake-ui and shows useful operational state without requiring shell commands.
- Existing manual config and existing tunnel bundle flows continue to work.
- No secret values are committed, logged, or displayed in the dashboard.
- The codebase has clear extension points for future heartbeat and remote action APIs.
