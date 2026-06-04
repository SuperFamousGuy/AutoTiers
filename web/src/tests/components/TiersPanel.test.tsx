import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TiersPanel } from "@/components/TiersPanel";
import generateResponse from "../fixtures/generate-response.json";
import type { GenerateResponse } from "@/api/types";

const response = generateResponse as GenerateResponse;

describe("TiersPanel", () => {
  it("shows placeholder when no result", () => {
    render(<TiersPanel result={null} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/click generate/i)).toBeInTheDocument();
  });

  it("shows skeleton when pending", () => {
    render(<TiersPanel result={null} isPending={true} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/generating/i)).toBeInTheDocument();
  });

  it("renders all players grouped by tier", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Bijan Robinson")).toBeInTheDocument();
    expect(screen.getByText("Josh Allen")).toBeInTheDocument();
  });

  it("renders tier headers", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/tier 1/i)).toBeInTheDocument();
    expect(screen.getByText(/tier 2/i)).toBeInTheDocument();
  });

  it("shows descriptive label 'Elite' in the Tier 1 header span", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    // Verify "Elite" is co-located with "Tier 1" in the same header span, not elsewhere in the DOM.
    // eliteEl.parentElement is the outer bold <span> that also contains the tier number text node.
    const eliteEl = screen.getByText("Elite");
    expect(eliteEl.parentElement).toHaveTextContent(/Tier 1/);
  });

  it("shows descriptive label 'Strong Starter' in the Tier 2 header span", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const starterEl = screen.getByText("Strong Starter");
    expect(starterEl.parentElement).toHaveTextContent(/Tier 2/);
  });

  it("does not show descriptive labels when position filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    expect(screen.queryByText("Elite")).not.toBeInTheDocument();
    expect(screen.queryByText("Strong Starter")).not.toBeInTheDocument();
  });

  it("filters by position when a position chip is clicked", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Justin Jefferson")).toBeInTheDocument();
    expect(screen.queryByText("Bijan Robinson")).not.toBeInTheDocument();
    expect(screen.queryByText("Josh Allen")).not.toBeInTheDocument();
  });

  it("groups by positional tier when filtered to a position", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    // Now the tier headers should be position-relative (WR1, WR2) not overall (Tier 1, Tier 2).
    expect(screen.getByText(/WR1/)).toBeInTheDocument();
    expect(screen.getByText(/WR2/)).toBeInTheDocument();
  });

  it("calls onDownloadCsv when CSV button clicked", async () => {
    const onDownload = vi.fn();
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={onDownload} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /download csv/i }));
    expect(onDownload).toHaveBeenCalled();
  });
});
