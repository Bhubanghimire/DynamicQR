# Shared Project QR Account Attribution Review and Implementation Plan

## Executive summary

The project-sharing feature exists, but account-level QR attribution is incomplete.

Confirmed current behavior:

- Project invitations and role-based access are implemented.
- Invited users with `Admin` or `Edit` roles can create QRs inside the owner's project.
- QR creation and quota checks still use the invited user's account.
- Subscription usage counts QRs by `QRCode.created_by`.
- Bulk imports, duplicate operations, scan quotas, and dashboards repeat the same assumption.

This document is a review and implementation plan only. No application changes or migrations are included.

## Required ownership rule

Use one explicit invariant:

```text
QR account owner =
    project.owner       when the QR belongs to a project
    QR.created_by       when the QR does not belong to a project
```

`created_by` should continue to mean the person who created the QR. It should not be overwritten with the project owner because creator identity is useful for auditing.

| Operation | Creator | QR project | Account charged |
|---|---|---|---|
| Owner creates personal QR | Owner | None | Owner |
| Invited user creates personal QR | Invited user | None | Invited user |
| Invited editor creates QR inside owner project | Invited user | Owner's project | Project owner |
| Owner creates QR inside own project | Owner | Owner's project | Owner |
| Personal QR is attached to another owner's project | Original creator | Owner's project | Project owner |
| QR is removed from a project | Original creator | None | Original creator |

This approach does not require a new ownership column. Existing project relationships can determine the billed account dynamically.

## What is already implemented correctly

### Project ownership

`Qr/models.py:14` has a clear `Project.owner` relationship.

### Invitations and membership

- Invitations reference projects through content types.
- Accepted invitations create `SharePermissions` records.
- Acceptance is transactional and locks the invitation row in `Qr/normal_user/views.py:1667`.
- Email identity is verified before acceptance.
- Duplicate active membership is rejected.

### Project roles

`Qr/access.py:9` defines the Owner, Admin, Edit, and View roles.

`Qr/serializers.py:72` prevents View members from creating QRs in a project.

### Shared-project visibility

Project and QR querysets include accepted shared projects:

- `Qr/normal_user/views.py:432` — project queryset
- `Qr/normal_user/views.py:571` — project QR listing
- `Qr/normal_user/views.py:703` — accessible QR queryset

These behaviors should be preserved.

## Confirmed implementation gaps

### 1. Normal QR creation checks the invited user's subscription

`Qr/normal_user/views.py:801` calls `_enforce_qr_limit(request.user)`.

The helper at `Qr/normal_user/views.py:73` counts `QRCode.objects.filter(created_by=user)`. Therefore, an editor creating a QR inside another person's project consumes the editor's quota.

The serializer assigns `created_by=request.user` through the hidden field at `Qr/serializers.py:62`. Keeping the creator is correct, but billing and quota attribution must be resolved separately.

### 2. QR duplication has the same problem

`Qr/normal_user/views.py:1008` checks `request.user` even when the source QR belongs to a shared project.

`Qr/serializers.py:374` creates the duplicate with the requesting user as `created_by`. The creator attribution is acceptable, but the quota account should be the source project's owner.

### 3. Bulk import uses the invited member's limits

Bulk import currently:

- checks `get_bulk_upload_limit(request.user)`;
- checks QR capacity with `_enforce_qr_limit(request.user)`;
- stores `QRImportJob.user=request.user`;
- rechecks the worker against `import_job.user`;
- creates every imported QR with `created_by=job.user`.

Relevant locations:

- `Qr/normal_user/views.py:2053` — bulk-import endpoint
- `Qr/normal_user/views.py:2099` — request-side QR check
- `Qr/tasks.py:126` — worker-side entitlement and limit checks
- `Qr/importers/website.py:28` and the other importer modules — QR creation

For project imports, entitlements and QR usage should come from `project.owner`; `QRImportJob.user` should remain the initiating actor.

### 4. Subscription usage counts only `created_by`

`subscriptions/normal_user/views.py:322` builds QR and scan usage from `QRCode.objects.filter(created_by=user)`.

Consequences:

- The invited member is charged for QRs created inside another person's project.
- The project owner does not see those QRs in subscription usage.
- Scan totals are attributed to the wrong subscription account.

