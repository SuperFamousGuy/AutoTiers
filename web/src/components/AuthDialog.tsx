import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { yahooAuthorizeUrl, googleAuthorizeUrl, requestPasswordReset } from "@/api/auth";
import { YahooIcon, GoogleIcon } from "@/components/BrandIcons";
import { ApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import type { SettingsState } from "@/components/SettingsPanel";
import type { PositionRulesState } from "@/api/types";

interface AuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialState: { settings: SettingsState; rules: PositionRulesState } | null;
  /** When provided, opens the dialog directly to the forgot-password sub-view. */
  initialView?: "login" | "signup" | "forgot_password";
}

type View = "login" | "signup" | "forgot_password" | "forgot_password_sent";

// ---------------------------------------------------------------------------
// Password strength hint
// ---------------------------------------------------------------------------

function passwordStrengthHint(password: string): { text: string; level: "error" | "warn" | "ok" } | null {
  if (password.length === 0) return null;
  if (password.length < 10) return { text: "Must be at least 10 characters", level: "error" };
  if (/^[a-z]+$/.test(password)) return { text: "Add uppercase letters, numbers, or symbols", level: "warn" };
  return null;
}

// ---------------------------------------------------------------------------
// Show/hide password input
// ---------------------------------------------------------------------------

interface PasswordInputProps {
  id: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  minLength?: number;
  autoComplete?: string;
  placeholder?: string;
}

