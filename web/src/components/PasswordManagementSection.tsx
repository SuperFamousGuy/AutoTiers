/**
 * Password management section inside LinkedAccountsDialog.
 *
 * Shows:
 *  - "Change password" (expanded form) when user.has_password === true
 *  - "Set password" (expanded form) when user.has_password === false && user.email !== null
 *  - Hidden entirely when user.has_password === false && user.email === null
 */
import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { changePassword, setPassword } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { User } from "@/api/types";

interface Props {
  user: User;
  onRefresh: () => Promise<void>;
}

type FormState = "collapsed" | "expanded" | "saving";

function formatLastChanged(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  const now = Date.now();
  const diffMs = now - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 30) return `${diffDays} days ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths === 1) return "1 month ago";
  if (diffMonths < 12) return `${diffMonths} months ago`;
  const diffYears = Math.floor(diffDays / 365);
  return diffYears === 1 ? "1 year ago" : `${diffYears} years ago`;
}

function passwordStrengthHint(password: string): { text: string; level: "error" | "warn" } | null {
  if (password.length === 0) return null;
  if (password.length < 10) return { text: "Must be at least 10 characters", level: "error" };
  if (/^[a-z]+$/.test(password)) return { text: "Add uppercase letters, numbers, or symbols", level: "warn" };
  return null;
}

function ShowHideInput({
  id, value, onChange, label, autoComplete, required,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  label: string;
  autoComplete?: string;
  required?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="text-xs text-muted-foreground">{label}</label>
      <div className="relative mt-0.5">
        <Input
          id={id}
          type={show ? "text" : "password"}
          required={required}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          className="h-8 pr-9 text-xs"
        />
        <button
          type="button"
          aria-label={show ? "Hide password" : "Show password"}
          onClick={() => setShow((s) => !s)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>
      </div>
    </div>
  );
}

function describePasswordError(err: unknown): string {
  if (!(err instanceof ApiError)) return "Something went wrong. Please try again.";
  try {
    const parsed = JSON.parse(err.message);
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Not JSON
  }
  return err.message || "Something went wrong. Please try again.";
}

// ---------------------------------------------------------------------------
// Change-password form
// ---------------------------------------------------------------------------

function ChangePasswordForm({
  onSuccess,
  onCancel,
}: {
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [newPwTouched, setNewPwTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const strengthHint = newPwTouched ? passwordStrengthHint(newPw) : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPw !== confirmPw) {
      setError("Passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      await changePassword({ current_password: currentPw, new_password: newPw });
      onSuccess();
    } catch (err) {
      setError(describePasswordError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mt-2 space-y-2">
      <ShowHideInput
        id="change-current-password"
        value={currentPw}
        onChange={setCurrentPw}
        label="Current password"
        autoComplete="current-password"
        required
      />
      <ShowHideInput
        id="change-new-password"
        value={newPw}
        onChange={(v) => { setNewPw(v); setNewPwTouched(true); }}
        label="New password"
        autoComplete="new-password"
        required
      />
      {strengthHint && (
        <p
          className={`text-xs ${strengthHint.level === "error" ? "text-destructive" : "text-yellow-600 dark:text-yellow-400"}`}
          role="status"
          aria-live="polite"
        >
          {strengthHint.text}
        </p>
      )}
      <ShowHideInput
        id="change-confirm-password"
        value={confirmPw}
        onChange={setConfirmPw}
        label="Confirm new password"
        autoComplete="new-password"
        required
      />
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
      <div className="flex gap-2 pt-1">
        <Button type="submit" size="sm" className="h-7 text-xs" disabled={saving}>
          {saving ? "Saving..." : "Save"}
        </Button>
        <Button type="button" size="sm" variant="ghost" className="h-7 text-xs" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Set-password form (OAuth-only accounts)
// ---------------------------------------------------------------------------

function SetPasswordForm({
  email,
  onSuccess,
  onCancel,
}: {
  email: string;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [newPwTouched, setNewPwTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const strengthHint = newPwTouched ? passwordStrengthHint(newPw) : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPw !== confirmPw) {
      setError("Passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      await setPassword({ new_password: newPw });
      onSuccess();
    } catch (err) {
      setError(describePasswordError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mt-2 space-y-2">
      <ShowHideInput
        id="set-new-password"
        value={newPw}
        onChange={(v) => { setNewPw(v); setNewPwTouched(true); }}
        label="New password"
        autoComplete="new-password"
        required
      />
      {strengthHint && (
        <p
          className={`text-xs ${strengthHint.level === "error" ? "text-destructive" : "text-yellow-600 dark:text-yellow-400"}`}
          role="status"
          aria-live="polite"
        >
          {strengthHint.text}
        </p>
      )}
      <ShowHideInput
        id="set-confirm-password"
        value={confirmPw}
        onChange={setConfirmPw}
        label="Confirm new password"
        autoComplete="new-password"
        required
      />
      <p className="text-xs text-muted-foreground">
        You'll be able to log in with <strong className="font-medium">{email}</strong> and this password.
      </p>
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
      <div className="flex gap-2 pt-1">
        <Button type="submit" size="sm" className="h-7 text-xs" disabled={saving}>
          {saving ? "Saving..." : "Set password"}
        </Button>
        <Button type="button" size="sm" variant="ghost" className="h-7 text-xs" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Main section component
// ---------------------------------------------------------------------------

export function PasswordManagementSection({ user, onRefresh }: Props) {
  const [formState, setFormState] = useState<FormState>("collapsed");
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Hidden when OAuth-only and no email (no credential pair to log in with).
  if (!user.has_password && user.email === null) return null;

  function handleSuccess(message: string) {
    setFormState("collapsed");
    setSuccessBanner(message);
    // Refresh so has_password and password_changed_at update.
    onRefresh().catch(() => {});
    setTimeout(() => setSuccessBanner(null), 3000);
  }

  return (
    <div className="px-4 py-3">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium">Password</p>
          {user.email && (
            <p className="mt-0.5 text-xs text-muted-foreground truncate">{user.email}</p>
          )}
          {user.has_password ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              Last changed: {formatLastChanged(user.password_changed_at)}
            </p>
          ) : (
            <p className="mt-0.5 text-xs text-muted-foreground">
              No password set. Add one to log in with email.
            </p>
          )}
        </div>

        {formState === "collapsed" && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 shrink-0 text-xs"
            onClick={() => setFormState("expanded")}
            aria-label={user.has_password ? "Change password" : "Set password"}
          >
            {user.has_password ? "Change password" : "Set password"}
          </Button>
        )}
      </div>

      {successBanner && (
        <p className="mt-2 text-xs text-green-700 dark:text-green-400" role="status">
          {successBanner}
        </p>
      )}

      {formState !== "collapsed" && (
        <>
          {user.has_password ? (
            <ChangePasswordForm
              onSuccess={() => handleSuccess("Password updated.")}
              onCancel={() => setFormState("collapsed")}
            />
          ) : (
            <SetPasswordForm
              email={user.email!}
              onSuccess={() => handleSuccess("Password set. You can now log in with your email.")}
              onCancel={() => setFormState("collapsed")}
            />
          )}
        </>
      )}
    </div>
  );
}
