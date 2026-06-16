"""Email template builders for each transactional email type.

Each function returns a (html, text) tuple. Templates are plain f-strings
with minimal inline styling — no external template engine dependency.
"""


def reset_password_email(reset_url: str) -> tuple[str, str]:
    """Build the password-reset email body.

    Parameters
    ----------
    reset_url:
        The full URL the user should visit to reset their password.
        Example: https://app.autotiers.com?reset_token=<token>

    Returns
    -------
    (html, text) tuple
    """
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #111;">
  <h2 style="margin-bottom: 8px;">Reset your AutoTiers password</h2>
  <p>We received a request to reset the password for your account. Click the button below to choose a new password.</p>
  <p style="margin: 24px 0;">
    <a href="{reset_url}"
       style="background-color: #2563eb; color: #fff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600;">
      Reset password
    </a>
  </p>
  <p style="color: #555; font-size: 14px;">This link expires in 1 hour. If you didn't request a password reset, you can safely ignore this email — your password won't change.</p>
  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
  <p style="color: #888; font-size: 12px;">AutoTiers &mdash; Fantasy Football Tiers</p>
</body>
</html>"""

    text = f"""Reset your AutoTiers password

We received a request to reset the password for your account.

Click the link below to choose a new password:
{reset_url}

This link expires in 1 hour.

If you didn't request a password reset, you can safely ignore this email — your password won't change.

— AutoTiers
"""
    return html, text


def verify_email_email(verify_url: str) -> tuple[str, str]:
    """Build the email-verification email body.

    Parameters
    ----------
    verify_url:
        The full URL the user should visit to verify their email address.
        Example: https://app.autotiers.com?verify_token=<token>

    Returns
    -------
    (html, text) tuple
    """
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #111;">
  <h2 style="margin-bottom: 8px;">Verify your AutoTiers email</h2>
  <p>Thanks for signing up! Please verify your email address by clicking the button below.</p>
  <p style="margin: 24px 0;">
    <a href="{verify_url}"
       style="background-color: #2563eb; color: #fff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600;">
      Verify email
    </a>
  </p>
  <p style="color: #555; font-size: 14px;">This link expires in 72 hours. If you didn't create an AutoTiers account, you can safely ignore this email.</p>
  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
  <p style="color: #888; font-size: 12px;">AutoTiers &mdash; Fantasy Football Tiers</p>
</body>
</html>"""

    text = f"""Verify your AutoTiers email

Thanks for signing up! Please verify your email address by clicking the link below:
{verify_url}

This link expires in 72 hours.

If you didn't create an AutoTiers account, you can safely ignore this email.

— AutoTiers
"""
    return html, text


def feedback_email(
    message: str,
    sender_email: str | None,
    category_label: str | None = None,
) -> tuple[str, str]:
    """Build the team-inbox email for an in-app feedback submission.

    Parameters
    ----------
    message:
        The user's free-text feedback. Treated as untrusted: HTML-escaped in the
        HTML body so a message cannot inject markup into the team's inbox.
    sender_email:
        The authenticated submitter's email, or None for anonymous submissions.
    category_label:
        Human-readable category label ("Bug", "Idea", "Other"). When provided it
        is rendered as a "Type:" line in both bodies. Optional so callers that
        predate the category field (and old clients) still produce a valid email.

    Returns
    -------
    (html, text) tuple
    """
    from datetime import datetime, timezone
    from html import escape

    who = sender_email or "anonymous (not logged in / no email on file)"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_message = escape(message)

    # The label comes from a fixed server-side enum map (never user free-text),
    # so it is safe; escape it anyway as defence in depth.
    type_html = (
        f'  <p style="color: #555; font-size: 14px; margin: 0 0 16px;">'
        f"<strong>Type:</strong> {escape(category_label)}</p>\n"
        if category_label
        else ""
    )
    type_text = f"Type: {category_label}\n" if category_label else ""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #111;">
  <h2 style="margin-bottom: 8px;">New AutoTiers feedback</h2>
  <p style="color: #555; font-size: 14px; margin: 0;"><strong>From:</strong> {escape(who)}</p>
  <p style="color: #555; font-size: 14px; margin: 0;"><strong>Submitted:</strong> {when}</p>
{type_html}  <div style="white-space: pre-wrap; border-left: 3px solid #2563eb; padding: 8px 12px; background: #f8fafc;">{safe_message}</div>
  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
  <p style="color: #888; font-size: 12px;">AutoTiers &mdash; in-app feedback</p>
</body>
</html>"""

    text = f"""New AutoTiers feedback

From: {who}
Submitted: {when}
{type_text}
{message}

— AutoTiers in-app feedback
"""
    return html, text
