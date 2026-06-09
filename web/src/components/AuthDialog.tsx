import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { yahooAuthorizeUrl, googleAuthorizeUrl } from "@/api/auth";
import { YahooIcon, GoogleIcon } from "@/components/BrandIcons";
import { ApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import type { SettingsState } from "@/components/SettingsPanel";
import type { Rule } from "@/api/types";

interface AuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialState: { settings: SettingsState; rules: Rule[] } | null;
}

export function AuthDialog({ open, onOpenChange, initialState }: AuthDialogProps) {
  const { signup, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

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
    try {
      await login({ email, password });
      onOpenChange(false);
    } catch (err) {
      setError(describe(err, "Login failed. Check your email and password."));
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await signup({
        email,
        password,
        initial_settings: initialState ? (initialState.settings as unknown as Record<string, unknown>) : undefined,
        initial_rules: initialState ? (initialState.rules as unknown as Array<Record<string, unknown>>) : undefined,
      });
      onOpenChange(false);
    } catch (err) {
      setError(describe(err, "Signup failed. Please try again."));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Account</DialogTitle>
        <Tabs defaultValue="login" onValueChange={() => setError(null)}>
          <TabsList>
            <TabsTrigger value="login">Log In</TabsTrigger>
            <TabsTrigger value="signup">Sign Up</TabsTrigger>
          </TabsList>

          <TabsContent value="login">
            <form onSubmit={handleLogin} className="space-y-3">
              <div>
                <label htmlFor="login-email" className="text-sm">Email</label>
                <Input id="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1" />
              </div>
              <div>
                <label htmlFor="login-password" className="text-sm">Password</label>
                <Input id="login-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1" />
              </div>
              {error && <p className="text-xs text-red-600">{error}</p>}
              <Button type="submit" className="w-full">Log In</Button>
            </form>
          </TabsContent>

          <TabsContent value="signup">
            <form onSubmit={handleSignup} className="space-y-3">
              <div>
                <label htmlFor="signup-email" className="text-sm">Email</label>
                <Input id="signup-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1" />
              </div>
              <div>
                <label htmlFor="signup-password" className="text-sm">Password (min 10 chars)</label>
                <Input id="signup-password" type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1" />
              </div>
              {error && <p className="text-xs text-red-600">{error}</p>}
              <Button type="submit" className="w-full">Create account</Button>
            </form>
          </TabsContent>
        </Tabs>

        <div className="text-center text-xs text-muted-foreground my-3">— or —</div>

        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={() => { window.location.href = yahooAuthorizeUrl(); }}
        >
          <YahooIcon />
          Continue with Yahoo
        </Button>
        <Button
          type="button"
          variant="outline"
          className="w-full mt-2"
          onClick={() => { window.location.href = googleAuthorizeUrl(); }}
        >
          <GoogleIcon />
          Continue with Google
        </Button>
      </DialogContent>
    </Dialog>
  );
}
