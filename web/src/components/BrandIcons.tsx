/**
 * Brand icons for the Linked Accounts dialog.
 *
 * Google / Yahoo come from react-icons (Font Awesome) — vector marks that scale
 * crisp at any size. ESPN, NFL, Sleeper, and CBS aren't in any major icon library,
 * so we self-host each provider's actual favicon under `web/public/icons/`. See
 * `web/public/icons/README.md` for the sources and how to refresh them.
 */
import { FaGoogle, FaYahoo } from "react-icons/fa";

const SIZE = "h-4 w-4 shrink-0";

export function GoogleIcon() {
  return <FaGoogle aria-hidden className={`${SIZE} text-[#4285F4]`} />;
}

export function YahooIcon() {
  return <FaYahoo aria-hidden className={`${SIZE} text-[#6001D2]`} />;
}

function LocalIcon({ src, alt }: { src: string; alt: string }) {
  return (
    <img
      src={src}
      alt={alt}
      className={`${SIZE} rounded-sm object-contain`}
      loading="lazy"
    />
  );
}

export function SleeperIcon() {
  return <LocalIcon src="/icons/sleeper.png" alt="Sleeper" />;
}

export function EspnIcon() {
  return <LocalIcon src="/icons/espn.png" alt="ESPN" />;
}

export function NflFantasyIcon() {
  return <LocalIcon src="/icons/nfl.png" alt="NFL Fantasy" />;
}

export function CbsIcon() {
  return <LocalIcon src="/icons/cbs.png" alt="CBS Sports" />;
}