function PasswordInput({ id, value, onChange, required, minLength, autoComplete, placeholder }: PasswordInputProps) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? "text" : "password"}
        required={required}
        minLength={minLength}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        className="pr-9"
      />
      <button
        type="button"
        aria-label={show ? "Hide password" : "Show password"}
        onClick={() => setShow((s) => !s)}
        tabIndex={0}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AuthDialog({ open, onOpenChange, initialState, initialView }: AuthDialogProps) {
  const { signup, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Forgot-password sub-view lives outside the Tabs so we can overlay it
  // without unmounting the tabs (which would reset tab-level state).
  const [view, setView] = useState<View>(initialView ?? "login");
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotError, setForgotError] = useState<string | null>(null);
  const [forgotLoading, setForgotLoading] = useState(false);

  // Try to extract a human-readable error from a backend response. FastAPI
  // returns JSON like {"detail": "..."} for 4xx; Pydantic 422s return a list
  // of field errors under "detail" — we surface the first one.
  function describe(err: unknown, fallback: string): string {
    if (!(err instanceof ApiError)) return fallback;
    try {
      const parsed = JSON.parse(err.message);
      if (typeof parsed.detail === "string") return parsed.detail;
      if (Array.isArray(parsed.detail) && parsed.detail.length > 0) {
        const first = parsed.detail[0];
        if (typeof first?.msg === "string") {
          const path = Array.isArray(first.loc) ? first.loc.slice(-1).join("") : "";
          return path ? `${path}: ${first.msg}` : first.msg;
        }
      }
    } catch {
      // Not JSON — fall through and use the raw message.
    }
    return err.message || fallback;
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ email, password });
      onOpenChange(false);
    } catch (err) {
      setError(describe(err, "Login failed. Check your email and password."));
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (confirmPassword !== password) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await signup({
        email,
        password,
        initial_settings: initialState ? (initialState.settings as unknown as Record<string, unknown>) : undefined,
        initial_rules: initialState ? initialState.rules : undefined,
      });
      onOpenChange(false);
    } catch (err) {
      setError(describe(err, "Signup failed. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotError(null);
    setForgotLoading(true);
    try {
      await requestPasswordReset({ email: forgotEmail });
      setView("forgot_password_sent");
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setForgotError("Too many requests. Please wait a few minutes before trying again.");
      } else {
        setForgotError("Something went wrong. Please try again.");
      }
    } finally {
      setForgotLoading(false);
    }
  };

  function resetToLogin() {
    setView("login");
    setForgotEmail("");
    setForgotError(null);
    setError(null);
  }

  // Clear errors when switching tabs; keep the tab-level view in sync.
  function handleTabChange(value: string) {
    setError(null);
    setPasswordTouched(false);
    // Switching tabs always exits forgot-password sub-view.
    if (view === "forgot_password" || view === "forgot_password_sent") {
      setView(value as "login" | "signup");
    }
  }

  const strengthHint = passwordTouched ? passwordStrengthHint(password) : null;

  // ---------------------------------------------------------------------------
  // Forgot-password and sent views replace the tab content area
  // ---------------------------------------------------------------------------

  const renderForgotPasswordRequest = () => (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-semibold">Reset your password</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Enter the email address on your account. If it matches, you'll receive a reset link within a few minutes.
        </p>
      </div>
      <form onSubmit={handleForgotPassword} className="space-y-3">
        <div>
          <label htmlFor="forgot-email" className="text-sm">Email address</label>
          <Input
            id="forgot-email"
            type="email"
            required
            value={forgotEmail}
            onChange={(e) => setForgotEmail(e.target.value)}
            className="mt-1"
            autoComplete="email"
          />
        </div>
        {forgotError && <p className="text-xs text-destructive" role="alert">{forgotError}</p>}
        <Button type="submit" className="w-full" disabled={forgotLoading}>
          {forgotLoading ? "Sending..." : "Send reset link"}
        </Button>
      </form>
      <button
        type="button"
        onClick={resetToLogin}
        className="text-xs text-muted-foreground underline-offset-4 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Back to log in
      </button>
    </div>
  );

  const renderForgotPasswordSent = () => (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-semibold">Check your inbox</p>
        <p className="mt-1 text-xs text-muted-foreground">
          If that email matches an account, a reset link is on its way. Check your spam folder if you don't see it within a few minutes.
        </p>
      </div>
      <button
        type="button"
        onClick={resetToLogin}
        className="text-xs text-muted-foreground underline-offset-4 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Back to log in
      </button>
    </div>
  );

  const isForgotView = view === "forgot_password" || view === "forgot_password_sent";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Account</DialogTitle>
        <Tabs
          defaultValue={initialView && (initialView === "signup") ? "signup" : "login"}
          onValueChange={handleTabChange}
        >
          <TabsList>
            <TabsTrigger value="login">Log In</TabsTrigger>
            <TabsTrigger value="signup">Sign Up</TabsTrigger>
          </TabsList>

          {isForgotView ? (
            <div className="mt-4">
              {view === "forgot_password" ? renderForgotPasswordRequest() : renderForgotPasswordSent()}
            </div>
          ) : (
            <>
              <TabsContent value="login">
                <form onSubmit={handleLogin} className="space-y-3">
                  <div>
                    <label htmlFor="login-email" className="text-sm">Email</label>
                    <Input
                      id="login-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="mt-1"
                      autoComplete="email"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between">
                      <label htmlFor="login-password" className="text-sm">Password</label>
                      <button
                        type="button"
                        onClick={() => setView("forgot_password")}
                        className="text-xs text-muted-foreground underline-offset-4 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        Forgot password?
                      </button>
                    </div>
                    <PasswordInput
                      id="login-password"
                      value={password}
                      onChange={setPassword}
                      required
                      autoComplete="current-password"
                    />
                  </div>
                  {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
                  <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? "Logging in..." : "Log In"}
                  </Button>
                </form>
              </TabsContent>

              <TabsContent value="signup">
                <form onSubmit={handleSignup} className="space-y-3">
                  <div>
                    <label htmlFor="signup-email" className="text-sm">Email</label>
                    <Input
                      id="signup-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="mt-1"
                      autoComplete="email"
                    />
                  </div>
                  <div>
                    <label htmlFor="signup-password" className="text-sm">Password</label>
                    <div className="mt-1">
                      <PasswordInput
                        id="signup-password"
                        value={password}
                        onChange={(v) => { setPassword(v); setPasswordTouched(true); }}
                        required
                        minLength={10}
                        autoComplete="new-password"
                      />
                    </div>
                    {strengthHint && (
                      <p
                        className={`mt-1 text-xs ${
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
                  </div>
                  <div>
                    <label htmlFor="signup-confirm-password" className="text-sm">Confirm password</label>
                    <div className="mt-1">
                      <PasswordInput
                        id="signup-confirm-password"
                        value={confirmPassword}
                        onChange={setConfirmPassword}
                        required
                        autoComplete="new-password"
                      />
                    </div>
                  </div>
                  {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
                  <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? "Creating account..." : "Create account"}
                  </Button>
                </form>
              </TabsContent>
            </>
          )}
        </Tabs>

        <div className="text-center text-xs text-muted-foreground my-3">— or —</div>

        <Button
          type="button"
          variant="outline"
          className="w-full gap-2"
          onClick={() => { window.location.href = yahooAuthorizeUrl(); }}
        >
          <span aria-hidden="true"><YahooIcon /></span>
          Continue with Yahoo
        </Button>
        <Button
          type="button"
          variant="outline"
          className="w-full mt-2 gap-2"
          onClick={() => { window.location.href = googleAuthorizeUrl(); }}
        >
          <span aria-hidden="true"><GoogleIcon /></span>
          Continue with Google
        </Button>
      </DialogContent>
    </Dialog>
  );
}
