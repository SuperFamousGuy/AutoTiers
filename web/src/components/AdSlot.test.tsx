import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdSlot } from "@/components/AdSlot";

afterEach(() => {
  vi.unstubAllEnvs();
  sessionStorage.clear();
  document.head
    .querySelectorAll("script[data-autotiers-adsense]")
    .forEach((el) => el.remove());
  delete (window as { adsbygoogle?: unknown[] }).adsbygoogle;
});

describe("AdSlot", () => {
  it("renders nothing when ads are disabled (default)", () => {
    const { container } = render(<AdSlot slot="123" hasPublisherContent />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a labelled in-house placeholder when enabled without a client id", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    render(<AdSlot slot="123" hasPublisherContent />);
    expect(screen.getByLabelText("Advertisement")).toBeInTheDocument();
    expect(screen.getByText(/your ad could be here/i)).toBeInTheDocument();
    // No real AdSense unit without a client id.
    expect(document.querySelector("ins.adsbygoogle")).toBeNull();
  });

  it("renders a real AdSense unit when enabled with client + slot", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    vi.stubEnv("VITE_ADSENSE_CLIENT_ID", "ca-pub-123");
    render(<AdSlot slot="999" hasPublisherContent />);

    const ins = document.querySelector("ins.adsbygoogle");
    expect(ins).not.toBeNull();
    expect(ins).toHaveAttribute("data-ad-client", "ca-pub-123");
    expect(ins).toHaveAttribute("data-ad-slot", "999");
    // The component should have queued a fill request and loaded the script.
    expect((window as { adsbygoogle?: unknown[] }).adsbygoogle).toHaveLength(1);
    expect(document.querySelector("script[data-autotiers-adsense]")).not.toBeNull();
  });

  it("falls back to the placeholder when a client id is set but no slot", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    vi.stubEnv("VITE_ADSENSE_CLIENT_ID", "ca-pub-123");
    render(<AdSlot hasPublisherContent />);
    expect(screen.getByText(/your ad could be here/i)).toBeInTheDocument();
    expect(document.querySelector("ins.adsbygoogle")).toBeNull();
  });

  it("hides itself for the session when dismissed", async () => {
    const user = userEvent.setup();
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    const { container } = render(<AdSlot slot="123" hasPublisherContent />);

    await user.click(screen.getByLabelText("Dismiss advertisement"));
    expect(container).toBeEmptyDOMElement();

    // A freshly mounted slot stays hidden for the rest of the session.
    const second = render(<AdSlot slot="123" hasPublisherContent />);
    expect(second.container).toBeEmptyDOMElement();
  });

  it("omits the dismiss control when dismissible is false", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    render(<AdSlot slot="123" hasPublisherContent dismissible={false} />);
    expect(screen.queryByLabelText("Dismiss advertisement")).not.toBeInTheDocument();
  });

  // AdSense flagged the site for "Google-served ads on screens without
  // publisher-content". The pre-generate empty state is such a screen, so the
  // slot must stay closed there even with ads fully configured.
  it("renders nothing on a screen with no publisher content", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    vi.stubEnv("VITE_ADSENSE_CLIENT_ID", "ca-pub-123");
    const { container } = render(<AdSlot slot="999" hasPublisherContent={false} />);

    expect(container).toBeEmptyDOMElement();
    expect(document.querySelector("ins.adsbygoogle")).toBeNull();
    // Crucially, no fill was requested and no loader was injected.
    expect((window as { adsbygoogle?: unknown[] }).adsbygoogle).toBeUndefined();
    expect(document.querySelector("script[data-autotiers-adsense]")).toBeNull();
  });

  it("fails closed when hasPublisherContent is omitted entirely", () => {
    vi.stubEnv("VITE_ADS_ENABLED", "true");
    vi.stubEnv("VITE_ADSENSE_CLIENT_ID", "ca-pub-123");
    const { container } = render(<AdSlot slot="999" />);
    expect(container).toBeEmptyDOMElement();
  });
});