### 5. Package scan quota uses `created_by`

`subscriptions/usage.py:17` totals scans using `qr__created_by=user`.

`analytics/services/tracker.py:58` locks `qr.created_by` before enforcing the package scan quota. Scans of member-created project QRs therefore consume the member's allowance instead of the project owner's allowance.

### 6. Project QR permission treats the creator as an owner

`Qr/access.py:38` returns `owner` whenever `qr.created_by_id == user.id`.

For a project QR created by an invited editor, this can elevate that editor from `Edit` to QR owner. Project QR authority should instead be determined by the project role:

```text
project owner -> owner
project Admin -> admin
project Edit  -> edit
project View  -> view
```

Creator ownership should apply only to individual QRs.

### 7. Attaching and removing QRs does not reevaluate quota

`Qr/normal_user/views.py:510` changes only `qr.project`.

This permits the following inconsistencies:

- A personal QR can be attached to an owner's project without checking the owner's available capacity.
- A QR can be removed from a project even if its creator's personal account is already at its QR limit.
- Moving a QR between projects can transfer usage without checking the destination owner.

### 8. QR-limit enforcement is race-prone

The application counts QRs and creates the next QR in separate database operations. Two invited members can both see one remaining slot and both create a QR.

This already affects individual accounts, but shared projects make it substantially easier to trigger.

### 9. Team-member limits are reported but not enforced

Subscriptions contain `team_member_limit`, and `subscriptions/normal_user/views.py:436` reports accepted unique members. Neither invitation creation nor invitation acceptance currently enforces that limit.

This is related to shared-account behavior and should be addressed as part of the same account-ownership boundary.

## Proposed design

### 1. Introduce a central account-attribution service

Create a focused module such as `Qr/services/account_ownership.py`.

Responsibilities:

```python
def account_owner_for_project(project, actor):
    return project.owner if project else actor


def account_owner_for_qr(qr):
    return qr.project.owner if qr.project_id else qr.created_by


def qrs_billed_to(user):
    return QRCode.objects.filter(
        Q(project__owner=user)
        | Q(project__isnull=True, created_by=user)
    )
```

All subscription and quota code should use these helpers instead of duplicating the ownership expression.

### 2. Keep creator and account owner conceptually separate

No model change is needed initially:

- `QRCode.created_by`: person who performed the creation
- `QRCode.project.owner`: subscription/account owner for project QRs
- No project: creator is also the account owner

Administrative APIs can expose both concepts as read-only information if needed.

### 3. Centralize quota enforcement

Create a service such as `subscriptions/quota_service.py` with operations equivalent to:

```python
resolve_qr_account_owner(actor, project=None, qr=None)
get_qr_usage(account_owner)
check_qr_capacity(account_owner, requested=1)
get_scan_usage(account_owner)
check_scan_capacity(account_owner)
```

For project-scoped actions, resolve and lock the project owner before checking quota.

### 4. Make single-QR creation atomic

For normal creation and duplication:

1. Validate project access.
2. Resolve the account owner.
3. Begin a database transaction.
4. Lock the account owner or active subscription with `select_for_update()`.
5. Recalculate current usage.
6. Reject if the operation exceeds the owner's limit.
7. Create the QR with `created_by=request.user`.
8. Commit.

This prevents simultaneous members from exceeding the shared quota.

### 5. Correct bulk-import attribution

For project imports:

- `QRImportJob.user` remains the initiating member.
- `project.owner` supplies QR and bulk-import entitlements.
- Imported QRs retain `created_by=job.user`.
- The worker re-resolves the owner from the project rather than trusting client data.

Bulk imports should reserve capacity transactionally because a long-running import should not hold a database lock for the entire workbook.

Recommended reservation behavior:

- Reserve requested QR slots when the job is accepted.
- Include active reservations when checking available capacity.
- Release unused slots when rows fail or the job terminates.
- Expire abandoned reservations safely.

A smaller first implementation can recheck in the worker, but competing jobs may both pass the API check before one later fails.

### 6. Update project attachment operations

For `add-qr`:

- Resolve the destination project owner.
- Check and lock the destination owner's quota.
- Attach only if capacity is available.
- If moving from another project, calculate both source and destination accounts.

For `remove-qr`:

