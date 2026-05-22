import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataFreshness } from "@/components/DataFreshness";
import type { ReactNode } from "react";

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DataFreshness", () => {
  it("renders 'Loading data status…' while fetching", async () => {
    renderWithClient(<DataFreshness />);
    expect(screen.getByText(/loading data status/i)).toBeInTheDocument();
  });

  it("renders the oldest source's relative time after load", async () => {
    renderWithClient(<DataFreshness />);
    expect(await screen.findByText(/data updated/i)).toBeInTheDocument();
  });
});
