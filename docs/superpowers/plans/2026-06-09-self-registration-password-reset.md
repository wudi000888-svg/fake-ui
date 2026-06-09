# Self Registration And Password Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement separated login/register flows, administrator-controlled public registration, email-backed password reset, account email updates, and admin logout UI.

**Architecture:** Keep the existing native HTTP server and SQLite settings repositories. Add focused modules for public settings and email verification while routing through existing `api_*_routes.py` files.

**Tech Stack:** Python stdlib HTTP/SQLite/smtplib, native ES modules frontend, pytest.

---

### Task 1: Public Auth Flow Contract

**Files:**
- Modify: `baseline/api_public_routes.py`
- Modify: `baseline/frontend/assets/js/components/login.js`
- Modify: `baseline/frontend/assets/js/actions/handlers.js`
- Test: `tests/test_core_api.py`
- Test: `tests/test_frontend_v2_structure.py`

- [ ] Add failing tests proving `/api/register` returns no token and frontend has separate login/register forms.
- [ ] Implement register API success without session/token.
- [ ] Update frontend submit handling to redirect registration success to `/login`.

### Task 2: Email Settings And User Email

**Files:**
- Create: `baseline/email_settings.py`
- Modify: `baseline/public_settings.py`
- Modify: `baseline/api_post_routes.py`
- Modify: `baseline/api_self_routes.py`
- Modify: `baseline/dashboard_service.py`
- Modify: `baseline/frontend/assets/js/pages/admin/settings.js`
- Modify: `baseline/frontend/assets/js/pages/user/account.js`
- Test: `tests/test_core_api.py`
- Test: `tests/test_frontend_v2_structure.py`

- [ ] Add failing tests proving SMTP password is not returned and users can update email.
- [ ] Implement private email settings storage.
- [ ] Add `/api/email-settings` admin save route and `/api/self/email` user route.
- [ ] Add admin/user frontend forms.

### Task 3: Password Reset Verification

**Files:**
- Create: `baseline/email_service.py`
- Create: `baseline/password_reset_service.py`
- Modify: `baseline/api_public_routes.py`
- Modify: `baseline/registration_store.py`
- Modify: `baseline/user_admin.py`
- Modify: `baseline/frontend/assets/js/components/login.js`
- Modify: `baseline/frontend/assets/js/actions/handlers.js`
- Test: `tests/test_core_api.py`
- Test: `tests/test_frontend_v2_structure.py`

- [ ] Add failing tests proving disabled reset blocks, enabled reset sends a code, valid code resets password, invalid code increments attempts.
- [ ] Implement SMTP send adapter and test stub hook.
- [ ] Implement hashed reset code storage and verification.
- [ ] Add `/api/password-reset/send-code` and `/api/password-reset/confirm`.
- [ ] Add `/forgot` page form.

### Task 4: Logout UI And Release Notes

**Files:**
- Modify: `baseline/frontend/assets/js/components/layout.js`
- Modify: `CHANGELOG.md`
- Modify: `docs/releases/v2.1.2.md`
- Test: `tests/test_frontend_v2_structure.py`

- [ ] Add failing test for shell logout button.
- [ ] Add logout action button to topbar/side nav.
- [ ] Update release notes.

### Validation

- [ ] Run targeted tests after each task.
- [ ] Run `python3 -m pytest -q`.
- [ ] Run `python3 -m py_compile docs/demo_data.py $(find baseline -name '*.py' -type f | sort)`.
- [ ] Run `git diff --check`.
- [ ] Run `bash -n scripts/install-fresh-vps.sh`.
