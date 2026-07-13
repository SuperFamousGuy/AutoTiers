import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/ui/toast";

// Regression guard for #647: the "Download Excel" export used to be fire-and-forget
// (`void downloadDraftXlsx(...)`), so a rejected lazy-chunk load / workbook build
// was a silently swallowed promise — the button did nothing and the user got no
// feedback. App now returns the promise so TiersPanel can show a busy spinner and
// surface a rejection as an inline error + Retry. These tests mock the code-split
// workbook builder so the export can be driven to both outcomes for real; they
// would fail if App reverted to `void`-ing the promise.

// The code-split workbook builder that downloadDraftXlsx lazy-imports. Mocking it
// lets us reject (offline / stale chunk) or resolve without a real xlsx library.
// downloadDraftXlsx also pulls buildXlsxFilename from this module to name the file,
// so the mock must stub it too — otherwise the success path throws before the
// download fires. A fixed name is fine here; these tests don't assert on it.
const buildDraftXlsxBlob = vi.fn();
vi.mock("@/lib/xlsx", () => ({
  buildDraftXlsxBlob: (...args: unknown[]) => buildDraftXlsxBlob(...args),
  buildXlsxFilename: () => "tiers.xlsx",
}));

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

// Generate a tier list so the TiersPanel (and its Download Excel button) renders.
async function generateTierList(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => {
    expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
  });
  await user.click(screen.getByRole("button", { name: /^generate$/i }));
  await waitFor(() => {
    expect(screen.getByRole("button", { name: /^download excel$/i })).toBeInTheDocument();
  });
}

describe("App — Download Excel busy/error wiring (#647)", () => {
  beforeEach(() => {
    buildDraftXlsxBlob.mockReset();
    // triggerBlobDownload uses these on the success path; jsdom lacks them.
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("surfaces an inline error when the workbook build rejects, instead of swallowing it", async () => {
    buildDraftXlsxBlob.mockRejectedValue(new Error("stale chunk"));
    const user = userEvent.setup();
    renderApp();
    await generateTierList(user);

    await user.click(screen.getByRole("button", { name: /^download excel$/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't build the excel file/i);
    expect(screen.getByRole("button", { name: /^retry$/i })).toBeInTheDocument();
  });

  it("clears busy state and shows no error when the export succeeds", async () => {
    buildDraftXlsxBlob.mockResolvedValue(new Blob(["x"]));
    const user = userEvent.setup();
    renderApp();
    await generateTierList(user);

    await user.click(screen.getByRole("button", { name: /^download excel$/i }));

    // The download fires (blob URL created) and no error alert appears.
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^download excel$/i })).not.toBeDisabled(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
