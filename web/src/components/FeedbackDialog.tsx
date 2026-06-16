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
import { sendFeedback, type FeedbackCategory } from "@/api/feedback";
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

export function FeedbackDialog({ open, onOpenChange, userEmail }: Props) {
  const { toast } = useToast();
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState<FeedbackCategory>(DEFAULT_CATEGORY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Reset transient state whenever the dialog opens.
  useEffect(() => {
    if (open) {
      setMessage("");
      setCategory(DEFAULT_CATEGORY);
      setError(null);
      setBusy(false);
    }
  }, [open]);

  const canSubmit = message.trim().length > 0 && !busy;

  async function handleSubmit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await sendFeedback(message.trim(), category);
      toast({ title: "Thanks for the feedback!", variant: "success" });
      onOpenChange(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setError("You're sending feedback too quickly — please wait a moment and try again.");
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
          {error && (
            <p role="alert" className="text-xs text-red-600">
              {error}
            </p>
          )}
        </div>

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
