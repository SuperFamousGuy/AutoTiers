# Runbook: Provision AWS SES for transactional auth email

Closes the ops side of [#244](https://github.com/SuperFamousGuy/AutoTiers/issues/244).
Brings password-reset and email-verification emails (shipped in #87 / PR #240,
defaulting to the in-process `fake` sender) online via AWS SES.

The Terraform (`infra/ses.tf`, `infra/iam.tf`, `infra/ecs.tf`) does everything
that can be expressed as code. The steps below are the parts that require a
human with AWS console / DNS / support access — Terraform cannot do them.

## DNS mode — IMPORTANT

`auto-tiers.com` DNS is **not** in Route 53 in this account (verified: the account
has zero hosted zones). So the default is **`manage_dns = false`** — Terraform
creates the SES identity but you add the DNS records manually at your real
provider (registrar/Cloudflare/wherever). Only set `manage_dns = true` if you
later migrate the zone into this account's Route 53.

## What the Terraform does

- Creates the apex domain `auto-tiers.com` as an SES identity, with Easy DKIM,
  and a custom MAIL FROM domain (`bounce.auto-tiers.com`).
- `manage_dns = true`: publishes the verification TXT + 3 DKIM CNAMEs + MAIL FROM
  MX/SPF to Route 53 and waits for verification during `apply`.
- `manage_dns = false` (default): emits those records via the
  `ses_dns_records_for_manual_entry` output for you to add manually; SES verifies
  asynchronously once they propagate.
- Creates an SNS topic for bounce/complaint notifications and wires it to the
  identity (optionally subscribes `var.ses_ops_email`).
- Grants the ECS task role `ses:SendEmail` / `ses:SendRawEmail`, scoped to the
  identity and pinned to the `noreply@auto-tiers.com` from-address.
- Passes `SES_FROM_ADDRESS` and `SES_REGION` to the backend container, and
  `EMAIL_SENDER_BACKEND` gated on `var.enable_ses`.

## Configurable knobs (`terraform.tfvars`)

| Variable | Default | Notes |
|----------|---------|-------|
| `ses_domain` | `auto-tiers.com` | Apex sending domain. |
| `manage_dns` | `false` | `true` only if the zone is in this account's Route 53. Default `false` = external DNS, add records manually. |
| `ses_route53_zone_name` | `auto-tiers.com` | Hosted zone that owns the records (only used when `manage_dns = true`). |
| `ses_from_email` | `noreply@auto-tiers.com` | Bare from-address; pinned in IAM. |
| `ses_from_display_name` | `AutoTiers` | From-header display name. |
| `ses_mail_from_subdomain` | `bounce` | → `bounce.auto-tiers.com`. |
| `enable_ses` | `false` | Flip to `true` to send for real. Keep `false` until verified + out of sandbox. |
| `ses_ops_email` | `""` | Email subscribed to bounce/complaint SNS. |

## Procedure

### 0. Heads-up: unrelated ALB/HTTPS drift in state

The local Terraform state is behind `main`: an unrelated, unshipped HTTPS rollout
(commit `60f07b6`) means a plain `terraform apply` also wants to **replace the
production ALB security group** (its description changed to add HTTPS — an
immutable attribute). That's a separate, deliberate action — do NOT let it ride
along with SES. Until that drift is reconciled, apply SES with **`-target`** so
only the SES/IAM/SNS resources change (commands below).

### 1. Apply the identity (external DNS; leave `enable_ses = false`)

```bash
cd infra
# Targeted plan — only the SES/IAM/SNS resources, avoiding the ALB-SG drift.
terraform plan -out=ses.tfplan \
  -target=aws_ses_domain_identity.main \
  -target=aws_ses_domain_dkim.main \
  -target=aws_ses_domain_mail_from.main \
  -target=aws_sns_topic.ses_notifications \
  -target=aws_sns_topic_policy.ses_notifications \
  -target=aws_ses_identity_notification_topic.bounce \
  -target=aws_ses_identity_notification_topic.complaint \
  -target=aws_iam_role.ecs_scheduler_task \
  -target=aws_iam_role_policy.ecs_task_ses
terraform apply ses.tfplan
```

The app stays on the `fake` sender (`enable_ses = false`) — no behavior change.

Then publish DNS so SES can verify the domain:

```bash
terraform output -json ses_dns_records_for_manual_entry
```

Add every emitted record (1 verification TXT, 3 DKIM CNAMEs, 1 MAIL FROM MX,
1 MAIL FROM SPF TXT) at your DNS provider. SES verifies asynchronously — watch
**SES → Verified identities → auto-tiers.com** until status is *Verified* and
DKIM is *Successful* (minutes to a couple hours depending on TTL/propagation).

### 2. Exit the SES sandbox  *(manual — AWS support request)*

A new SES account can only send to *verified* recipients until you request
production access. Terraform cannot do this.

- Console → **Amazon SES → Account dashboard → Request production access**.
- Provide use case (transactional: password reset + email verification), expected
  volume, and your bounce/complaint handling (point at the SNS topic from
  `terraform output ses_notifications_topic_arn`).
- Approval is typically < 24h.

Until this is granted, you can still smoke-test by verifying your own test
recipient address in the SES console.

### 3. Subscribe to bounce/complaint alerts *(optional but recommended)*

Set `ses_ops_email = "ops@…"` in `terraform.tfvars` and `apply`, then click the
confirmation link AWS emails to that address. (Or subscribe Slack/PagerDuty to
the SNS topic manually.)

### 4. Flip the switch and redeploy

```bash
# terraform.tfvars
enable_ses = true
```

```bash
terraform apply   # updates the backend task definition to EMAIL_SENDER_BACKEND=ses
```

Because the ECS service has `ignore_changes = [task_definition]`, force a new
deployment so the new task def revision is picked up:

```bash
aws ecs update-service \
  --cluster autotiers-prod \
  --service autotiers-prod-backend \
  --force-new-deployment
```

> The backend image must already include the #240 SES code (it does on `main`).
> If `enable_ses=true` is applied before the image with SES support is deployed,
> the running container ignores the unknown env var and keeps using `fake` — no
> crash, just no real sends until the image catches up.

### 5. Smoke test

1. Trigger a real password reset for a recipient you control (a verified address
   if still in sandbox).
2. Confirm the email arrives, the reset link works, and `email_verified` flips.
3. Check CloudWatch logs for the backend service — a failed SES send is logged
   (the background task swallows the exception so the HTTP response is unaffected),
   so absence of `ses` errors + an arriving email = success.

## Rollback

Set `enable_ses = false` and `terraform apply` + force a new deployment. The app
reverts to the in-process `fake` sender immediately; the SES identity, DNS, and
IAM remain in place (harmless) for the next attempt.
