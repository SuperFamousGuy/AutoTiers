/**
 * Minimal toast primitive built on @radix-ui/react-toast.
 *
 * Usage:
 *   const { toast } = useToast();
 *   toast({ title: "Done!", variant: "success" });
 *
 * Wrap your app with <ToastProvider> (exported from this file) once in main.tsx.
 */
import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

export interface ToastOptions {
  title: string;
  description?: string;
  /** "success" (role=status) | "error" (role=alert) */
  variant?: "success" | "error";
  /** Duration in ms — defaults to 4000 */
  duration?: number;
}

interface ToastItem extends ToastOptions {
  id: string;
  open: boolean;
}

interface ToastContextValue {
  toast: (opts: ToastOptions) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider + Toaster
// ---------------------------------------------------------------------------

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);

  const toast = React.useCallback((opts: ToastOptions) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { ...opts, id, open: true }]);
  }, []);

  const close = React.useCallback((id: string) => {
    // Toggle `open` to false so Radix plays the exit animation, then drop the
    // item from state once the animation has finished. Without the removal the
    // array grows unbounded over a long session (one stale entry per toast).
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, open: false } : t)));
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 1000);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {toasts.map((t) => (
          <ToastPrimitive.Root
            key={t.id}
            open={t.open}
            onOpenChange={(open) => { if (!open) close(t.id); }}
            duration={t.duration ?? 4000}
            role={t.variant === "error" ? "alert" : "status"}
            className={cn(
              "group pointer-events-auto relative flex w-full max-w-sm items-center justify-between space-x-4 overflow-hidden rounded-md border p-4 shadow-lg transition-all",
              "data-[state=open]:animate-in data-[state=closed]:animate-out",
              "data-[state=closed]:fade-out-80 data-[state=open]:fade-in-0",
              "data-[state=closed]:slide-out-to-right-full data-[state=open]:slide-in-from-right-full",
              t.variant === "error"
                ? "border-destructive bg-destructive text-destructive-foreground"
                : "border-border bg-card text-card-foreground",
            )}
          >
            <div className="grid gap-1">
              <ToastPrimitive.Title className="text-sm font-semibold">
                {t.title}
              </ToastPrimitive.Title>
              {t.description && (
                <ToastPrimitive.Description className="text-xs opacity-80">
                  {t.description}
                </ToastPrimitive.Description>
              )}
            </div>
            <ToastPrimitive.Close
              aria-label="Dismiss notification"
              className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              onClick={() => close(t.id)}
            >
              <X className="h-4 w-4" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-[100] flex max-h-screen w-full flex-col-reverse gap-2 p-4 sm:max-w-sm" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
