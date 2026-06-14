/**
 * Inline password-reset panel, shown when ?reset_token= is in the URL.
 * Not a dialog — renders between Header and main content.
 */
import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { confirmPasswordReset } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";

interface Props {
  token: string;
  onDismiss: () => void;
  /** Called when reset opens the forgot-password dialog flow. */
  onRequestNewLink: () => void;
}

type PanelState = "form" | "success" | "error";

function passwordStrengthHint(password: string): { text: string; level: "error" | "warn" } | null {
  if (password.length === 0) return null;
  if (password.length < 10) return { text: "Must be at least 10 characters", level: "error" };
  if (/^[a-z]+$/.test(password)) return { text: "Add uppercase letters, numbers, or symbols", level: "warn" };
  return null;
}

function ShowHideInput({
  id, value, onChange, label, autoComplete,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  label: string;
  autoComplete?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="text-sm">{label}</label>
      <div className="relative mt-1">
        <Input
          id={id}
          type={show ? "text" : "password"}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          className="pr-9"
        />
        <button
          type="button"
          aria-label={show ? "Hide password" : "Show password"}
          onClick={() => setShow((s) => !s)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

export function PasswordResetPanel({ token, onDismiss, onRequestNewLink }: Props) {
  const { refresh } = useAuth();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [state, setPanelState] = useState<PanelState>("form");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const strengthHint = passwordTouched ? passwordStrengthHint(newPassword) : null;

  function describeResetError(err: unknown): string {
    if (!(err instanceof ApiError)) return "Something went wrong. Please try again.";
    try {
      const parsed = JSON.parse(err.message);
      const detail = typeof parsed.detail === "string" ? parsed.detail : null;
      if (detail === "This link has already been used") {
        return "This reset link has already been used. Request a new one.";
      }
      if (detail === "This link has expired") {
        return "This reset link has expired. Request a new one.";
      }
      if (detail === "Invalid or expired token") {
        return "This reset link is invalid. Request a new one.";
      }
      if (detail) return detail;
    } catch {
      // Not JSON
    }
    return "Something went wrong. Please try again.";
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);
    if (newPassword.length < 10) {
      setErrorText("Password must be at least 10 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorText("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await confirmPasswordReset({ token, new_password: newPassword });
      await refresh();
      setPanelState("success");
      // Auto-dismiss after a short delay.
      setTimeout(() => onDismiss(), 2500);
    } catch (err) {
      setErrorText(describeResetError(err));
      setPanelState("error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      role="region"
      aria-label="Reset your password"
      className="border-b border-border bg-muted/40 px-4 py-5 sm:px-6"
    >
      <div className="mx-auto max-w-sm">
        {state === "success" ? (
          <div role="status" className="space-y-2 text-center">
            <p className="text-sm font-semibold">Your password has been updated.</p>
            <p className="text-xs text-muted-foreground">You are now logged in.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <p className="text-sm font-semibold">Set a new password</p>
            <ShowHideInput
              id="reset-new-password"
              value={newPassword}
              onChange={(v) => { setNewPassword(v); setPasswordTouched(true); }}
              label="New password"
              autoComplete="new-password"
            />
            {strengthHint && (
              <p
                className={`text-xs ${
                  strengthHint.level === "error"
                    ? "text-destructive"
                    : "text-yellow-600 dark:text-yellow-400"
                }`}
                role="status"
                aria-live="polite"
              >
                {strengthHint.text}
              </p>
            )}
            <ShowHideInput
              id="reset-confirm-password"
              value={confirmPassword}
              onChange={setConfirmPassword}
              label="Confirm new password"
              autoComplete="new-password"
            />
            {errorText && (
              <div role="alert" className="space-y-2">
                <p className="text-xs text-destructive">{errorText}</p>
                {state === "error" && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={onRequestNewLink}
                  >
                    Request new link
                  </Button>
                )}
              </div>
            )}
            <div className="flex gap-2">
              <Button type="submit" className="flex-1" disabled={loading}>
                {loading ? "Saving..." : "Save new password"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
