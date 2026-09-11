# QR Scan Production Readiness Tracker

This document tracks issues found in the public QR scan flow. Resolve and
verify every open item before production release.

| Status | Priority | Issue | Affected area | Required resolution |
| --- | --- | --- | --- | --- |
| Done | P0 | Draft QR codes could be reached by public scan endpoints. | `Qr/normal_user/views.py` | Public identifier lookup now excludes `is_draft=True`; regression test added. |
| Open | P0 | Inactive QR codes (`status=False`) can still be scanned. | `Qr/normal_user/views.py` | Reject inactive QR codes in the shared scan eligibility check. |
| Open | P0 | Scan limits are applied only after content has already been returned, and failures are suppressed. The current check is per visitor rather than an overall QR limit. | `Qr/normal_user/views.py`, `analytics/services/tracker.py` | Enforce the agreed limit atomically before serving content. Return a deterministic limit-reached response. |
| Open | P0 | QR passwords are stored and compared as plaintext. The scan response includes the complete scan settings, including the password. | `Qr/models.py`, `Qr/serializers.py` | Store a password hash, verify it with Django's password utilities, and use a public scan response serializer that never exposes secrets. |
| Open | P1 | The public analytics endpoint bypasses schedule, password, status, and scan-limit validation, allowing metric inflation. | `Qr/normal_user/views.py` | Use one shared eligibility check for scan and tracking, then add rate limiting and abuse controls. |
| Open | P1 | `is_time_limit` and `time_limit` are configured but never enforced. | `Qr/models.py`, `Qr/normal_user/views.py` | Define the intended meaning and enforce it in the shared eligibility check. |
| Open | P1 | Public analytics processing is synchronous despite being declared as a Celery task. GeoIP lookup and aggregate writes delay the request and can be abused. | `Qr/normal_user/views.py`, `analytics/task.py` | Move non-critical tracking to a queue or make synchronous work bounded; protect the endpoint with throttling. |
| Open | P1 | Analytics errors are swallowed and callers receive success, causing silent data loss. | `analytics/services/tracker.py` | Emit observable failure metrics and choose an explicit retry/error strategy. |
| Open | P1 | Client IP headers are trusted without proxy validation, and IP/user-agent/referrer are printed to application logs. | `Qr/normal_user/views.py` | Trust forwarded headers only from the configured proxy; remove raw request-data prints and apply data-retention/privacy controls. |
| Open | P2 | Concurrent scans can race on aggregate creation and updates, producing failed or inconsistent analytics. | `analytics/models.py`, `analytics/services/*` | Use database-safe upserts/locking and load-test concurrent scans. |
| Open | P1 | There is no backend `GET` redirect handler; the repository exposes JSON `POST` scan APIs only. | `DynamicOCR/urls.py`, `Qr/normal_user/views.py` | Verify that a frontend or edge service provides direct QR resolution and redirect, or implement a dedicated public redirect endpoint. |
| Open | P1 | Deployment configuration fails Django production checks: DEBUG is enabled, hosts are unrestricted, HTTPS/HSTS and secure cookies are not enabled, and CSRF middleware is disabled. | `DynamicOCR/settings.py` | Use production-only settings and rerun `manage.py check --deploy` with production environment variables. |

## Verification baseline

- Draft QR regression: `./.venv/bin/python manage.py test Qr.tests.QRCodeListTests`
- Full scan-flow coverage still needs tests for inactive, scheduled, password-protected, rate-limited, and concurrent scans.
