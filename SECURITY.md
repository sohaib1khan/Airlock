# Security Policy

## Supported Versions

This project is pre-1.0 and actively evolving. Security fixes are applied to the latest mainline code.

## Reporting a Vulnerability

- Do not open a public issue for suspected vulnerabilities.
- Send details privately to the repository maintainer with:
  - impact summary
  - reproduction steps
  - affected commit/version (if known)
  - suggested fix (optional)

If contact details are not published yet, use a temporary private channel and request a disclosure contact.

## Threat Model (Current)

Airlock is a self-hosted workspace platform with high-value authentication/session surfaces.

Primary trust boundaries:

- Browser client <-> API boundary (auth/session control).
- API <-> container runtime boundary (Docker control + file operations).
- Public network <-> private internal Docker network.

Key assets:

- User credentials and second factors (2FA).
- Access/refresh/session tickets.
- Workspace container state and file contents.
- Audit event history.

Primary risks addressed:

- Credential stuffing/brute force on login and 2FA endpoints.
- Session hijacking (refresh token theft, stale session tickets).
- Privilege escalation from limited scope to full scope.
- File path traversal in session file APIs.
- Accidental container network exposure.

Controls implemented:

- Argon2 password hashing.
- JWT scope separation (`limited`/`full`) and short-lived connect tokens.
- HttpOnly, SameSite-strict refresh/session cookies.
- Rate limiting on auth/setup/2FA flows.
- Audit event logging for security-sensitive actions.
- Container network isolation defaults with explicit attach flow.
- Workspace file path normalization and bounds checks.

## Secure Deployment Guidance

- Run behind TLS only (HTTPS/WSS in production).
- Set `COOKIE_SECURE=true` and correct `SESSION_COOKIE_DOMAIN`.
- Set strict `ALLOWED_ORIGINS` and `FRONTEND_URL`.
- Rotate `JWT_SECRET` and `SESSION_SECRET` before production.
- Restrict Docker socket access to trusted runtime contexts only.
- Apply reverse-proxy security headers (see `deploy/nginx/airlock.conf`).

## Security Testing Checklist

- Run dependency audits (`pip audit`, `npm audit`).
- Run container image scanning for base/workspace images.
- Validate OWASP Top 10 controls for auth/session/file endpoints.
- Verify no secrets in repo history or committed files.
