import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// A component that throws on render, standing in for a real render crash such as
// `player.vbd_score.toFixed(1)` when vbd_score is NaN/undefined inside the Tiers
// tree (#1186).
function Boom({ message = "kaboom" }: { message?: string }): JSX.Element {
  throw new Error(message);
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // React logs the caught error to console.error; silence it so the test
    // output stays readable, and so componentDidCatch's own log is observable.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children unchanged when nothing throws", () => {
    render(
      <ErrorBoundary>
        <div>healthy child</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("healthy child")).toBeInTheDocument();
  });

  it("catches a render throw inside the tree and shows the fallback instead of unmounting", () => {
    render(
      <ErrorBoundary label="the tiers">
        <div>sibling content</div>
        <Boom />
      </ErrorBoundary>,
    );

    // The default fallback is an alert naming the guarded region.
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong displaying the tiers/i);
    // The crashing subtree is gone, not a blank screen: the fallback replaced it.
    expect(screen.queryByText("sibling content")).not.toBeInTheDocument();
  });

  it("logs the caught error via componentDidCatch", () => {
    render(
      <ErrorBoundary>
        <Boom message="explode" />
      </ErrorBoundary>,
    );
    expect(console.error).toHaveBeenCalled();
  });

  it("renders a custom fallback with the caught error when provided", () => {
    render(
      <ErrorBoundary fallback={(error) => <p>custom: {error.message}</p>}>
        <Boom message="from-render" />
      </ErrorBoundary>,
    );
    expect(screen.getByText("custom: from-render")).toBeInTheDocument();
  });

  it("recovers via the Try again button once the child stops throwing", async () => {
    const user = userEvent.setup();

    // A parent whose child throws only on the first render pass; clicking
    // "Try again" resets the boundary and the now-healthy child mounts.
    function Flaky(): JSX.Element {
      const [ok, setOk] = useState(false);
      return (
        <>
          <button onClick={() => setOk(true)}>fix it</button>
          <ErrorBoundary>{ok ? <div>recovered</div> : <Boom />}</ErrorBoundary>
        </>
      );
    }

    render(<Flaky />);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    // Repair the child first, then reset the boundary so its re-render succeeds.
    await user.click(screen.getByText("fix it"));
    await user.click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByText("recovered")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
