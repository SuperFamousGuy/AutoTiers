/**
 * Brand icons for the Linked Accounts dialog.
 *
 * Google / Yahoo come from react-icons (Font Awesome), since their vector marks
 * render cleaner at small sizes than rasters. ESPN, NFL, Sleeper, and CBS aren't
 * in any major icon library, so we use DuckDuckGo's icon proxy — it returns each
 * site's actual favicon as a PNG. Real official mark, no hand-drawn approximation.
 */
import { FaGoogle, FaYahoo } from "react-icons/fa";

const SIZE = "h-4 w-4 shrink-0";

export function GoogleIcon() {
  return <FaGoogle aria-hidden className={`${SIZE} text-[#4285F4]`} />;
}

export function YahooIcon() {
  return <FaYahoo aria-hidden className={`${SIZE} text-[#6001D2]`} />;
}

function FaviconIcon({ domain, alt }: { domain: string; alt: string }) {
  return (
    <img
      src={`https://icons.duckduckgo.com/ip3/${domain}.ico`}
      alt={alt}
      className={`${SIZE} rounded-sm object-contain`}
      loading="lazy"
    />
  );
}

export function SleeperIcon() {
  return <FaviconIcon domain="sleeper.com" alt="Sleeper" />;
}

export function EspnIcon() {
  return <FaviconIcon domain="espn.com" alt="ESPN" />;
}

export function NflFantasyIcon() {
  return <FaviconIcon domain="fantasy.nfl.com" alt="NFL Fantasy" />;
}

export function CbsIcon() {
  return <FaviconIcon domain="cbssports.com" alt="CBS Sports" />;
}
