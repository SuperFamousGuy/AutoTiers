/**
 * Brand icons for the Linked Accounts dialog.
 *
 * All six provider icons are self-hosted under `web/public/icons/`. No
 * third-party icon library, no runtime third-party requests. See
 * `web/public/icons/README.md` for sources and how to refresh them.
 */

const SIZE = "h-4 w-4 shrink-0";

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

export function GoogleIcon() {
  return <LocalIcon src="/icons/google.png" alt="Google" />;
}

export function YahooIcon() {
  return <LocalIcon src="/icons/yahoo.png" alt="Yahoo" />;
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
