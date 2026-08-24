import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Human-readable name of the region being guarded, shown in the fallback copy. */
  label?: string;
  /**
   * Optional custom fallback. Receives the caught error and a `reset` callback
   * that clears the boundary's error state so the subtree re-mounts and retries.
   * When omitted, a minimal inline error card is rendered.
   */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Top-level React error boundary (#1186). React unmounts the entire component
 * tree when a render/lifecycle throw is uncaught, degrading the whole app to a
 * blank white screen with nothing in the DOM and only a console error. A single
 * malformed player (e.g. a NaN score that reached `.toFixed(1)`) should not be
 * able to do that. This boundary catches the throw and renders an inline
 * fallback so the failure is visible and — via `reset` — recoverable, instead of
 * silent. Error boundaries must be class components: there is no hook equivalent
 * of `getDerivedStateFromError` / `componentDidCatch`.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface the crash to the console (and any error-reporting hook a future
    // deployment wires in) rather than swallowing it — the fallback UI tells the
    // user, but developers still need the stack.
    console.error("ErrorBoundary caught a render error:", error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error !== null) {
      if (this.props.fallback) {
        return this.props.fallback(error, this.reset);
      }
      const region = this.props.label ?? "this view";
      return (
        <div
          role="alert"
          className="m-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          <p className="font-semibold">Something went wrong displaying {region}.</p>
          <p className="mt-1 text-red-700 dark:text-red-300">
            The rest of the app is still usable. You can try again, and if it keeps
            happening, reload the page.
          </p>
          <button
            type="button"
            onClick={this.reset}
            className="mt-3 rounded-md border border-red-300 bg-background px-3 py-1.5 font-medium text-red-800 hover:bg-red-100 dark:border-red-800 dark:text-red-200 dark:hover:bg-red-900/40"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
