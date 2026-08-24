import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Header } from "@/components/Header";
import { ToastProvider } from "@/components/ui/toast";

// Header renders DataFreshness (fetches via react-query) and a FeedbackDialog
// (uses the toast context), so it needs both providers around it even though this
// test only exercises the menu.
function renderHeader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <Header
          generateDisabled={false}
          generateIsPending={false}
          onGenerate={vi.fn()}
          isDark={false}
          onToggleDark={vi.fn()}
        />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("Header content-library link (#1250)", () => {
  it("exposes a Guides & Glossary link to the static content hub", async () => {
    const user = userEvent.setup();
    renderHeader();

    // The link lives in the hamburger dropdown, which only renders once opened.
    await user.click(screen.getByRole("button", { name: /menu/i }));

    // Radix's DropdownMenuItem asChild merges role="menuitem" onto the anchor,
    // so it is a menuitem that happens to be a link — query it as such.
    const link = await screen.findByRole("menuitem", { name: /guides & glossary/i });
    expect(link).toHaveAttribute("href", "/content.html");
    // Opens in a new tab like the sibling Privacy / Terms links.
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});
