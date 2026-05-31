/**
 * Brand icons for the Linked Accounts dialog.
 *
 * Each icon is served by DuckDuckGo's icon proxy — it returns the site's
 * current favicon. Using the third-party service means rebrands flow through
 * automatically without us shipping a new asset.
 */

const SIZE = "h-4 w-4 shrink-0";

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

export function GoogleIcon() {
  return <FaviconIcon domain="google.com" alt="Google" />;
}

export function YahooIcon() {
  return <FaviconIcon domain="yahoo.com" alt="Yahoo" />;
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
