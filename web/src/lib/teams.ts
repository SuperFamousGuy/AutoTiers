export const NFL_CONFERENCES: {
  conference: string;
  divisions: { division: string; teams: { code: string; name: string }[] }[];
}[] = [
  {
    conference: "AFC",
    divisions: [
      { division: "East", teams: [
        { code: "BUF", name: "Buffalo Bills" },
        { code: "MIA", name: "Miami Dolphins" },
        { code: "NE",  name: "New England Patriots" },
        { code: "NYJ", name: "New York Jets" },
      ]},
      { division: "North", teams: [
        { code: "BAL", name: "Baltimore Ravens" },
        { code: "CIN", name: "Cincinnati Bengals" },
        { code: "CLE", name: "Cleveland Browns" },
        { code: "PIT", name: "Pittsburgh Steelers" },
      ]},
      { division: "South", teams: [
        { code: "HOU", name: "Houston Texans" },
        { code: "IND", name: "Indianapolis Colts" },
        { code: "JAX", name: "Jacksonville Jaguars" },
        { code: "TEN", name: "Tennessee Titans" },
      ]},
      { division: "West", teams: [
        { code: "DEN", name: "Denver Broncos" },
        { code: "KC",  name: "Kansas City Chiefs" },
        { code: "LV",  name: "Las Vegas Raiders" },
        { code: "LAC", name: "Los Angeles Chargers" },
      ]},
    ],
  },
  {
    conference: "NFC",
    divisions: [
      { division: "East", teams: [
        { code: "DAL", name: "Dallas Cowboys" },
        { code: "NYG", name: "New York Giants" },
        { code: "PHI", name: "Philadelphia Eagles" },
        { code: "WAS", name: "Washington Commanders" },
      ]},
      { division: "North", teams: [
        { code: "CHI", name: "Chicago Bears" },
        { code: "DET", name: "Detroit Lions" },
        { code: "GB",  name: "Green Bay Packers" },
        { code: "MIN", name: "Minnesota Vikings" },
      ]},
      { division: "South", teams: [
        { code: "ATL", name: "Atlanta Falcons" },
        { code: "CAR", name: "Carolina Panthers" },
        { code: "NO",  name: "New Orleans Saints" },
        { code: "TB",  name: "Tampa Bay Buccaneers" },
      ]},
      { division: "West", teams: [
        { code: "ARI", name: "Arizona Cardinals" },
        { code: "LAR", name: "Los Angeles Rams" },
        { code: "SF",  name: "San Francisco 49ers" },
        { code: "SEA", name: "Seattle Seahawks" },
      ]},
    ],
  },
];

export const TEAM_FULL_NAME: Record<string, string> = Object.fromEntries(
  NFL_CONFERENCES.flatMap((c) =>
    c.divisions.flatMap((d) => d.teams.map((t) => [t.code, t.name]))
  )
);

export const TEAM_PRIMARY_COLORS: Record<string, string> = {
  ARI: "#97233F", ATL: "#A71930", BAL: "#241773", BUF: "#00338D",
  CAR: "#0085CA", CHI: "#0B162A", CIN: "#FB4F14", CLE: "#311D00",
  DAL: "#003594", DEN: "#FB4F14", DET: "#0076B6", GB:  "#203731",
  HOU: "#03202F", IND: "#002C5F", JAX: "#006778", KC:  "#E31837",
  LAC: "#0080C6", LAR: "#003594", LV:  "#A5ACAF", MIA: "#008E97",
  MIN: "#4F2683", NE:  "#002244", NO:  "#D3BC8D", NYG: "#0B2265",
  NYJ: "#125740", PHI: "#004C54", PIT: "#FFB612", SEA: "#69BE28",
  SF:  "#AA0000", TB:  "#D50A0A", TEN: "#4B92DB", WAS: "#5A1414",
};

export function hexToRgb(hex: string): string {
  if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) return "0, 0, 0";
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r}, ${g}, ${b}`;
}
