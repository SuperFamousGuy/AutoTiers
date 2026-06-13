/**
 * Dismissible email-verification banner.
 * Shown when user.email_verified === false and session hasn't dismissed it.
 *
 * Session-storage key: "email_verified_banner_dismissed"
 */
import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { resendVerificationEmail } from "@/api/auth";
import { ApiError } from "@/api/client";

interface Props {
  email: string;
  onDismiss: () => void;
}

type BannerState = "default" | "sending" | "sent" | "rate_limited";

export function EmailVerificationBanner({ email, onDismiss }: Props) {
  const [bannerState, setBannerState] = useState<BannerState>("default");

  async function handleResend() {
    setBannerState("sending");
    try {
      await resendVerificationEmail();
      setBannerState("sent");
      // Banner auto-dismisses after 3s on success.
      setTimeout(() => onDismiss(), 3000);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setBannerState("rate_limited");
      } else {
        // On generic error, revert to default so the user can try again.
        setBannerState("default");
      }
    }
  }

  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 border-b border-yellow-300 bg-yellow-50 px-4 py-2.5 text-yellow-900 dark:border-yellow-700/60 dark:bg-yellow-950/40 dark:text-yellow-200"
    >
      <div className="min-w-0 flex-1 text-xs">
        {bannerState === "sent" ? (
          <span>Verification email sent. Check your inbox.</span>
        ) : bannerState === "rate_limited" ? (
          <span>Please wait a minute before requesting another verification email.</span>
        ) : (
          <span>
            Please verify your email. We sent a link to{" "}
            <strong className="font-medium">{email}</strong>.
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {(bannerState === "default" || bannerState === "sending") && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-xs text-yellow-900 hover:bg-yellow-100 hover:text-yellow-900 dark:text-yellow-200 dark:hover:bg-yellow-900/30"
            onClick={handleResend}
            disabled={bannerState === "sending"}
          >
            {bannerState === "sending" ? "Sending..." : "Resend"}
          </Button>
        )}
        <button
          type="button"
          aria-label="Dismiss email verification banner"
          onClick={onDismiss}
          className="ml-1 rounded-sm opacity-70 hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

const SESSION_KEY = "email_verified_banner_dismissed";

export function shouldShowVerificationBanner(): boolean {
  try {
    return sessionStorage.getItem(SESSION_KEY) !== "1";
  } catch {
    return false;
  }
}

export function dismissVerificationBanner(): void {
  try {
    sessionStorage.setItem(SESSION_KEY, "1");
  } catch {
    // sessionStorage unavailable — ignore
  }
}
