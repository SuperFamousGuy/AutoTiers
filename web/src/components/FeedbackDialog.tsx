import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useToast } from "@/components/ui/toast";
import {
  sendFeedback,
  type FeedbackCategory,
  type FeedbackAttachment,
} from "@/api/feedback";
import { ApiError } from "@/api/client";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The logged-in user's email, if any — used only for the reply-disclosure copy. */
  userEmail?: string | null;
}

/** Selectable feedback categories, in display order. Default is "idea". */
const CATEGORY_OPTIONS: { value: FeedbackCategory; label: string }[] = [
  { value: "bug", label: "Bug" },
  { value: "idea", label: "Idea" },
  { value: "other", label: "Other" },
];

const DEFAULT_CATEGORY: FeedbackCategory = "idea";

/** Client-side screenshot constraints (#287). The backend re-validates these;
 * this is a UX nicety so the user gets immediate feedback, not the gate. */
const ALLOWED_SCREENSHOT_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024; // 2 MB

/** Best-effort extraction of FastAPI's `{ detail }` string from an ApiError.
 * The ApiError message is the raw response body (JSON for our backend). */
function apiErrorDetail(e: ApiError): string | null {
  try {
    const parsed = JSON.parse(e.message);
    if (parsed && typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Body wasn't JSON — nothing to surface.
  }
  return null;
}

/** Read a File into raw base64 (no data-URL prefix). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        // readAsDataURL should always yield a string; guard so an unexpected
        // null/ArrayBuffer rejects cleanly instead of throwing in onload.
        reject(new Error("unexpected FileReader result"));
        return;
      }
      // Strip the "data:<type>;base64," prefix; keep only the payload.
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.readAsDataURL(file);
  });
}

export function FeedbackDialog({ open, onOpenChange, userEmail }: Props) {
  const { toast } = useToast();
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState<FeedbackCategory>(DEFAULT_CATEGORY);
  const [attachment, setAttachment] = useState<FeedbackAttachment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset transient state whenever the dialog opens.
  useEffect(() => {
    if (open) {
      setMessage("");
      setCategory(DEFAULT_CATEGORY);
      setAttachment(null);
      setError(null);
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [open]);

  const canSubmit = message.trim().length > 0 && !busy;

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    const file = e.target.files?.[0];
    if (!file) {
      setAttachment(null);
      return;
    }
    if (!ALLOWED_SCREENSHOT_TYPES.includes(file.type)) {
      setError("Image must be a PNG, JPEG, or WebP file.");
      setAttachment(null);
      e.target.value = "";
      return;
    }
    if (file.size > MAX_SCREENSHOT_BYTES) {
      setError("Image must be under 2 MB.");
      setAttachment(null);
      e.target.value = "";
      return;
    }
    try {
      const base64 = await fileToBase64(file);
      setAttachment({ base64, name: file.name, type: file.type });
    } catch {
      setError("Couldn't read that image. Please try a different file.");
      setAttachment(null);
      e.target.value = "";
    }
  }

  function removeAttachment() {
    setAttachment(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await sendFeedback(message.trim(), category, attachment);
      toast({ title: "Thanks for the feedback!", variant: "success" });
      onOpenChange(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setError("You're sending feedback too quickly — please wait a moment and try again.");
      } else if (e instanceof ApiError && e.status === 422) {
        // 422 can be screenshot-specific OR another validation failure; prefer
        // the backend's own user-facing detail when present.
        setError(
          apiErrorDetail(e) ??
            "That image couldn't be accepted. Please try a smaller PNG, JPEG, or WebP.",
        );
      } else {
        setError("Couldn't send your feedback right now. Please try again in a moment.");
      }
      setBusy(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void handleSubmit();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Send Feedback</DialogTitle>
        <DialogDescription>
          Found a bug or have an idea? Tell us — it goes straight to the AutoTiers team.
        </DialogDescription>

        <div className="mt-3 space-y-2">
          <span id="feedback-type-label" className="text-xs font-medium text-foreground">
            Type
          </span>
          <RadioGroup
            aria-labelledby="feedback-type-label"
            className="flex gap-4"
            value={category}
            onValueChange={(v) => setCategory(v as FeedbackCategory)}
            disabled={busy}
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                htmlFor={`feedback-category-${opt.value}`}
                className="flex items-center gap-2 text-xs text-foreground"
              >
                <RadioGroupItem
                  id={`feedback-category-${opt.value}`}
                  value={opt.value}
                />
                {opt.label}
              </label>
            ))}
          </RadioGroup>
        </div>

        <div className="mt-3 space-y-2">
          <label htmlFor="feedback-message" className="text-xs font-medium text-foreground">
            Your feedback
          </label>
          <Textarea
            id="feedback-message"
            ref={textareaRef}
            rows={5}
            maxLength={4000}
            autoFocus
            disabled={busy}
            placeholder="What's on your mind?"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <p className="text-[11px] text-muted-foreground">
            {userEmail
              ? `We'll include your email (${userEmail}) so we can reply.`
              : "Sign in if you'd like a reply — otherwise this is anonymous."}
          </p>
        </div>

        <div className="mt-3 space-y-2">
          <label htmlFor="feedback-screenshot" className="text-xs font-medium text-foreground">
            Attach screenshot (optional)
          </label>
          <input
            id="feedback-screenshot"
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            disabled={busy}
            onChange={handleFileChange}
            className="block w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-secondary-foreground hover:file:bg-secondary/80"
          />
          {attachment && (
            <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
              <span className="truncate">Attached: {attachment.name}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={removeAttachment}
              >
                Remove
              </Button>
            </div>
          )}
          <p className="text-[11px] text-muted-foreground">
            PNG, JPEG, or WebP, up to 2 MB.
          </p>
        </div>

        {error && (
          <p role="alert" className="mt-2 text-xs text-red-600">
            {error}
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button size="sm" disabled={!canSubmit} onClick={() => void handleSubmit()}>
            {busy ? "Sending…" : "Send Feedback"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
