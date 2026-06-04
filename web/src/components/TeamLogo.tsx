import { useState } from "react";
import { teamLogoUrl } from "@/lib/espn-cdn";

interface Props {
  code: string;
  size?: number;
}

export function TeamLogo({ code, size = 20 }: Props) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="text-xs">{code}</span>;
  return (
    <img
      src={teamLogoUrl(code)}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      className="inline shrink-0"
      onError={() => setFailed(true)}
    />
  );
}
