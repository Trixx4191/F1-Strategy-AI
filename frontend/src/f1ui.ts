/** Official-ish Pirelli compound colours used across F1 graphics */
export const COMPOUND_STYLE: Record<
  string,
  { fill: string; text: string; border: string; label: string }
> = {
  SOFT: { fill: "#E10600", text: "#fff", border: "#E10600", label: "SOFT" },
  MEDIUM: { fill: "#FFD12E", text: "#111", border: "#FFD12E", label: "MEDIUM" },
  HARD: { fill: "#F0F0F0", text: "#111", border: "#C8C8C8", label: "HARD" },
  INTERMEDIATE: { fill: "#43B02A", text: "#fff", border: "#43B02A", label: "INTER" },
  INTER: { fill: "#43B02A", text: "#fff", border: "#43B02A", label: "INTER" },
  WET: { fill: "#00A0DE", text: "#fff", border: "#00A0DE", label: "WET" },
};

export function compoundStyle(c?: string | null) {
  const key = (c || "").toUpperCase().trim();
  return COMPOUND_STYLE[key] || { fill: "#444", text: "#fff", border: "#555", label: key || "?" };
}

/**
 * Map FastF1 / schedule event names to ISO country codes for flagcdn.
 * Covers common naming variants (e.g. "Dutch", "Netherlands", "Emilia Romagna").
 */
const RACE_TO_CC: Record<string, string> = {
  bahrain: "bh", sakhir: "bh",
  "saudi arabia": "sa", jeddah: "sa",
  australia: "au", melbourne: "au", albert: "au",
  japan: "jp", suzuka: "jp",
  china: "cn", shanghai: "cn",
  miami: "us",
  "emilia romagna": "it", imola: "it",
  monaco: "mc",
  canada: "ca", montreal: "ca",
  spain: "es", spanish: "es", barcelona: "es", catalunya: "es",
  austria: "at", spielberg: "at", styrian: "at",
  "great britain": "gb", british: "gb", silverstone: "gb", england: "gb",
  hungary: "hu", hungarian: "hu", budapest: "hu",
  belgium: "be", belgian: "be", spa: "be",
  netherlands: "nl", dutch: "nl", zandvoort: "nl",
  italy: "it", italian: "it", monza: "it",
  azerbaijan: "az", baku: "az",
  singapore: "sg",
  "united states": "us", austin: "us", americas: "us", "us ": "us",
  mexico: "mx", "mexico city": "mx",
  brazil: "br", "sao paulo": "br", "são paulo": "br", interlagos: "br",
  "las vegas": "us", vegas: "us",
  qatar: "qa", losail: "qa",
  "abu dhabi": "ae", yas: "ae",
  portugal: "pt", portimao: "pt",
  france: "fr", french: "fr",
  russia: "ru", sochi: "ru",
  turkey: "tr", turkish: "tr",
  eifel: "de", germany: "de", german: "de", nurburgring: "de", hockenheim: "de",
  toscana: "it", tuscany: "it", mugello: "it",
  "70th anniversary": "gb",
};

export function raceCountryCode(raceName: string): string | null {
  const n = (raceName || "").toLowerCase().replace(/grand prix|gp/gi, "").trim();
  if (!n) return null;
  for (const [key, cc] of Object.entries(RACE_TO_CC)) {
    if (n.includes(key)) return cc;
  }
  return null;
}

/** flagcdn.com — no API key, works in img tags */
export function flagUrl(cc: string, w = 40): string {
  return `https://flagcdn.com/w${w}/${cc.toLowerCase()}.png`;
}

export function flagUrlSvg(cc: string): string {
  return `https://flagcdn.com/${cc.toLowerCase()}.svg`;
}

/** Read chronological stints rather than a set-like compound summary. */
export function strategyCompounds(row: { strategy?: string; compound_sequence?: string[] }): string[] {
  const stints = [...(row.strategy || "").matchAll(/\b(SOFT|MEDIUM|HARD|INTERMEDIATE|INTER|WET)\s*\(/gi)].map((match) => match[1].toUpperCase());
  return stints.length ? stints : (row.compound_sequence || []).flatMap((compound) => compound.split(/\s*[→,+]\s*/)).filter(Boolean);
}

export function formatRaceTime(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const tenths = Math.round(seconds * 10);
  const hours = Math.floor(tenths / 36000);
  const minutes = Math.floor((tenths % 36000) / 600);
  const remainder = ((tenths % 600) / 10).toFixed(1).padStart(4, "0");
  return `${hours ? `${hours}:` : ""}${String(minutes).padStart(2, "0")}:${remainder}`;
}
