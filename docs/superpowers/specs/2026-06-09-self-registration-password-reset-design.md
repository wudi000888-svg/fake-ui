# Self Registration And Password Reset Design

## Goal

Split login and registration into separate flows, keep public registration administrator-controlled, and add administrator-controlled email verification password reset.

## Scope

- `/login` shows only the login form.
- When `registration_enabled=true`, `/login` shows a register button linking to `/register`; when disabled it does not.
- `/register` is a separate page. Successful registration creates a no-plan user and redirects back to `/login`.
- `password_reset_enabled=false` by default. When enabled, `/login` shows a forgot-password button linking to `/forgot`.
- `/forgot` sends an email verification code and then accepts code plus new password.
- Users can add or update their email from the account page.
- Admin settings include public registration, password reset, and SMTP email provider settings.
- Admin responses never return SMTP password values.
- Admin and user shells include a logout button.

## Data Model

`public_settings` remains the public feature flag settings record:

- `registration_enabled`
- `password_reset_enabled`
- `email_provider`
- `smtp_configured`

Email provider secrets are stored in a separate private settings record:

- `email_provider_settings`
- `smtp_host`
- `smtp_port`
- `smtp_username`
- `smtp_password`
- `smtp_from`
- `smtp_tls`

Users store `email` in their SQLite user JSON.

Password reset verification records use the existing `password_resets` table. The record stores username, email, hashed code, expiry, attempts, and status. It never stores the plaintext code.

## Behavior

Registration:

1. User opens `/register`.
2. If registration is disabled, the page shows unavailable state and `/api/register` returns `403`.
3. If enabled, user submits username, password, and optional email.
4. Backend creates a no-plan user with `plan_id=""`, `node_groups=[]`, `node_ids=[]`, `quota_bytes=0`, and `expires_at=""`.
5. API returns success without session/token so the frontend redirects to `/login`.

Password reset:

1. User opens `/forgot`.
2. If password reset is disabled, the page shows unavailable state and API returns `403`.
3. User submits username or email.
4. Backend finds exactly one user with an email, generates a six-digit code, stores only its hash, and sends via SMTP.
5. User submits username/email, code, and new password.
6. Backend validates TTL and attempts, updates the user password, marks the reset consumed, and returns success.

Email configuration:

Admin can save SMTP settings. Blank SMTP password means keep existing password. API responses include `smtp_configured` but never `smtp_password`.

## Tests

- Public registration returns no token and creates no-plan user.
- Login page register/forgot links render only when enabled.
- User account can update email.
- Password reset disabled blocks request.
- Password reset stores hashed code, sends email through provider adapter, and resets password with valid code.
- Invalid code increments attempts and fails.
- Admin email settings do not leak SMTP password.
- Admin shell exposes logout button.
