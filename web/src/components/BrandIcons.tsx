/**
 * Brand icons for the Linked Accounts dialog.
 *
 * Google / Yahoo / CBS come from react-icons (Font Awesome + Simple Icons).
 * Sleeper, ESPN, and NFL aren't in those libraries, so they're styled letter marks
 * in each provider's brand color. All icons render at 16px and stay color-aware.
 */
import { FaGoogle, FaYahoo } from "react-icons/fa";
import { SiCbs } from "react-icons/si";

const SIZE = "h-4 w-4 shrink-0";

export function GoogleIcon() {
  return <FaGoogle aria-hidden className={`${SIZE} text-[#4285F4]`} />;
}

export function YahooIcon() {
  return <FaYahoo aria-hidden className={`${SIZE} text-[#6001D2]`} />;
}

export function CbsIcon() {
  return <SiCbs aria-hidden className={`${SIZE} text-foreground`} />;
}

function LetterMark({
  label,
  bg,
  color = "white",
}: {
  label: string;
  bg: string;
  color?: string;
}) {
  return (
    <span
      aria-hidden
      className={`${SIZE} inline-flex items-center justify-center rounded-sm text-[8px] font-bold leading-none`}
      style={{ backgroundColor: bg, color }}
    >
      {label}
    </span>
  );
}

export function SleeperIcon() {
  // Sleeper's brand orange.
  return <LetterMark label="S" bg="#FF7900" />;
}

export function EspnIcon() {
  // ESPN's signature red.
  return <LetterMark label="E" bg="#D81F26" />;
}

export function NflFantasyIcon() {
  // NFL navy.
  return <LetterMark label="N" bg="#013369" />;
}
