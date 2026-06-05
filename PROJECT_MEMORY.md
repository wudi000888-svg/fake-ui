# Project Memory

This file is a public-safe handoff note for future development sessions. It keeps project context without storing live secrets, real user data, private keys, subscription tokens, or production passwords.

## Project Identity

| Item | Value |
|---|---|
| Short name | `fake-ui` |
| Current public version | `v2.0.1` |
| Chinese positioning | 单机多出口代理编排系统 |
| Core idea | Use one VPS as a stable entry point, then orchestrate multiple VLESS/Hysteria2 nodes with independently controlled direct, HTTP, or SOCKS5 exits. |
| Main pain point | Users want multiple high-quality regional exits without buying and maintaining one VPS per region. |
| Target users | Personal developers, small self-hosted teams, cost-sensitive multi-exit proxy experiments. |

## Differentiation

| Compared With | fake-ui Focus |
|---|---|
| General airport panels | Smaller scope, single-VPS multi-exit orchestration. |
| 3x-ui-like panels | More opinionated around per-node upstream exit control and subscription naming sync. |
| Manual proxy setup | Centralized users, subscriptions, quotas, expiry, node naming, and deployment scripts. |

## Current Capabilities

| Area | Status |
|---|---|
| VLESS Reality | Supported. Multiple default VLESS nodes can be managed. |
| Per-node exit | Supported for direct, HTTP upstream, and SOCKS5 upstream. |
| Exit naming | Exit IP/country can be detected and synchronized to node names/subscriptions. |
| Hysteria2 | Supported and kept independent from VLESS orchestration. |
| Subscriptions | base64, raw URI, Mihomo/Clash.Meta. |
| Users | Create, disable, renew, quota, expiry, reset subscription. |
| Operations | Plans, orders, registrations, password reset requests, audit logs. |
| Payments | USD-priced crypto payments with receive-only admin addresses, QR codes, automatic EVM/BTC verification, TXID fallback, and order activation. |
| Payment resilience | Public RPC fallback, EVM log range splitting, payment-time scan narrowing, and minimum safe scan windows for BSC/ETH. |
| Deployment | Docker Compose, native Nginx coexistence, SNI split, self-signed cert fallback, certificate renewal mode. |
| Windows deploy | `scripts/deploy-compose-windows.ps1` packages local HEAD, uploads safely over SSH, runs local/remote tests, backs up, rebuilds, and checks panel health. |
| Storage | SQLite by default in v2.0.0, with JSON import/export compatibility under runtime `data/`. |

## Important Design Rules

| Rule | Reason |
|---|---|
| Keep runtime data out of Git | Avoid leaking users, tokens, certificates, proxy credentials, and private keys. |
| Validate generated Xray/Hysteria2 configs before applying | Prevent broken configs from disconnecting live nodes. |
| Back up before risky operations | Deployment, cert changes, and config rewrites must be recoverable. |
| Keep Hysteria2 and VLESS logic separated | Reduces cross-protocol regression risk. |
| Preserve native Nginx compatibility | Some VPS users already run Nginx on TCP 80/443. |
| Keep installer beginner-friendly | DNS, port, Docker, Nginx, and certificate failures should produce actionable messages. |

## Public Handoff Prompt

Use this prompt when starting a new Codex conversation:

```text
Please continue development of fake-ui.

Repository:
https://github.com/wudi000888-svg/fake-ui

Project positioning:
fake-ui / 单机多出口代理编排系统.
It solves the problem of using one VPS as a stable entry point while orchestrating multiple independently controlled regional exits through direct, HTTP upstream, or SOCKS5 upstream modes.

Current state:
- VLESS Reality and Hysteria2 are supported.
- Multiple default VLESS nodes can be added/deleted and synchronized into user subscriptions.
- Each VLESS node can independently use direct, HTTP upstream, or SOCKS5 upstream exits.
- Exit IP/country naming can be synchronized to node names and subscriptions.
- Users, plans, orders, registrations, subscriptions, quota, expiry, audit logs, and backups exist.
- v2.0.1 includes mobile-first modular frontend, visible panel version, SQLite default storage, TTL cache, cryptocurrency payments, restored Hysteria2 management, immediate node exit sync after save/refresh, refreshed GitHub screenshots, and CI/test fixture isolation.
- Docker Compose deployment, native Nginx coexistence, SNI split, self-signed certificate fallback, and --renew-cert are supported.

Development workflow:
- Answer in Chinese.
- Do not break existing core functionality.
- Do local tests first, then VPS preflight tests before deployment.
- Back up before risky operations.
- Roll back if deployment health checks fail.
- Never commit live data, passwords, tokens, certificates, private keys, or proxy credentials.

Recommended next version:
v2.0.1 focused on upgrade/install polish:
1. UPGRADE.md
2. scripts/upgrade.sh
3. installer preflight report
4. node exit quality checks
5. README first-screen polish
```

## Private Notes

Do not put these in Git:

| Secret / Runtime Item | Where It Belongs |
|---|---|
| Production VPS IP/domain | Private notebook or deployment environment |
| Admin password | Server-side `data/DEPLOY-SECRETS.txt` only |
| Subscription token | Runtime `data/` only |
| TLS private key/cert | Runtime `data/letsencrypt/` only |
| Xray Reality private key | Runtime config/secrets only |
| Upstream proxy username/password | Runtime node config only |
