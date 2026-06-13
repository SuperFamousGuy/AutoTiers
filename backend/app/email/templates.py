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
