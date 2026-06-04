import { useState } from "react";
import { User } from "lucide-react";
import { playerHeadshotUrl } from "@/lib/espn-cdn";

interface Props {
  espnId: string | null;
  name: string;
}

export function PlayerHeadshot({ espnId, name }: Props) {
  const [failed, setFailed] = useState(false);
  if (!espnId || failed) {
    return (
      <div
        className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-muted"
        aria-hidden="true"
      >
        <User className="h-6 w-6 text-muted-foreground" />
      </div>
    );
  }
  return (
    <img
      src={playerHeadshotUrl(espnId)}
      alt={name}
      className="h-12 w-12 shrink-0 rounded-md object-cover object-top"
      onError={() => setFailed(true)}
    />
  );
}