- Resolve the original creator as the new personal account owner.
- Check the creator's personal quota before detaching.
- Reject detachment if it would exceed their limit.

### 7. Correct role calculation

Change `qr_role()` conceptually to:

```python
if qr.project_id:
    inherited_role = project_role(user, qr.project)
    direct_role = direct_qr_share_role(user, qr)
    return strongest(inherited_role, direct_role)

if qr.created_by_id == user.id:
    return "owner"

return direct_qr_share_role(user, qr)
```

An invited creator should not gain permanent owner privileges over a project asset merely because they created it.

### 8. Update usage and scan paths

Use `qrs_billed_to(user)` for:

- subscription QR usage;
- subscription scan usage;
- scan quota calculation;
- owner analytics dashboards;
- weekly account-level performance summaries, if those summaries are intended for the billed account.

Use `account_owner_for_qr(qr)` when:

- locking the account during a scan;
- finding the subscription whose scan limit applies;
- building package-limit error responses.

Notifications require a separate product decision: alerts could go to the creator, the project owner, or configured project recipients. They should not change automatically merely because billing attribution changes.

## Test plan

### Shared-project creation

- Editor creates a QR in the owner's project.
- `created_by` remains the editor.
- Owner QR usage increases.
- Editor personal QR usage does not increase.
- Owner's QR limit controls success or rejection.

### Individual creation

- Editor creates a QR with no project.
- Editor usage increases.
- Owner usage remains unchanged.

### Permission regression

- View member cannot create.
- Edit member can create but does not gain owner/delete permissions.
- Admin retains permitted management operations.
- Project owner retains full access.

### Quota boundaries

- Owner with zero remaining slots rejects member creation.
- Member's own available quota does not bypass owner exhaustion.
- Owner capacity permits member creation even if the member's personal quota is exhausted.
- Two concurrent members cannot exceed the owner limit.

### Duplication

- Duplicating a shared-project QR charges the project owner.
- Duplicating a personal QR charges the requester.
- Owner exhaustion blocks project duplication.

### Bulk import

- Project import uses owner QR and bulk limits.
- Personal import uses initiating user limits.
- Worker rechecks ownership and capacity.
- Competing imports cannot exceed owner capacity.
- Failed rows release reserved capacity.

### Project movement

- Attaching a personal QR transfers usage to the project owner.
- Detaching transfers usage back to the creator.
- Moving between projects transfers usage between owners.
- Destination capacity is enforced atomically.

### Scan quota

- Scans of member-created project QRs count against the owner.
- Member personal QR scans count against the member.
- Concurrent scans cannot exceed the account limit.

### Usage API

- Owner usage includes every QR in owned projects regardless of creator.
- Owner usage also includes personal QRs.
- Member usage excludes QRs they created inside another owner's project.
- Soft-deleted QRs remain excluded, preserving current behavior.

### Team-member limit

- Invitations or acceptance cannot exceed the owner's unique-member limit.
- Pending invitations cannot be used to oversubscribe.
- Inviting one person to multiple owner projects follows the existing unique-person usage definition.

## Recommended implementation sequence

1. Add failing regression tests defining shared-project attribution.
2. Introduce account-owner and billed-queryset helpers.
3. Update normal QR creation and duplication with atomic owner quota checks.
4. Correct `qr_role()` so project roles govern project QRs.
5. Update subscription usage and scan quota calculations.
6. Update bulk-import entitlement resolution and reservation handling.
7. Add quota-aware attach, detach, and cross-project movement.
8. Review analytics and notification semantics separately.
9. Enforce the existing team-member subscription limit.
10. Audit existing production data before enabling strict enforcement.

## Deployment and compatibility risk

When corrected queries are enabled, existing project QRs created by invited members will immediately shift into project-owner usage. Some owners may already exceed their package limits.

Before enabling strict enforcement:

- Calculate current usage under both the old and proposed rules.
- Report affected owners without changing records.
- Preserve all existing QRs.
- Block only new creation for over-limit accounts unless the product explicitly chooses a different policy.

## Implementation decision required

The proposed plan assumes that moving a QR into or out of a project dynamically transfers which subscription is charged. This follows the rule that project QRs belong to the project owner's account and individual QRs belong to their creator's account.

Implementation should begin only after this ownership invariant is approved.
