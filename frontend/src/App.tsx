import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type SessionData,
  type SimulateResult,
  type TimingRow,
  type RivalAnalysisResult,
  type DriverEntry,
  type StrategyRow,
} from "./api";
import {
  LineChart,
  ScatterChart,
  BarChart,
  EvTimeline,
  HeatStrip,
  TYRE,
  TRACE_COLORS,
} from "./Charts";
import {
  compoundStyle,
  raceCountryCode,
  flagUrl,
  strategyCompounds,
  formatRaceTime,
} from "./f1ui";
import "./index.css";

function CompoundPill({
  c,
  size = "md",
}: {
  c?: string | null;
  size?: "sm" | "md";
}) {
  const s = compoundStyle(c);
  return (
    <span
      className={`compound-pill${size === "sm" ? " sm" : ""}`}
      style={{ background: s.fill, color: s.text, borderColor: s.border }}
      title={s.label}
      aria-label={s.label}
    >
      {s.label[0]}
    </span>
  );
}

function CompoundSequence({
  compounds,
  strategy,
}: {
  compounds?: string[];
  strategy?: string;
}) {
  const list = strategyCompounds({ compound_sequence: compounds, strategy });
  if (!list.length) return <span className="muted">—</span>;
  return (
    <span className="compound-seq">
      {list.map((c, i) => (
        <span
          key={i}
          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
        >
          {i > 0 && <span className="arrow">→</span>}
          <CompoundPill c={c} />
        </span>
      ))}
    </span>
  );
}

function RaceFlag({ race, size = 22 }: { race: string; size?: number }) {
  const cc = raceCountryCode(race);
  if (!cc) return null;
  return (
    <span className={`flag-chip${size > 28 ? " lg" : ""}`}>
      <img
        src={flagUrl(cc, size >= 28 ? 80 : 40)}
        alt=""
        width={size}
        height={Math.round(size * 0.67)}
      />
    </span>
  );
}

/** Fallback only when no session roster yet — teams are NEVER trusted from this map. */
const DRIVER_FALLBACK: Record<string, string> = {
  VER: "VERSTAPPEN",
  NOR: "NORRIS",
  HAM: "HAMILTON",
  LEC: "LECLERC",
  RUS: "RUSSELL",
  PIA: "PIASTRI",
  SAI: "SAINZ",
  ALO: "ALONSO",
  STR: "STROLL",
  GAS: "GASLY",
  OCO: "OCON",
  ALB: "ALBON",
  BOT: "BOTTAS",
  HUL: "HULKENBERG",
  TSU: "TSUNODA",
  PER: "PEREZ",
  MAG: "MAGNUSSEN",
  RIC: "RICCIARDO",
  LAW: "LAWSON",
  BEA: "BEARMAN",
  COL: "COLAPINTO",
  DOO: "DOOHAN",
  ANT: "ANTONELLI",
  HAD: "HADJAR",
};

function rosterMap(
  entries?: DriverEntry[] | null,
): Record<string, DriverEntry> {
  const m: Record<string, DriverEntry> = {};
  for (const e of entries || []) {
    if (e?.code) m[e.code] = e;
  }
  return m;
}

function displayName(
  code: string,
  roster: Record<string, DriverEntry>,
): string {
  return roster[code]?.name || DRIVER_FALLBACK[code] || code;
}

function displayTeam(
  code: string,
  roster: Record<string, DriverEntry>,
): string {
  return roster[code]?.team || "";
}

type Status = "idle" | "loading" | "ready" | "error";
type Tab =
  | "overview"
  | "strategy"
  | "tyres"
  | "undercut"
  | "rival"
  | "backtest"
  | "results"
  | "saved";

type PersistedUiState = {
  year: number;
  race: string;
  driver: string;
  rival: string;
  nSims: number;
  strategyType: string;
  noise: number;
  useLiveTemp: boolean;
  manualTemp: number;
  tab: Tab;
  autoPersist: boolean;
};

type PersistedCurrentRun = {
  savedAt: number;
  state: PersistedUiState;
  result: SimulateResult;
};

type SavedRun = {
  id: string;
  label: string;
  createdAt: number;
  state: PersistedUiState;
  result: SimulateResult;
};

const STORAGE_KEYS = {
  current: "f1-strategy-ai.current-run.v1",
  saved: "f1-strategy-ai.saved-runs.v1",
  ui: "f1-strategy-ai.ui-state.v1",
};

function readFromStorage<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeToStorage(key: string, value: unknown): boolean {
  if (typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (e) {
    // Real, measured risk: a single /api/simulate response (252+ strategies,
    // tyre curves, lap traces, undercut heatmap) is ~900KB serialized.
    // Most browsers cap localStorage at 5-10MB per origin, so as few as
    // 5-10 saved runs can exceed quota. Silently swallowing this — the
    // previous behavior — means "Save" can appear to succeed while doing
    // nothing, with no way for the user to know their saves aren't
    // actually persisting. Callers now get a boolean so they can surface
    // a real error instead.
    console.warn(`localStorage write failed for "${key}":`, e);
    return false;
  }
}

function removeFromStorage(key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore storage failures gracefully
  }
}

function makeSavedRunId(): string {
  return `sim-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [runConfig, setRunConfig] = useState<PersistedUiState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [latestYear, setLatestYear] = useState(2025);
  const [year, setYear] = useState(2024);
  const [races, setRaces] = useState<string[]>([]);
  const [race, setRace] = useState("");
  const [driver, setDriver] = useState("VER");
  const [rival, setRival] = useState("NOR");
  const [nSims, setNSims] = useState(500);
  const [strategyType, setStrategyType] = useState("Both");
  const [noise, setNoise] = useState(0.3);
  const [status, setStatus] = useState<Status>("idle");
  // Separate from `status` above deliberately: `status` also tracks
  // session-load state (set to "loading" while fetching track/timing data
  // on race selection, before any simulation has run). The RUN button used
  // to read `status === "loading"` directly, which meant simply selecting
  // a race — no simulation involved at all — made the button show
  // "RUNNING…" and disable itself, looking exactly like a simulation was
  // running in the background when only lightweight session metadata was
  // being fetched. This tracks the actual /api/simulate call specifically.
  const [simRunning, setSimRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<SessionData | null>(null);
  const [sim, setSim] = useState<SimulateResult | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [useLiveTemp, setUseLiveTemp] = useState(true);
  const [manualTemp, setManualTemp] = useState(35);
  const [autoPersist, setAutoPersist] = useState(true);
  const [savedRuns, setSavedRuns] = useState<SavedRun[]>([]);
  const [selectedSavedIds, setSelectedSavedIds] = useState<string[]>([]);
  const [hasHydrated, setHasHydrated] = useState(false);
  const [rivalResult, setRivalResult] = useState<RivalAnalysisResult | null>(
    null,
  );
  const [rivalBusy, setRivalBusy] = useState(false);
  // Interactive rival params (dashboard Tab 5)
  const [rivalCompound, setRivalCompound] = useState(
    import.meta.env.VITE_DEMO_MODE === "true" ? "HARD" : "MEDIUM",
  );
  const [rivalTyreAge, setRivalTyreAge] = useState(10);
  const [gapToRival, setGapToRival] = useState(2.0);
  const [scanFrom, setScanFrom] = useState(15);
  const [scanTo, setScanTo] = useState(30);
  const [ourCompound, setOurCompound] = useState(
    import.meta.env.VITE_DEMO_MODE === "true" ? "SOFT" : "MEDIUM",
  );
  const [ourTyreAge, setOurTyreAge] = useState(10);
  const [newCompound, setNewCompound] = useState("HARD");

  useEffect(() => {
    const storedUi = readFromStorage<PersistedUiState>(STORAGE_KEYS.ui);
    const storedCurrent = readFromStorage<PersistedCurrentRun>(
      STORAGE_KEYS.current,
    );
    const storedSaves = readFromStorage<SavedRun[]>(STORAGE_KEYS.saved);

    if (storedUi) {
      setYear(
        import.meta.env.VITE_DEMO_MODE === "true"
          ? 2024
          : storedUi.year || 2024,
      );
      setRace(
        import.meta.env.VITE_DEMO_MODE === "true"
          ? "Bahrain"
          : storedUi.race || "",
      );
      setDriver(storedUi.driver || "VER");
      setRival(storedUi.rival || "NOR");
      setNSims(storedUi.nSims || 500);
      setStrategyType(storedUi.strategyType || "Both");
      setNoise(storedUi.noise ?? 0.3);
      setUseLiveTemp(storedUi.useLiveTemp ?? true);
      setManualTemp(storedUi.manualTemp ?? 35);
      setTab(storedUi.tab || "overview");
      setAutoPersist(storedUi.autoPersist ?? true);
    }

    if (storedCurrent?.result) {
      setSim(storedCurrent.result);
      setRunConfig(storedCurrent.state);
      setSession({
        year: storedCurrent.result.year,
        race: storedCurrent.result.race,
        race_laps: storedCurrent.result.race_laps,
        timing: storedCurrent.result.timing,
        circuit: storedCurrent.result.circuit,
        weather: storedCurrent.result.weather,
        session_drivers: storedCurrent.result.session_drivers,
        drivers: storedCurrent.result.drivers,
      });
      setStatus("ready");
    }

    if (Array.isArray(storedSaves)) {
      setSavedRuns(storedSaves);
    }

    setHasHydrated(true);
    api
      .latestSeason()
      .then((r) => {
        setLatestYear(r.year);
        setYear((prev) =>
          import.meta.env.VITE_DEMO_MODE === "true" ? 2024 : prev || r.year,
        );
        if (import.meta.env.VITE_DEMO_MODE === "true") setRace("Bahrain");
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!hasHydrated) return;
    writeToStorage(STORAGE_KEYS.ui, {
      year,
      race,
      driver,
      rival,
      nSims,
      strategyType,
      noise,
      useLiveTemp,
      manualTemp,
      tab,
      autoPersist,
    });
  }, [
    hasHydrated,
    year,
    race,
    driver,
    rival,
    nSims,
    strategyType,
    noise,
    useLiveTemp,
    manualTemp,
    tab,
    autoPersist,
  ]);

  useEffect(() => {
    if (!hasHydrated) return;
    if (autoPersist && sim) {
      // Deliberately NOT depending on year/race/driver/... /tab here —
      // those are read from the closure at write time, which is correct
      // (the persisted "current run" should reflect whatever parameters
      // produced THIS sim result). Including them as dependencies meant
      // this ~900KB payload was being re-serialized and re-written to
      // localStorage on every tab switch and slider tweak, not just when
      // a new simulation actually completed — real, avoidable overhead
      // on every minor UI interaction.
      const ok = writeToStorage(STORAGE_KEYS.current, {
        savedAt: Date.now(),
        state: runConfig ?? {
          year,
          race,
          driver,
          rival,
          nSims,
          strategyType,
          noise,
          useLiveTemp,
          manualTemp,
          tab,
          autoPersist,
        },
        result: sim,
      });
      if (!ok) {
        setError(
          "Couldn't auto-save this run — browser storage is full. Delete " +
            "an old saved run, or turn off auto-save, and try again.",
        );
      }
    } else if (!autoPersist) {
      removeFromStorage(STORAGE_KEYS.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHydrated, autoPersist, sim, runConfig]);

  useEffect(() => {
    if (!hasHydrated) return;
    if (savedRuns.length === 0) {
      // Nothing to persist, and no point warning about a write that would
      // never fail anyway (an empty array serializes to a couple bytes).
      writeToStorage(STORAGE_KEYS.saved, savedRuns);
      return;
    }
    const ok = writeToStorage(STORAGE_KEYS.saved, savedRuns);
    if (!ok) {
      setError(
        "Couldn't save this run — browser storage is full. Delete an old " +
          "saved run and try again.",
      );
    }
  }, [hasHydrated, savedRuns]);

  // (Duplicate `api.latestSeason()` fetch removed here — the hydration
  // effect earlier in this file already fetches it once on mount; this
  // second copy fired the same request a second time on every page load.)

  useEffect(() => {
    if (!year) return;
    api
      .races(year)
      .then((r) => {
        setRaces(r.races);
        setRace((prev) => prev || r.races[0] || "");
      })
      .catch((e) => setError(String(e.message || e)));
  }, [year]);

  useEffect(() => {
    if (!year || !race) return;
    let active = true;
    setStatus("loading");
    setError(null);
    setSim(null);
    api
      .session(year, race)
      .then((data) => {
        if (!active) return;
        setSession(data);
        setStatus("idle");
        if (
          import.meta.env.VITE_DEMO_MODE === "true" &&
          year === 2024 &&
          race === "Bahrain"
        ) {
          const saved = readFromStorage<PersistedCurrentRun>(
            STORAGE_KEYS.current,
          );
          const initialRun =
            saved?.result?.year === year && saved.result.race === race
              ? Promise.resolve(saved.result)
              : api.demoRun();
          initialRun
            .then((result) => {
              if (!active) return;
              setSim(result);
              setRunConfig(
                saved?.result?.year === year && saved.result.race === race
                  ? saved.state
                  : {
                      year,
                      race,
                      driver: result.driver,
                      rival: result.rival.rival_code,
                      nSims: result.n_simulations,
                      strategyType: "Both",
                      noise: 0.3,
                      useLiveTemp: true,
                      manualTemp: 35,
                      tab: "overview",
                      autoPersist: true,
                    },
              );
              setDriver(result.driver);
              if (!saved?.result) {
                setRival("NOR");
                setNSims(500);
                setStrategyType("Both");
                setNoise(0.3);
                setUseLiveTemp(true);
              }
              setStatus("ready");
            })
            .catch((error: unknown) => {
              if (active) {
                setStatus("error");
                setError(
                  error instanceof Error ? error.message : String(error),
                );
              }
            });
        }
        const codes = (data.drivers || []).map((d) => d.code);
        if (codes.length) {
          if (!codes.includes(driver)) setDriver(codes[0]);
          if (!codes.includes(rival) || rival === codes[0]) {
            setRival(
              codes.find(
                (c) => c !== (codes.includes(driver) ? driver : codes[0]),
              ) || codes[0],
            );
          }
        }
      })
      .catch((e) => {
        if (active) {
          setSession(null);
          setStatus("error");
          setError(String(e.message || e));
        }
      });
    return () => {
      active = false;
    };
  }, [year, race]);

  const saveCurrentRunToSavedList = useCallback(() => {
    if (!sim) return;
    const item: SavedRun = {
      id: makeSavedRunId(),
      label: `${sim.race} · ${sim.driver} · ${new Date().toLocaleString([], { dateStyle: "short", timeStyle: "short" })}`,
      createdAt: Date.now(),
      state: runConfig ?? {
        year,
        race,
        driver,
        rival,
        nSims,
        strategyType,
        noise,
        useLiveTemp,
        manualTemp,
        tab,
        autoPersist,
      },
      result: sim,
    };
    // Each saved run is a full /api/simulate response — measured at
    // ~900KB serialized for a typical race (252+ strategies, tyre curves,
    // lap traces, undercut heatmap). Most browsers cap localStorage at
    // 5-10MB per origin, so unbounded saves will eventually blow the
    // quota. Capping at MAX_SAVED_RUNS and evicting the oldest keeps
    // total storage well within that limit rather than discovering the
    // failure only after it silently happens. The actual persistence
    // (and quota-failure detection) happens in the effect below that
    // watches `savedRuns`, so this stays a single write path.
    const MAX_SAVED_RUNS = 5;
    const next = [item, ...savedRuns].slice(0, MAX_SAVED_RUNS);
    if (!writeToStorage(STORAGE_KEYS.saved, next)) {
      setError(
        "Could not save: browser storage is full. Delete an older saved run and try again.",
      );
      return;
    }
    setSavedRuns(next);
    setNotice("Run saved in this browser. Find it in Saved runs.");
  }, [
    sim,
    year,
    race,
    driver,
    rival,
    nSims,
    strategyType,
    noise,
    useLiveTemp,
    manualTemp,
    tab,
    autoPersist,
    savedRuns,
    runConfig,
  ]);

  const resetCurrentRun = useCallback(() => {
    setSim(null);
    setRunConfig(null);
    setStatus("idle");
    setError(null);
    setRivalResult(null);
    setTab("overview");
    removeFromStorage(STORAGE_KEYS.current);
  }, []);

  const runSim = useCallback(async () => {
    if (!year || !race) return;
    setStatus("loading");
    setError(null);
    setNotice(null);
    setSimRunning(true);
    try {
      const result = await api.simulate({
        year,
        race,
        driver,
        rival,
        n_simulations: nSims,
        strategy_type: strategyType,
        noise_std: noise,
        use_live_temp: useLiveTemp,
        ...(useLiveTemp ? {} : { track_temp_override: manualTemp }),
      } as any);
      setSim(result);
      setRunConfig({
        year,
        race,
        driver,
        rival,
        nSims,
        strategyType,
        noise,
        useLiveTemp,
        manualTemp,
        tab: "overview",
        autoPersist,
      });
      setRivalResult(null);
      setSettingsOpen(false);
      setSession({
        year: result.year,
        race: result.race,
        race_laps: result.race_laps,
        timing: result.timing,
        circuit: result.circuit,
        weather: result.weather,
        session_drivers: result.session_drivers,
        drivers: result.drivers,
      });
      setStatus("ready");
      setTab("overview");
    } catch (e: unknown) {
      setStatus(sim ? "ready" : "error");
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSimRunning(false);
    }
  }, [
    year,
    race,
    driver,
    rival,
    nSims,
    strategyType,
    noise,
    useLiveTemp,
    manualTemp,
    sim,
    autoPersist,
  ]);

  useEffect(() => {
    setRivalResult(null);
  }, [
    year,
    race,
    driver,
    rival,
    rivalCompound,
    rivalTyreAge,
    gapToRival,
    scanFrom,
    scanTo,
    ourCompound,
    ourTyreAge,
    newCompound,
    noise,
  ]);

  const timing: TimingRow[] = useMemo(() => {
    const rmap = rosterMap(sim?.drivers ?? session?.drivers);
    return (sim?.timing ?? session?.timing ?? []).map((r) => ({
      ...r,
      team_color: r.team_color || rmap[r.driver]?.team_color || "#888",
      name:
        r.name || rmap[r.driver]?.name || DRIVER_FALLBACK[r.driver] || r.driver,
      team: r.team || rmap[r.driver]?.team || "",
    }));
  }, [session, sim]);

  const roster = useMemo(
    () => rosterMap(sim?.drivers ?? session?.drivers),
    [sim?.drivers, session?.drivers],
  );
  const driverCodes = useMemo(() => {
    const fromSession = sim?.session_drivers ?? session?.session_drivers;
    if (fromSession && fromSession.length) return fromSession;
    return Object.keys(roster);
  }, [sim?.session_drivers, session?.session_drivers, roster]);

  const weather = sim?.weather ?? session?.weather;
  const circuit = sim?.circuit ?? session?.circuit;
  const raceLaps = sim?.race_laps ?? session?.race_laps ?? 0;
  const strategies = sim?.strategies ?? [];
  const tyreSummary = sim?.tyre_summary ?? [];
  const rivalData = sim?.rival;
  const yearOptions = Array.from(
    { length: Math.max(1, latestYear - 2017) },
    (_, i) => latestYear - i,
  );
  const rivalOptions = (
    driverCodes.length ? driverCodes : Object.keys(DRIVER_FALLBACK)
  ).filter((d) => d !== driver);

  const settingsChanged =
    !!sim &&
    !!runConfig &&
    (year !== runConfig.year ||
      race !== runConfig.race ||
      driver !== runConfig.driver ||
      rival !== runConfig.rival ||
      nSims !== runConfig.nSims ||
      strategyType !== runConfig.strategyType ||
      noise !== runConfig.noise ||
      useLiveTemp !== runConfig.useLiveTemp ||
      (!useLiveTemp && manualTemp !== runConfig.manualTemp));
  const resultDriver = sim?.driver ?? driver;
  const resultRace = sim?.race ?? race;
  const busy = simRunning || rivalBusy;

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "strategy", label: "Strategy" },
    { id: "tyres", label: "Tyres" },
    { id: "undercut", label: "Pit windows" },
    { id: "rival", label: "Rival analysis" },
    { id: "backtest", label: "Backtest" },
    { id: "results", label: "Results" },
    { id: "saved", label: "Saved runs" },
  ];

  function exportCsv() {
    if (!strategies.length) return;
    const cols = [
      "rank",
      "strategy",
      "compound_sequence",
      "pit_laps",
      "pit_count",
      "mean_time",
      "std_time",
      "p10",
      "p50",
      "p90",
      "win_rate",
    ];
    const lines = [cols.join(",")];
    for (const s of strategies) {
      lines.push(
        [
          s.rank,
          `"${(s.strategy || s.compound_sequence.join("→")).replace(/"/g, '""')}"`,
          `"${strategyCompounds(s).join("→")}"`,
          `"${(s.pit_laps || []).join(" ")}"`,
          s.pit_count ?? "",
          s.mean_time ?? "",
          s.std_time ?? "",
          s.p10 ?? "",
          s.p50 ?? "",
          s.p90 ?? "",
          s.win_rate ?? "",
        ].join(","),
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `f1_strategy_${sim?.year ?? year}_${resultRace}_${resultDriver}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="app">
      <a className="skip-link" href="#analysis">
        Skip to analysis
      </a>
      <aside
        className={`sidebar${settingsOpen ? " is-open" : ""}`}
        aria-label="Simulation settings"
      >
        <div className="sidebar-brand">
          <a
            className="brand"
            href="#"
            onClick={(event) => {
              event.preventDefault();
              setTab("overview");
            }}
          >
            <span className="brand-mark" aria-hidden="true">
              F1
            </span>
            <span>
              STRATEGY
              <span className="brand-subtitle">Race strategy analysis</span>
            </span>
          </a>
          <button
            className="settings-toggle btn-export"
            aria-expanded={settingsOpen}
            aria-controls="simulation-settings"
            onClick={() => setSettingsOpen(!settingsOpen)}
          >
            {settingsOpen ? "Close settings" : "Settings"}
          </button>
        </div>
        <div className="settings-panel" id="simulation-settings">
          <fieldset disabled={busy} className="settings-fields">
            <legend className="sb-section">Race setup</legend>
            {import.meta.env.VITE_DEMO_MODE === "true" ? (
              <div className="session-card">
                <RaceFlag race="Bahrain" />
                <div>
                  <strong>Bahrain Grand Prix</strong>
                  <span>2024 · Historical race data</span>
                </div>
              </div>
            ) : (
              <>
                <div className="sb-field">
                  <label htmlFor="season">Season</label>
                  <select
                    id="season"
                    value={year}
                    onChange={(e) => {
                      setYear(Number(e.target.value));
                      setRace("");
                    }}
                  >
                    {yearOptions.map((y) => (
                      <option key={y}>{y}</option>
                    ))}
                  </select>
                </div>
                <div className="sb-field">
                  <label htmlFor="race">Grand Prix</label>
                  <select
                    id="race"
                    value={race}
                    onChange={(e) => setRace(e.target.value)}
                  >
                    {races.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                </div>
              </>
            )}
            <div className="sb-field">
              <label htmlFor="driver">Driver</label>
              <select
                id="driver"
                value={driver}
                onChange={(e) => {
                  const next = e.target.value;
                  setDriver(next);
                  setRivalResult(null);
                  if (rival === next) setRival(driver);
                }}
              >
                {(driverCodes.length
                  ? driverCodes
                  : Object.keys(DRIVER_FALLBACK)
                ).map((d) => (
                  <option key={d} value={d}>
                    {d} · {displayName(d, roster)}
                  </option>
                ))}
              </select>
            </div>
            <div className="sb-field">
              <label htmlFor="rival">Compare against</label>
              <select
                id="rival"
                value={rival}
                onChange={(e) => {
                  setRival(e.target.value);
                  setRivalResult(null);
                }}
              >
                {rivalOptions.map((d) => (
                  <option key={d} value={d}>
                    {d} · {displayName(d, roster)}
                  </option>
                ))}
              </select>
            </div>
            <div className="sb-section">Simulation</div>
            <div className="sb-field">
              <label htmlFor="strategy-type">Pit stops</label>
              <select
                id="strategy-type"
                value={strategyType}
                onChange={(e) => setStrategyType(e.target.value)}
              >
                <option value="1-stop">One stop</option>
                <option value="2-stop">Two stops</option>
                <option value="Both">Compare one & two stops</option>
              </select>
            </div>
            <div className="sb-field">
              <label htmlFor="iterations">
                Iterations per strategy{" "}
                <output>{nSims.toLocaleString()}</output>
              </label>
              <input
                id="iterations"
                type="range"
                min={100}
                max={2000}
                step={100}
                value={nSims}
                onChange={(e) => setNSims(Number(e.target.value))}
              />
              <p className="field-hint">
                More iterations take longer to calculate.
              </p>
            </div>
            <details className="advanced-settings">
              <summary>Advanced settings</summary>
              <div className="sb-field">
                <label htmlFor="noise">
                  Lap variability <output>{noise.toFixed(2)} s</output>
                </label>
                <input
                  id="noise"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={noise}
                  onChange={(e) => setNoise(Number(e.target.value))}
                />
              </div>
              <div className="sb-field">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={useLiveTemp}
                    onChange={(e) => setUseLiveTemp(e.target.checked)}
                  />
                  Use recorded track temperature
                </label>
              </div>
              {!useLiveTemp && (
                <div className="sb-field">
                  <label htmlFor="temperature">
                    Track temperature <output>{manualTemp}°C</output>
                  </label>
                  <input
                    id="temperature"
                    type="range"
                    min={15}
                    max={55}
                    value={manualTemp}
                    onChange={(e) => setManualTemp(Number(e.target.value))}
                  />
                </div>
              )}
              <div className="sb-field">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={autoPersist}
                    onChange={(e) => setAutoPersist(e.target.checked)}
                  />
                  Remember current run in this browser
                </label>
              </div>
              {sim && (
                <div className="sb-field">
                  <button className="text-button" onClick={resetCurrentRun}>
                    Clear current results
                  </button>
                </div>
              )}
            </details>
          </fieldset>
          <div className="sidebar-actions">
            <button
              className="btn-run"
              disabled={busy || status === "loading" || !race}
              onClick={runSim}
            >
              {simRunning ? "Simulating…" : "Run simulation"}
              <span aria-hidden="true">↗</span>
            </button>
            {sim && (
              <button
                className="btn-export save-run"
                disabled={busy || settingsChanged}
                onClick={saveCurrentRunToSavedList}
              >
                Save run
              </button>
            )}
          </div>
          <p className="sidebar-note">
            {import.meta.env.VITE_DEMO_MODE === "true"
              ? "Bahrain 2024 demo. Starts with a completed 500-iteration run; run again to test your settings."
              : "Compare tyre strategies using recorded race data and Monte Carlo simulation."}
          </p>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="race-heading">
            <span className="eyebrow">
              {import.meta.env.VITE_DEMO_MODE === "true"
                ? "Historical race · 2024"
                : `Race analysis · ${year}`}
            </span>
            <h1>
              {race || "Choose a race"}
              <span> Grand Prix</span>
            </h1>
          </div>
          <div className="race-conditions">
            <span>
              <strong>{raceLaps || "—"}</strong> laps
            </span>
            <span>
              <strong>
                {weather?.track_temp != null
                  ? `${weather.track_temp.toFixed(0)}°C`
                  : "—"}
              </strong>{" "}
              track
            </span>
            <span className="historical-tag">
              {weather?.rainfall ? "Wet conditions" : "Historical data"}
            </span>
          </div>
        </header>
        <div className="analysis-heading">
          <div>
            <span className="eyebrow">Strategy workspace</span>
            <h2>{tabs.find((t) => t.id === tab)?.label}</h2>
          </div>
          <span className="run-status" role="status">
            {simRunning
              ? "Calculating simulation…"
              : rivalBusy
                ? "Calculating rival analysis…"
                : status === "loading"
                  ? "Loading race data…"
                  : sim
                    ? `${resultDriver} · ${sim.n_simulations.toLocaleString()} iterations · ${strategies.length.toLocaleString()} strategies`
                    : "Ready to simulate"}
          </span>
        </div>
        {error && (
          <div className="error-box" role="alert">
            {error}
            <button
              className="text-button"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
            >
              Dismiss
            </button>
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            {notice}
            <button
              className="text-button"
              onClick={() => setNotice(null)}
              aria-label="Dismiss notification"
            >
              Dismiss
            </button>
          </div>
        )}
        {settingsChanged && (
          <div className="settings-notice" role="status">
            <strong>Settings changed.</strong> Results below are from{" "}
            {resultDriver} vs {sim?.rival.rival_code}. Run a simulation to apply
            the new settings.
          </div>
        )}
        <nav className="tab-bar" aria-label="Analysis sections">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={`tab-btn${tab === t.id ? " active" : ""}`}
              aria-current={tab === t.id ? "page" : undefined}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <main className="tab-content" id="analysis" tabIndex={-1}>
          {[
            {
              id: "overview",
              panel: (
                <Overview
                  timing={timing}
                  driver={resultDriver}
                  circuit={circuit}
                  race={resultRace}
                  strategies={strategies}
                  raceLaps={raceLaps}
                  status={status}
                  weather={weather}
                  pitLoss={sim?.pit_loss}
                  optimal={sim?.optimal_strategy}
                  stopComparison={sim?.stop_comparison}
                  roster={roster}
                  onNavigate={setTab}
                />
              ),
            },
            {
              id: "strategy",
              panel: (
                <StrategyTab
                  strategies={strategies}
                  lapTraces={sim?.lap_traces ?? []}
                  ready={!!sim && !simRunning}
                  stopComparison={sim?.stop_comparison}
                  optimal={sim?.optimal_strategy}
                />
              ),
            },
            {
              id: "tyres",
              panel: (
                <TyresTab
                  curves={sim?.tyre_curves ?? []}
                  scatter={sim?.stint_scatter ?? []}
                  phaseSlopes={sim?.phase_slopes ?? []}
                  summary={sim?.model_summary ?? []}
                  tyreSummary={tyreSummary}
                />
              ),
            },
            {
              id: "undercut",
              panel: (
                <UndercutTab strategies={strategies} rivalData={rivalData} />
              ),
            },
            {
              id: "rival",
              panel: (
                <RivalTab
                  rival={
                    rivalData?.rival_code === rival && sim?.driver === driver
                      ? rivalData
                      : undefined
                  }
                  fallbackRival={rival}
                  rivalResult={rivalResult}
                  rivalBusy={busy}
                  year={year}
                  race={race}
                  driver={driver}
                  raceLaps={raceLaps}
                  circuit={circuit}
                  rivalCompound={rivalCompound}
                  setRivalCompound={setRivalCompound}
                  rivalTyreAge={rivalTyreAge}
                  setRivalTyreAge={setRivalTyreAge}
                  gapToRival={gapToRival}
                  setGapToRival={setGapToRival}
                  scanFrom={scanFrom}
                  setScanFrom={setScanFrom}
                  scanTo={scanTo}
                  setScanTo={setScanTo}
                  ourCompound={ourCompound}
                  setOurCompound={setOurCompound}
                  ourTyreAge={ourTyreAge}
                  setOurTyreAge={setOurTyreAge}
                  newCompound={newCompound}
                  setNewCompound={setNewCompound}
                  noise={noise}
                  onRunRival={async () => {
                    setRivalBusy(true);
                    setError(null);
                    try {
                      const r = await api.rivalAnalysis({
                        year,
                        race,
                        driver,
                        rival,
                        rival_compound: rivalCompound,
                        rival_tyre_age: rivalTyreAge,
                        gap_to_rival: gapToRival,
                        scan_from_lap: scanFrom,
                        scan_to_lap: scanTo,
                        our_compound: ourCompound,
                        our_tyre_age: ourTyreAge,
                        new_compound: newCompound,
                        n_simulations: Math.min(200, nSims),
                        noise_std: noise,
                        run_h2h: true,
                      });
                      setRivalResult(r);
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : String(e));
                    } finally {
                      setRivalBusy(false);
                    }
                  }}
                />
              ),
            },
            {
              id: "backtest",
              panel: (
                <BacktestTab
                  backtest={sim?.backtest ?? null}
                  driver={resultDriver}
                  circuit={circuit}
                  race={resultRace}
                />
              ),
            },
            {
              id: "results",
              panel: (
                <ResultsTab
                  strategies={strategies}
                  onExport={exportCsv}
                  ready={!!sim && !simRunning}
                />
              ),
            },
            {
              id: "saved",
              panel: (
                <SavedRunsTab
                  savedRuns={savedRuns}
                  selectedIds={selectedSavedIds}
                  onToggleSelect={(id) => {
                    setSelectedSavedIds((prev) =>
                      prev.includes(id)
                        ? prev.filter((x) => x !== id)
                        : [...prev, id],
                    );
                  }}
                  onLoad={(run) => {
                    setSim(run.result);
                    setRunConfig(run.state);
                    setRivalResult(null);
                    setStatus("ready");
                    setSession({
                      year: run.result.year,
                      race: run.result.race,
                      race_laps: run.result.race_laps,
                      timing: run.result.timing,
                      circuit: run.result.circuit,
                      weather: run.result.weather,
                      session_drivers: run.result.session_drivers,
                      drivers: run.result.drivers,
                    });
                    setYear(run.state.year);
                    setRace(run.state.race);
                    setDriver(run.state.driver);
                    setRival(run.state.rival);
                    setNSims(run.state.nSims);
                    setStrategyType(run.state.strategyType);
                    setNoise(run.state.noise);
                    setUseLiveTemp(run.state.useLiveTemp);
                    setManualTemp(run.state.manualTemp);
                    setTab("overview");
                  }}
                  onDelete={(id) => {
                    setSavedRuns((prev) => prev.filter((run) => run.id !== id));
                    setSelectedSavedIds((prev) => prev.filter((x) => x !== id));
                  }}
                  onClearAll={() => {
                    setSavedRuns([]);
                    setSelectedSavedIds([]);
                    removeFromStorage(STORAGE_KEYS.saved);
                  }}
                />
              ),
            },
          ]
            .filter((pane) => pane.id === tab)
            .map((pane) => (
              <div
                key={pane.id}
                style={{ display: tab === pane.id ? "block" : "none" }}
              >
                {pane.panel}
              </div>
            ))}
        </main>

        <div className="footer-note">
          Race data: FastF1 · Results are model estimates · Replay illustrates
          simulated pace
        </div>
      </div>
    </div>
  );
}

function SavedRunsTab({
  savedRuns,
  selectedIds,
  onToggleSelect,
  onLoad,
  onDelete,
  onClearAll,
}: {
  savedRuns: SavedRun[];
  selectedIds: string[];
  onToggleSelect: (id: string) => void;
  onLoad: (run: SavedRun) => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
}) {
  const selected = savedRuns.filter((run) => selectedIds.includes(run.id));
  const comparable = selected.every(
    (run) =>
      run.result.year === selected[0]?.result.year &&
      run.result.race === selected[0]?.result.race &&
      run.result.driver === selected[0]?.result.driver,
  );
  return (
    <div className="detail-grid">
      <section className="panel span-full">
        <div className="panel-header">
          <span className="title">Saved simulations</span>
          <span>{savedRuns.length} saved in this browser</span>
        </div>
        <div className="panel-body">
          {!savedRuns.length ? (
            <div className="empty-state">
              <h3>No saved runs yet</h3>
              <p>
                Save a completed simulation to compare its settings and results
                here. Runs are stored on this device.
              </p>
            </div>
          ) : (
            <>
              <p className="section-description">
                Select two or more runs to compare. The five most recent saves
                are kept, subject to browser storage space.
              </p>
              {savedRuns.map((run) => (
                <div key={run.id} className="saved-run-row">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(run.id)}
                    onChange={() => onToggleSelect(run.id)}
                    aria-label={`Select ${run.label}`}
                  />
                  <div>
                    <strong>
                      {run.result.driver} · {run.result.race} {run.result.year}
                    </strong>
                    <div className="muted">
                      {run.result.n_simulations} iterations ·{" "}
                      {new Date(run.createdAt).toLocaleString([], {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </div>
                  </div>
                  <div className="saved-time">
                    {formatRaceTime(run.result.optimal_strategy?.mean_time)}
                  </div>
                  <button className="btn-export" onClick={() => onLoad(run)}>
                    Load
                  </button>
                  <button
                    className="text-button"
                    onClick={() => onDelete(run.id)}
                  >
                    Delete
                  </button>
                </div>
              ))}
              <div className="saved-actions">
                <button
                  className="btn-export"
                  disabled={selected.length < 2}
                  onClick={() =>
                    document
                      .getElementById("saved-compare-panel")
                      ?.scrollIntoView({ behavior: "smooth", block: "start" })
                  }
                >
                  Compare selected ({selected.length})
                </button>
                <button className="text-button" onClick={onClearAll}>
                  Clear saved runs
                </button>
              </div>
            </>
          )}
        </div>
      </section>
      {selected.length >= 2 && (
        <section id="saved-compare-panel" className="panel span-full">
          <div className="panel-header">
            <span className="title">Side-by-side comparison</span>
            <span>{selected.length} runs</span>
          </div>
          <div className="panel-body">
            {!comparable && (
              <p className="section-description">
                These runs use different drivers or races. Their total race
                times are not directly comparable.
              </p>
            )}
            <div className="saved-comparison-grid">
              {selected.map((run) => (
                <article key={run.id} className="ev-block">
                  <h3 className="saved-run-title">
                    {run.result.driver} · {run.result.race}
                  </h3>
                  <p className="section-description">
                    {run.result.n_simulations} iterations ·{" "}
                    {run.state.strategyType === "Both"
                      ? "One & two stops"
                      : run.state.strategyType}
                  </p>
                  <dl className="saved-facts">
                    <div>
                      <dt>Best strategy</dt>
                      <dd>
                        <CompoundSequence
                          compounds={
                            run.result.optimal_strategy?.compound_sequence
                          }
                          strategy={run.result.optimal_strategy?.strategy}
                        />
                      </dd>
                    </div>
                    <div>
                      <dt>Expected race time</dt>
                      <dd>
                        {formatRaceTime(run.result.optimal_strategy?.mean_time)}
                      </dd>
                    </div>
                    <div>
                      <dt>Pit laps</dt>
                      <dd>
                        {run.result.optimal_strategy?.pit_laps.join(" / ") ||
                          "—"}
                      </dd>
                    </div>
                    <div>
                      <dt>Lap variability</dt>
                      <dd>{run.state.noise.toFixed(2)} s</dd>
                    </div>
                    <div>
                      <dt>Track temperature</dt>
                      <dd>
                        {run.state.useLiveTemp
                          ? "Recorded"
                          : `${run.state.manualTemp}°C`}
                      </dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function Overview({
  timing,
  driver,
  circuit,
  race,
  strategies,
  raceLaps,
  status,
  weather,
  pitLoss,
  optimal,
  stopComparison,
  roster = {},
  onNavigate,
}: any) {
  const sequence = optimal ? strategyCompounds(optimal) : [];
  const pitLaps: number[] = optimal?.pit_laps || [];
  const boundaries = [0, ...pitLaps, raceLaps];
  return (
    <div className="overview-layout">
      <section className="panel recommendation">
        <div className="panel-header">
          <span className="title">Recommended strategy</span>
          <span>
            {driver} · {displayTeam(driver, roster)}
          </span>
        </div>
        <div className="panel-body">
          {optimal ? (
            <>
              <div className="recommendation-top">
                <div>
                  <span className="eyebrow">Lowest expected race time</span>
                  <h3>
                    {pitLaps.length === 1
                      ? "One"
                      : pitLaps.length === 2
                        ? "Two"
                        : pitLaps.length}{" "}
                    stop{pitLaps.length !== 1 ? "s" : ""}
                    <span className="strategy-sequence">
                      <CompoundSequence compounds={sequence} />
                    </span>
                  </h3>
                </div>
                <div className="race-time">
                  <strong>{formatRaceTime(optimal.mean_time)}</strong>
                  <span>Expected race time</span>
                </div>
              </div>
              <div className="stint-plan" aria-label="Recommended tyre stints">
                {sequence.map((compound, i) => (
                  <div
                    className="stint"
                    key={i}
                    style={{
                      flex: Math.max(
                        1,
                        (boundaries[i + 1] || raceLaps) - boundaries[i],
                      ),
                      borderTopColor: compoundStyle(compound).fill,
                    }}
                  >
                    <strong>{compoundStyle(compound).label}</strong>
                    <span>
                      L{boundaries[i] + 1}–{boundaries[i + 1] || raceLaps}
                    </span>
                  </div>
                ))}
              </div>
              <div className="recommendation-facts">
                <div>
                  <span>Pit on lap{pitLaps.length !== 1 ? "s" : ""}</span>
                  <strong>{pitLaps.join(" & ") || "No stop"}</strong>
                </div>
                <div>
                  <span>Race time variability</span>
                  <strong>
                    {optimal.std_time != null
                      ? `±${optimal.std_time.toFixed(2)} s`
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>Estimated pit loss</span>
                  <strong>
                    {pitLoss != null ? `${pitLoss.toFixed(1)} s` : "—"}
                  </strong>
                </div>
              </div>
              <p className="field-hint">
                Fastest expected strategy among those tested. Variability is one
                standard deviation across simulations.
              </p>
              <button
                className="text-button"
                onClick={() => onNavigate("strategy")}
              >
                Compare strategy performance <span aria-hidden="true">→</span>
              </button>
            </>
          ) : (
            <div className="empty-state">
              <h3>
                {status === "loading"
                  ? "Loading race data…"
                  : "Set up your first simulation"}
              </h3>
              <p>
                Choose a driver and pit-stop options, then run a simulation to
                compare strategies.
              </p>
            </div>
          )}
        </div>
      </section>
      <section className="panel circuit-panel">
        <div className="panel-header">
          <span className="title">{race} circuit</span>
          <span>{raceLaps} laps</span>
        </div>
        <div className="panel-body circuit-body">
          <TrackOutline circuit={circuit} />
          <div className="circuit-facts">
            <span>
              {weather?.track_temp != null
                ? `${weather.track_temp.toFixed(0)}°C track`
                : "Temperature unavailable"}
            </span>
            <span>{weather?.rainfall ? "Wet" : "Dry"} session</span>
          </div>
          <p className="field-hint">Recorded circuit geometry · FastF1</p>
        </div>
      </section>
      <section className="panel span-full">
        <div className="panel-header">
          <span className="title">Leading strategies</span>
          <button className="text-button" onClick={() => onNavigate("results")}>
            All {strategies.length.toLocaleString()} results →
          </button>
        </div>
        <div className="panel-body no-pad table-scroll">
          <table className="data-table strategy-table">
            <caption className="sr-only">
              Top five strategies ranked by expected race time
            </caption>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Tyre sequence</th>
                <th>Pit laps</th>
                <th>Race time</th>
                <th>Gap to best</th>
              </tr>
            </thead>
            <tbody>
              {strategies.slice(0, 5).map((row: StrategyRow) => (
                <tr key={row.rank}>
                  <td className="rank-cell">
                    {String(row.rank).padStart(2, "0")}
                  </td>
                  <td>
                    <CompoundSequence
                      compounds={row.compound_sequence}
                      strategy={row.strategy}
                    />
                  </td>
                  <td>{row.pit_laps.join(" / ") || "—"}</td>
                  <td>{formatRaceTime(row.mean_time)}</td>
                  <td className={row.rank === 1 ? "best-value" : "muted"}>
                    {row.rank === 1
                      ? "Best"
                      : row.mean_time != null && optimal?.mean_time != null
                        ? `+${(row.mean_time - optimal.mean_time).toFixed(2)} s`
                        : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!strategies.length && (
            <p className="empty-state">Simulation results will appear here.</p>
          )}
        </div>
      </section>
      {stopComparison?.faster && (
        <p className="comparison-note">
          <strong>
            {stopComparison.faster === "1-stop" ? "One stop" : "Two stops"}
          </strong>{" "}
          is faster by {stopComparison.delta_seconds?.toFixed(2)} s in this
          model.{" "}
          <button
            className="text-button"
            onClick={() => onNavigate("strategy")}
          >
            View comparison →
          </button>
        </p>
      )}
      <details className="panel classification span-full">
        <summary>
          Recorded race classification <span>{timing.length} drivers</span>
        </summary>
        <div className="table-scroll">
          <table className="data-table">
            <caption className="sr-only">
              Historical race classification, separate from simulation results
            </caption>
            <thead>
              <tr>
                <th>Pos</th>
                <th>Driver</th>
                <th>Team</th>
                <th>Gap (s)</th>
                <th>Tyre / age</th>
              </tr>
            </thead>
            <tbody>
              {timing.map((row: TimingRow) => (
                <tr
                  key={row.driver}
                  className={row.driver === driver ? "selected-row" : ""}
                >
                  <td>{row.pos ?? "—"}</td>
                  <td>
                    <span style={{ color: row.team_color }}>{row.driver}</span>{" "}
                    · {row.name}
                  </td>
                  <td>{row.team}</td>
                  <td>
                    {row.pos === 1
                      ? "Leader"
                      : row.gap != null
                        ? `+${row.gap.toFixed(3)}`
                        : "—"}
                  </td>
                  <td>
                    <CompoundPill c={row.compound} size="sm" />{" "}
                    {row.tyre_age ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function TrackOutline({ circuit }: { circuit?: SessionData["circuit"] }) {
  const points = circuit?.points ?? [];
  if (points.length < 2)
    return <p className="muted">Circuit outline unavailable.</p>;
  const path =
    points
      .map((point, i) => `${i ? "L" : "M"}${point.x * 100},${point.y * 100}`)
      .join(" ") + " Z";
  return (
    <svg
      className="circuit-outline"
      viewBox="-8 -8 116 116"
      role="img"
      aria-label={`${circuit?.name || "Race"} circuit outline`}
    >
      <path
        d={path}
        fill="none"
        stroke="var(--border)"
        strokeWidth="5"
        strokeLinejoin="round"
      />
      <path
        d={path}
        fill="none"
        stroke="#c6cbd2"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <circle
        cx={points[0].x * 100}
        cy={points[0].y * 100}
        r="2"
        fill="var(--red)"
      />
    </svg>
  );
}

function StrategyTab({
  strategies,
  lapTraces,
  ready,
  stopComparison,
  optimal,
}: any) {
  const bestTime = strategies[0]?.mean_time ?? 0;
  const bars = strategies.slice(0, 10).map((s: any) => ({
    label: `#${s.rank} ${strategyCompounds(s)
      .map((c) => c[0])
      .join("→")} L${s.pit_laps.join("/")}`,
    value: (s.mean_time ?? bestTime) - bestTime,
    color: s.pit_count === 1 ? "#e8002d" : "#ffd700",
  }));
  const traces = (lapTraces || []).map((t: any, i: number) => ({
    name: t.label?.slice(0, 24) || `S${i + 1}`,
    color: TRACE_COLORS[i % TRACE_COLORS.length],
    points: (t.lap_times || []).map((lt: number, idx: number) => ({
      x: idx + 1,
      y: lt,
    })),
  }));
  return (
    <div className="detail-grid">
      {stopComparison &&
        (stopComparison.best_1stop || stopComparison.best_2stop) && (
          <div className="panel span-full">
            <div className="panel-header">
              <span className="title">1-Stop vs 2-Stop</span>
            </div>
            <div className="panel-body">
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 10,
                }}
              >
                {stopComparison.best_1stop && (
                  <div
                    className="ev-block"
                    style={{ borderLeft: "2px solid #e8002d" }}
                  >
                    <div className="lbl">Best 1-Stop</div>
                    <div
                      className="val"
                      style={{ color: "#e8002d", fontSize: "0.95rem" }}
                    >
                      {stopComparison.best_1stop.strategy}
                    </div>
                    <div className="sub">
                      {stopComparison.best_1stop.mean_time.toFixed(2)}s · WR{" "}
                      {stopComparison.best_1stop.win_rate != null
                        ? `${(stopComparison.best_1stop.win_rate * 100).toFixed(0)}%`
                        : "—"}
                    </div>
                  </div>
                )}
                {stopComparison.best_2stop && (
                  <div
                    className="ev-block"
                    style={{ borderLeft: "2px solid #ffd700" }}
                  >
                    <div className="lbl">Best 2-Stop</div>
                    <div
                      className="val"
                      style={{ color: "#ffd700", fontSize: "0.95rem" }}
                    >
                      {stopComparison.best_2stop.strategy}
                    </div>
                    <div className="sub">
                      {stopComparison.best_2stop.mean_time.toFixed(2)}s · WR{" "}
                      {stopComparison.best_2stop.win_rate != null
                        ? `${(stopComparison.best_2stop.win_rate * 100).toFixed(0)}%`
                        : "—"}
                    </div>
                  </div>
                )}
              </div>
              {stopComparison.faster && (
                <div className="muted" style={{ marginTop: 10 }}>
                  <strong style={{ color: "#fff" }}>
                    {stopComparison.faster.toUpperCase()}
                  </strong>{" "}
                  faster by {stopComparison.delta_seconds?.toFixed(2)}s in
                  expectation
                </div>
              )}
            </div>
          </div>
        )}
      <div className="panel">
        <div className="panel-header">
          <span className="title">Strategy comparison</span> — Seconds behind
          best
        </div>
        <div className="panel-body">
          {!ready ? (
            <div className="muted">Run simulation first</div>
          ) : (
            <BarChart items={bars} height={320} unit="s" />
          )}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header">
          <span className="title">Lap Trace</span> — Top 3 Strategies
        </div>
        <div className="panel-body">
          {!traces.length ? (
            <div className="muted">Run simulation first</div>
          ) : (
            <LineChart
              series={traces}
              xLabel="Lap"
              yLabel="Lap time (s)"
              height={280}
            />
          )}
        </div>
      </div>
      {optimal && (
        <div className="panel span-full">
          <div className="panel-header">
            <span className="title">Best Strategy Distribution</span>
          </div>
          <div className="panel-body">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4,1fr)",
                gap: 8,
              }}
            >
              {[
                ["P10", optimal.p10],
                ["P50", optimal.p50],
                ["P90", optimal.p90],
                [
                  "WIN",
                  optimal.win_rate != null ? optimal.win_rate * 100 : null,
                ],
              ].map(([k, v]) => (
                <div key={String(k)} className="ev-block">
                  <div className="lbl">{k}</div>
                  <div className="val" style={{ color: "var(--white)" }}>
                    {v != null
                      ? k === "WIN"
                        ? `${Number(v).toFixed(0)}%`
                        : `${Number(v).toFixed(1)}s`
                      : "—"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TyresTab({ curves, scatter, phaseSlopes, summary, tyreSummary }: any) {
  const series = (curves || []).map((c: any) => ({
    name: c.compound,
    color: TYRE[c.compound] || "#888",
    points: (c.ages || []).map((a: number, i: number) => ({
      x: a,
      y: c.lap_times[i],
    })),
  }));
  const cliffs = (curves || [])
    .filter((c: any) => c.cliff_lap != null)
    .map((c: any) => ({
      x: c.cliff_lap,
      color: TYRE[c.compound] || "#e8002d",
      label: `${c.compound} cliff`,
    }));
  const scatterPts = (scatter || []).map((p: any) => ({
    x: p.tyre_age,
    y: p.lap_time,
    color: TYRE[(p.compound || "").toUpperCase()] || "#888",
  }));
  return (
    <div className="detail-grid">
      <div className="panel">
        <div className="panel-header">
          <span className="title">Degradation Curves</span> — 3-Phase Piecewise
        </div>
        <div className="panel-body">
          {!series.length ? (
            <div className="muted">Run simulation first</div>
          ) : (
            <LineChart
              series={series}
              cliffMarks={cliffs}
              xLabel="Tyre age"
              yLabel="Lap time (s)"
              height={260}
            />
          )}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header">
          <span className="title">Stint Scatter</span>
        </div>
        <div className="panel-body">
          <ScatterChart points={scatterPts} height={260} />
        </div>
      </div>
      <div className="panel">
        <div className="panel-header">
          <span className="title">Cliff / Fit</span>
        </div>
        <div className="panel-body">
          {(tyreSummary || []).map((t: any) => (
            <div
              key={t.compound}
              style={{
                marginBottom: 10,
                borderBottom: "1px solid #1e1e1e",
                paddingBottom: 8,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <CompoundPill c={t.compound} size="sm" />
                <strong>{t.compound}</strong>
                <span className="muted">{t.fit_mode || ""}</span>
              </div>
              <div className="muted">
                Cliff{" "}
                {t.cliff_lap != null ? `L${t.cliff_lap.toFixed(1)}` : "none"}
                {t.cliff_ci_low != null &&
                  ` · CI [${t.cliff_ci_low.toFixed(1)}, ${t.cliff_ci_high.toFixed(1)}]`}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header">
          <span className="title">Phase Slopes</span> — s/lap
        </div>
        <div className="panel-body">
          <table className="data-table">
            <thead>
              <tr>
                <th>Compound</th>
                <th>Bedding</th>
                <th>Plateau</th>
                <th>Cliff</th>
              </tr>
            </thead>
            <tbody>
              {(phaseSlopes || []).map((r: any) => (
                <tr key={r.compound}>
                  <td>{r.compound}</td>
                  <td>{r.bedding != null ? r.bedding.toFixed(4) : "—"}</td>
                  <td>{r.plateau != null ? r.plateau.toFixed(4) : "—"}</td>
                  <td>{r.cliff != null ? r.cliff.toFixed(4) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel span-full">
        <div className="panel-header">
          <span className="title">Model Summary</span>
        </div>
        <div className="panel-body" style={{ overflowX: "auto" }}>
          {/* This table was previously fetched from the backend (the
              `summary` prop, i.e. model_summary from /api/simulate) but
              never rendered anywhere — a real gap versus dashboard.py's
              "Model Summary" table, found during the final parity audit
              before retiring dashboard.py. */}
          {!summary || !summary.length ? (
            <div className="muted">Run simulation first</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  {Object.keys(summary[0]).map((k) => (
                    <th key={k}>{k}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.map((row: any, i: number) => (
                  <tr key={i}>
                    {Object.keys(summary[0]).map((k) => (
                      <td key={k}>
                        {row[k] === null || row[k] === undefined
                          ? "—"
                          : String(row[k])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function UndercutTab({
  strategies,
  rivalData,
}: {
  strategies: StrategyRow[];
  rivalData?: SimulateResult["rival"];
}) {
  const cells = strategies
    .filter((row) => row.pit_laps.length === 1)
    .map((row) => ({
      pit_lap: row.pit_laps[0],
      mean_time: row.mean_time,
      pair: strategyCompounds(row).join(" → "),
      win_rate: row.win_rate ?? null,
    }));
  return (
    <div className="detail-grid">
      <section className="panel span-full">
        <div className="panel-header">
          <span className="title">One-stop pit timing</span>
          <span>From current simulation</span>
        </div>
        <div className="panel-body">
          <p className="section-description">
            Best expected one-stop race time at each tested pit lap. Green is
            faster; red is slower.
          </p>
          <HeatStrip cells={cells} />
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <span className="title">
            Undercut · {rivalData?.rival_code || "Rival"}
          </span>
        </div>
        <div className="panel-body">
          <EvTimeline
            points={rivalData?.undercut_timeline || []}
            color="#ef6259"
            label="Undercut"
          />
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <span className="title">
            Overcut · {rivalData?.rival_code || "Rival"}
          </span>
        </div>
        <div className="panel-body">
          <EvTimeline
            points={rivalData?.overcut_timeline || []}
            color="#75bda7"
            label="Overcut"
          />
        </div>
      </section>
      <p className="section-description span-full">
        Positive expected gain favours the move. Use Rival analysis to test a
        different gap, tyre age, or compound.
      </p>
    </div>
  );
}

function RivalTab(props: any) {
  const {
    rival,
    fallbackRival,
    rivalResult,
    rivalBusy,
    year,
    race,
    driver,
    raceLaps,
    circuit,
    rivalCompound,
    setRivalCompound,
    rivalTyreAge,
    setRivalTyreAge,
    gapToRival,
    setGapToRival,
    scanFrom,
    setScanFrom,
    scanTo,
    setScanTo,
    ourCompound,
    setOurCompound,
    ourTyreAge,
    setOurTyreAge,
    newCompound,
    setNewCompound,
    onRunRival,
  } = props;
  const r = rivalResult || {};
  const underTL = r.undercut_timeline || rival?.undercut_timeline || [];
  const overTL = r.overcut_timeline || rival?.overcut_timeline || [];
  const rec = r.recommendation;

  return (
    <div className="detail-grid">
      <div className="panel span-full">
        <div className="panel-header">
          <span className="title">Rival Configuration</span>
        </div>
        <div className="panel-body">
          <fieldset className="rival-controls" disabled={rivalBusy}>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-1">Rival compound</label>
              <select
                id="rival-setting-1"
                value={rivalCompound}
                onChange={(e) => setRivalCompound(e.target.value)}
              >
                {["SOFT", "MEDIUM", "HARD"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-2">
                Rival tyre age ({rivalTyreAge})
              </label>
              <input
                id="rival-setting-2"
                type="range"
                min={1}
                max={35}
                value={rivalTyreAge}
                onChange={(e) => setRivalTyreAge(Number(e.target.value))}
              />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-3">
                Gap to rival (s, + they lead) {gapToRival}
              </label>
              <input
                id="rival-setting-3"
                type="range"
                min={-10}
                max={15}
                step={0.5}
                value={gapToRival}
                onChange={(e) => setGapToRival(Number(e.target.value))}
              />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-4">Our compound now</label>
              <select
                id="rival-setting-4"
                value={ourCompound}
                onChange={(e) => setOurCompound(e.target.value)}
              >
                {["SOFT", "MEDIUM", "HARD"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-5">
                Our tyre age ({ourTyreAge})
              </label>
              <input
                id="rival-setting-5"
                type="range"
                min={1}
                max={35}
                value={ourTyreAge}
                onChange={(e) => setOurTyreAge(Number(e.target.value))}
              />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-6">Compound after pit</label>
              <select
                id="rival-setting-6"
                value={newCompound}
                onChange={(e) => setNewCompound(e.target.value)}
              >
                {["SOFT", "MEDIUM", "HARD"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-7">
                Scan from lap ({scanFrom})
              </label>
              <input
                id="rival-setting-7"
                type="range"
                min={1}
                max={Math.max(2, (raceLaps || 50) - 10)}
                value={scanFrom}
                onChange={(e) => {
                  const lap = Number(e.target.value);
                  setScanFrom(lap);
                  if (scanTo <= lap) setScanTo(lap + 1);
                }}
              />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label htmlFor="rival-setting-8">Scan to lap ({scanTo})</label>
              <input
                id="rival-setting-8"
                type="range"
                min={scanFrom + 1}
                max={Math.max(scanFrom + 2, (raceLaps || 50) - 2)}
                value={scanTo}
                onChange={(e) => setScanTo(Number(e.target.value))}
              />
            </div>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <button
                className="btn-run"
                style={{ width: "100%", margin: 0 }}
                disabled={rivalBusy || !race}
                onClick={onRunRival}
              >
                {rivalBusy ? "Scanning…" : "Run rival analysis"}
              </button>
            </div>
          </fieldset>
          <div className="muted" style={{ marginTop: 8 }}>
            vs {fallbackRival} · {year} {race}
          </div>
        </div>
      </div>

      {rec && (
        <div className="panel span-full">
          <div className="panel-header">
            <span className="title">Model comparison</span>
          </div>
          <div className="panel-body">
            <strong
              style={{
                color: rec.winner === "UNDERCUT" ? "#e8002d" : "#00d2be",
              }}
            >
              {rec.winner}
            </strong>{" "}
            is the stronger play · Best EV{" "}
            <strong>+{rec.best_ev.toFixed(2)}s</strong>
            <div className="muted" style={{ marginTop: 4 }}>
              Favourable laps — undercut: {rec.undercut_favourable_laps} ·
              overcut: {rec.overcut_favourable_laps}
            </div>
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <span className="title">Undercut EV Timeline</span>
        </div>
        <div className="panel-body">
          <EvTimeline points={underTL} color="#e8002d" label="Undercut" />
        </div>
      </div>
      <div className="panel">
        <div className="panel-header">
          <span className="title">Overcut EV Timeline</span>
        </div>
        <div className="panel-body">
          <EvTimeline points={overTL} color="#00d2be" label="Overcut" />
        </div>
      </div>

      <div className="panel span-full">
        <div className="panel-header">
          <span className="title">Undercut vs Overcut</span>
        </div>
        <div className="panel-body">
          <div className="ev-row">
            <div
              className="ev-block"
              style={{ borderLeft: "2px solid var(--red)" }}
            >
              <div className="lbl">UNDERCUT BEST</div>
              <div className="val" style={{ color: "var(--red)" }}>
                {r.best_undercut
                  ? `${r.best_undercut.mean_ev >= 0 ? "+" : ""}${r.best_undercut.mean_ev.toFixed(2)}s`
                  : rival?.undercut_best_ev != null
                    ? `${rival.undercut_best_ev.toFixed(2)}s`
                    : "—"}
              </div>
              <div className="sub">
                L{r.best_undercut?.lap ?? rival?.undercut_best_lap ?? "—"}
              </div>
            </div>
            <div
              className="ev-block"
              style={{ borderLeft: "2px solid var(--teal)" }}
            >
              <div className="lbl">OVERCUT BEST</div>
              <div className="val" style={{ color: "var(--teal)" }}>
                {r.best_overcut
                  ? `${r.best_overcut.mean_ev >= 0 ? "+" : ""}${r.best_overcut.mean_ev.toFixed(2)}s`
                  : rival?.overcut_best_ev != null
                    ? `${rival.overcut_best_ev.toFixed(2)}s`
                    : "—"}
              </div>
              <div className="sub">
                L{r.best_overcut?.lap ?? rival?.overcut_best_lap ?? "—"}
              </div>
            </div>
          </div>
        </div>
      </div>

      <details className="panel span-full replay-details">
        <summary>Illustrative rival replay</summary>
        <RivalReplay
          rivalResult={rivalResult}
          circuit={circuit}
          race={race}
          driver={driver}
          rivalCode={fallbackRival}
        />
      </details>

      {(underTL.length > 0 || overTL.length > 0) && (
        <details className="panel span-full scan-details">
          <summary>Scan data by lap</summary>
          <div className="panel-body" style={{ overflowX: "auto" }}>
            <div className="muted" style={{ marginBottom: 6 }}>
              Undercut
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Lap</th>
                  <th>Mean EV</th>
                  <th>P10</th>
                  <th>P90</th>
                  <th>Win%</th>
                  <th>Rec</th>
                </tr>
              </thead>
              <tbody>
                {underTL.map((row: any) => (
                  <tr key={"u" + row.lap}>
                    <td>{row.lap}</td>
                    <td>{row.mean_ev.toFixed(3)}</td>
                    <td>{row.p10_ev.toFixed(3)}</td>
                    <td>{row.p90_ev.toFixed(3)}</td>
                    <td>{(row.win_rate * 100).toFixed(1)}%</td>
                    <td>{row.recommend ? "✓" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="muted" style={{ margin: "12px 0 6px" }}>
              Overcut
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Lap</th>
                  <th>Mean EV</th>
                  <th>P10</th>
                  <th>P90</th>
                  <th>Win%</th>
                  <th>Rec</th>
                </tr>
              </thead>
              <tbody>
                {overTL.map((row: any) => (
                  <tr key={"o" + row.lap}>
                    <td>{row.lap}</td>
                    <td>{row.mean_ev.toFixed(3)}</td>
                    <td>{row.p10_ev.toFixed(3)}</td>
                    <td>{row.p90_ev.toFixed(3)}</td>
                    <td>{(row.win_rate * 100).toFixed(1)}%</td>
                    <td>{row.recommend ? "✓" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {(r.h2h || []).length > 0 && (
        <div className="panel span-full">
          <div className="panel-header">
            <span className="title">Head-to-Head</span> — Win Rate vs{" "}
            {fallbackRival}
          </div>
          <div className="panel-body">
            <BarChart
              items={r.h2h.slice(0, 12).map((h: any) => ({
                label: String(h.strategy).slice(0, 18),
                value: (h.win_rate ?? 0) * 100,
                color: (h.win_rate ?? 0) >= 0.5 ? "#39b54a" : "#e8002d",
              }))}
              height={300}
              unit="%"
            />
            {r.h2h[0] && (
              <div style={{ marginTop: 10 }} className="muted">
                Best:{" "}
                <strong style={{ color: "#fff" }}>{r.h2h[0].strategy}</strong> ·
                Win rate{" "}
                <strong
                  style={{
                    color:
                      (r.h2h[0].win_rate ?? 0) >= 0.5 ? "#39b54a" : "#e8002d",
                  }}
                >
                  {((r.h2h[0].win_rate ?? 0) * 100).toFixed(0)}%
                </strong>
                {r.h2h[0].mean_final_gap != null &&
                  ` · Mean gap ${r.h2h[0].mean_final_gap.toFixed(2)}s`}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function BacktestTab({ backtest, driver, circuit, race }: any) {
  if (!backtest) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="title">Backtest</span>
        </div>
        <div className="panel-body">
          <div className="muted">
            Run simulation to compare model strategy with recorded {driver}{" "}
            strategy. Requires stint data in the session.
          </div>
        </div>
      </div>
    );
  }
  const traces = [
    {
      name: backtest.actual.label,
      color: "#4c9be8",
      points: backtest.actual.lap_times.map((lt: number, i: number) => ({
        x: i + 1,
        y: lt,
      })),
    },
    {
      name: backtest.optimal.label,
      color: "#e8002d",
      points: backtest.optimal.lap_times.map((lt: number, i: number) => ({
        x: i + 1,
        y: lt,
      })),
    },
  ];
  const d = backtest.delta_seconds;
  const dColor = d > 0.5 ? "#e8002d" : d < -0.5 ? "#39b54a" : "#ffd700";
  return (
    <div className="detail-grid">
      <div className="panel span-full">
        <div className="panel-header">
          <span className="title">Backtest</span> — Model vs recorded
        </div>
        <div className="panel-body">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr",
              gap: 10,
              marginBottom: 16,
            }}
          >
            <div className="ev-block">
              <div className="lbl">Actual — {driver}</div>
              <div
                className="val"
                style={{ color: "#fff", fontSize: "0.95rem" }}
              >
                {backtest.actual.strategy}
              </div>
              <div className="sub">
                Pits: {(backtest.actual.pit_laps || []).join(", ") || "none"} ·{" "}
                {backtest.actual.total_time.toFixed(1)}s
              </div>
            </div>
            <div
              className="ev-block"
              style={{ borderLeft: "2px solid var(--red)" }}
            >
              <div className="lbl">Model strategy</div>
              <div
                className="val"
                style={{ color: "var(--red)", fontSize: "0.95rem" }}
              >
                {backtest.optimal.strategy}
              </div>
              <div className="sub">
                Pits: {(backtest.optimal.pit_laps || []).join(", ")} ·{" "}
                {backtest.optimal.total_time.toFixed(1)}s
              </div>
            </div>
            <div
              className="ev-block"
              style={{ borderLeft: `2px solid ${dColor}` }}
            >
              <div className="lbl">Delta</div>
              <div className="val" style={{ color: dColor }}>
                {d >= 0 ? "+" : ""}
                {d.toFixed(2)}s
              </div>
              <div className="sub">
                Actual was{" "}
                <strong style={{ color: dColor }}>{backtest.verdict}</strong>
              </div>
            </div>
          </div>
          <LineChart
            series={traces}
            xLabel="Lap"
            yLabel="Lap time (s)"
            height={260}
          />
        </div>
      </div>
      <details className="panel span-full replay-details">
        <summary>Illustrative race replay</summary>
        <BacktestReplay backtest={backtest} circuit={circuit} race={race} />
      </details>
    </div>
  );
}

// Given a closed polyline (the real circuit outline from get_circuit_outline
// — normalized 0-1 x/y points) and a 0-1 progress fraction around the lap,
// returns the interpolated point along the track. Uses actual segment arc
// length rather than naive index interpolation, since outline points are
// not evenly spaced around the circuit.
function interpolateAlongPath(
  points: { x: number; y: number }[],
  progress: number,
): { x: number; y: number } {
  if (!points || points.length < 2) return { x: 0.5, y: 0.5 };
  const n = points.length;
  const dist: number[] = [0];
  for (let i = 1; i <= n; i++) {
    const a = points[(i - 1) % n];
    const b = points[i % n];
    dist.push(dist[i - 1] + Math.hypot(b.x - a.x, b.y - a.y));
  }
  const total = dist[n];
  if (total <= 0) return points[0];
  const p = ((progress % 1) + 1) % 1;
  const target = p * total;
  let lo = 0,
    hi = n;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dist[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  const idx = Math.max(1, lo);
  const segStart = dist[idx - 1],
    segEnd = dist[idx];
  const t = segEnd > segStart ? (target - segStart) / (segEnd - segStart) : 0;
  const a = points[(idx - 1) % n],
    b = points[idx % n];
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

// Given cumulative lap-completion times and the per-lap durations, find
// which lap a given elapsed race time falls in and how far through that
// lap the driver is (0-1) — this feeds interpolateAlongPath's progress arg.
function lapProgressAt(
  cumTimes: number[],
  lapTimes: number[],
  t: number,
): { lap: number; progress: number } {
  if (!lapTimes.length) return { lap: 0, progress: 0 };
  let idx = 0;
  while (idx < lapTimes.length && cumTimes[idx + 1] <= t) idx++;
  if (idx >= lapTimes.length) return { lap: lapTimes.length, progress: 1 };
  const lapStart = cumTimes[idx];
  const lapDur = lapTimes[idx] || 1;
  const progress = Math.min(1, Math.max(0, (t - lapStart) / lapDur));
  return { lap: idx + 1, progress };
}

// Animated Actual-vs-AI-Optimal replay around the real circuit outline.
// Built entirely from data the backtest already computes (per-lap times
// for both strategies) — no new backend work, no telemetry fetching.
// Cars advance uniformly around the known track shape based on elapsed
// race time within the current lap; this is a strategy-comparison
// visualization, not a frame-accurate telemetry replay (see docs/decisions.md
// for the deliberate scope decision behind this vs full per-driver telemetry).
// Generic two-car animated replay around the real circuit outline. Built
// once here and reused by both BacktestReplay (Actual vs Model strategy) and
// RivalReplay (You vs a chosen rival) — the interpolation/animation logic
// is identical between them, only the two lap-time series, labels, and
// colors differ.
function RaceReplay({
  title,
  subtitle,
  resetKey,
  circuit,
  aLabel,
  aLapTimes,
  aColor,
  bLabel,
  bLapTimes,
  bColor,
  emptyMessage,
}: {
  title: string;
  subtitle: string;
  resetKey: unknown; // reset whenever this changes (e.g. a new result object)
  circuit: any;
  aLabel: string;
  aLapTimes: number[];
  aColor: string;
  bLabel: string;
  bLapTimes: number[];
  bColor: string;
  emptyMessage: string;
}) {
  const points: { x: number; y: number }[] = circuit?.points || [];

  const aCum = useMemo(() => {
    const out = [0];
    for (const lt of aLapTimes) out.push(out[out.length - 1] + lt);
    return out;
  }, [aLapTimes]);
  const bCum = useMemo(() => {
    const out = [0];
    for (const lt of bLapTimes) out.push(out[out.length - 1] + lt);
    return out;
  }, [bLapTimes]);

  const totalDuration = Math.max(
    aCum[aCum.length - 1] || 0,
    bCum[bCum.length - 1] || 0,
  );

  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(25); // race-seconds simulated per real second
  const rafRef = useRef<number | null>(null);
  const lastTsRef = useRef<number | null>(null);

  // Reset and pause whenever a new result arrives — not on
  // every re-render.
  useEffect(() => {
    setElapsed(0);
    setPlaying(false);
    lastTsRef.current = null;
  }, [resetKey]);

  useEffect(() => {
    if (!playing || totalDuration <= 0) {
      lastTsRef.current = null;
      return;
    }
    function step(ts: number) {
      if (lastTsRef.current == null) lastTsRef.current = ts;
      const dt = (ts - lastTsRef.current) / 1000;
      lastTsRef.current = ts;
      setElapsed((prev) => {
        const next = prev + dt * speed;
        if (next >= totalDuration) {
          setPlaying(false);
          return totalDuration;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(step);
    }
    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, speed, totalDuration]);

  if (!points.length || !aLapTimes.length || !bLapTimes.length) {
    return (
      <div className="panel span-full">
        <div className="panel-header">
          <span className="title">{title}</span>
        </div>
        <div className="panel-body">
          <div className="muted">
            {!points.length
              ? "Circuit geometry not available for this session — replay needs the real track outline."
              : emptyMessage}
          </div>
        </div>
      </div>
    );
  }

  const aState = lapProgressAt(aCum, aLapTimes, elapsed);
  const bState = lapProgressAt(bCum, bLapTimes, elapsed);
  const aPos = interpolateAlongPath(points, aState.progress);
  const bPos = interpolateAlongPath(points, bState.progress);

  const pathD =
    `M ${points[0].x * 100} ${points[0].y * 100} ` +
    points
      .slice(1)
      .map((p) => `L ${p.x * 100} ${p.y * 100}`)
      .join(" ") +
    " Z";

  return (
    <div className="panel span-full">
      <div className="panel-header">
        <span className="title">{title}</span>
        <span>{subtitle}</span>
      </div>
      <div className="panel-body no-pad">
        <div
          className="replay-stage"
          style={{
            position: "relative",
            width: "100%",
            background: "var(--off)",
          }}
        >
          <svg
            role="img"
            aria-label="Illustrative strategy replay"
            viewBox="0 0 100 100"
            preserveAspectRatio="xMidYMid meet"
            style={{ width: "100%", height: "100%", display: "block" }}
          >
            <path
              d={pathD}
              fill="none"
              stroke="#1a1a1a"
              strokeWidth="6"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <path
              d={pathD}
              fill="none"
              stroke="#2c2c2c"
              strokeWidth="3.4"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <path
              d={pathD}
              fill="none"
              stroke="#484848"
              strokeWidth="1"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <circle
              cx={aPos.x * 100}
              cy={aPos.y * 100}
              r={2.4}
              fill={aColor}
              stroke="#000"
              strokeWidth="0.5"
            />
            <circle
              cx={bPos.x * 100}
              cy={bPos.y * 100}
              r={2.4}
              fill={bColor}
              stroke="#000"
              strokeWidth="0.5"
            />
          </svg>
          <div className="replay-legend">
            <span>
              <span style={{ color: aColor }}>●</span> {aLabel} — Lap{" "}
              {aState.lap}/{aLapTimes.length}
            </span>
            <span>
              <span style={{ color: bColor }}>●</span> {bLabel} — Lap{" "}
              {bState.lap}/{bLapTimes.length}
            </span>
          </div>
        </div>
        <div className="track-replay-controls">
          <button
            className="btn-export"
            onClick={() => {
              if (elapsed >= totalDuration) {
                setElapsed(0);
                lastTsRef.current = null;
                setPlaying(true);
              } else {
                setPlaying((p) => !p);
              }
            }}
          >
            {playing ? "Pause" : elapsed >= totalDuration ? "Replay" : "Play"}
          </button>
          <input
            type="range"
            aria-label="Replay position"
            min={0}
            max={totalDuration || 1}
            step={0.1}
            value={Math.min(elapsed, totalDuration)}
            onChange={(e) => {
              const v = Number(e.target.value);
              setElapsed(v >= totalDuration ? totalDuration - 0.01 : v);
              setPlaying(false);
            }}
            style={{ flex: 1 }}
          />
          <span
            className="muted"
            style={{ minWidth: 46, textAlign: "right", fontSize: "0.72rem" }}
          >
            {elapsed.toFixed(0)}s
          </span>
          <select
            aria-label="Replay speed"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            style={{
              background: "var(--panel, #111)",
              color: "inherit",
              border: "1px solid #333",
              fontSize: "0.72rem",
              padding: "2px 4px",
            }}
          >
            <option value={10}>10×</option>
            <option value={25}>25×</option>
            <option value={50}>50×</option>
            <option value={100}>100×</option>
          </select>
        </div>
      </div>
    </div>
  );
}

function BacktestReplay({ backtest, circuit, race }: any) {
  return (
    <RaceReplay
      title="Race Replay"
      subtitle={`${race} — Actual vs Model strategy`}
      resetKey={backtest}
      circuit={circuit}
      aLabel="Actual"
      aLapTimes={backtest?.actual?.lap_times || []}
      aColor="#4c9be8"
      bLabel="Model strategy"
      bLapTimes={backtest?.optimal?.lap_times || []}
      bColor="#e8002d"
      emptyMessage="Backtest lap data unavailable for this driver/session."
    />
  );
}

// Rival replay: you vs the chosen rival, using the full-race lap-by-lap
// trace from /api/rival-analysis's race_trace field (simulate_race_with_
// rival — already existed in race_sim.py, just never wired into an
// endpoint until this was added). Same RaceReplay machinery as the
// Backtest tab, different data source.
function RivalReplay({ rivalResult, circuit, race, driver, rivalCode }: any) {
  const trace = rivalResult?.race_trace;
  return (
    <RaceReplay
      title="Rival Replay"
      subtitle={`${race} — ${driver} vs ${rivalCode}`}
      resetKey={trace}
      circuit={circuit}
      aLabel={driver || "You"}
      aLapTimes={trace?.our_lap_times || []}
      aColor="#4c9be8"
      bLabel={rivalCode || "Rival"}
      bLapTimes={trace?.rival_lap_times || []}
      bColor="#ff8000"
      emptyMessage="Run the rival analysis to generate a race trace."
    />
  );
}

function ResultsTab({
  strategies,
  onExport,
  ready,
}: {
  strategies: StrategyRow[];
  onExport: () => void;
  ready: boolean;
}) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const pageSize = 30;
  const filtered = strategies.filter(
    (row) =>
      (filter === "all" || row.pit_laps.length === Number(filter)) &&
      `${row.strategy} ${strategyCompounds(row).join(" ")} ${row.pit_laps.join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase().trim()),
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  return (
    <section className="panel">
      <div className="panel-header">
        <span className="title">Ranked strategies</span>
        <button className="btn-export" onClick={onExport} disabled={!ready}>
          Download all results CSV
        </button>
      </div>
      <div className="results-toolbar">
        <label>
          Search strategies
          <input
            type="search"
            value={query}
            placeholder="Compound or pit lap"
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <label htmlFor="results-stop-filter">
          Pit stops
          <select
            id="results-stop-filter"
            aria-label="Filter results by pit stops"
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setPage(0);
            }}
          >
            <option value="all">All strategies</option>
            <option value="1">One stop</option>
            <option value="2">Two stops</option>
          </select>
        </label>
        <span className="muted" role="status">
          {filtered.length.toLocaleString()} results · ranked by mean time
        </span>
      </div>
      <div className="table-scroll">
        <table className="data-table results-table">
          <caption className="sr-only">
            Strategy results. All time values are in seconds.
          </caption>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Tyre sequence</th>
              <th>Pit laps</th>
              <th>Mean (s)</th>
              <th>Std dev (s)</th>
              <th>P10 (s)</th>
              <th>Median (s)</th>
              <th>P90 (s)</th>
              <th>Win rate</th>
            </tr>
          </thead>
          <tbody>
            {filtered
              .slice(currentPage * pageSize, (currentPage + 1) * pageSize)
              .map((row) => (
                <tr key={row.rank}>
                  <td>{row.rank}</td>
                  <td>
                    <CompoundSequence
                      compounds={row.compound_sequence}
                      strategy={row.strategy}
                    />
                  </td>
                  <td>{row.pit_laps.join(" / ") || "—"}</td>
                  <td>{row.mean_time?.toFixed(2) ?? "—"}</td>
                  <td>{row.std_time?.toFixed(2) ?? "—"}</td>
                  <td>{row.p10?.toFixed(2) ?? "—"}</td>
                  <td>{row.p50?.toFixed(2) ?? "—"}</td>
                  <td>{row.p90?.toFixed(2) ?? "—"}</td>
                  <td>
                    {row.win_rate != null
                      ? `${(row.win_rate * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {!filtered.length && (
          <p className="empty-state">
            {strategies.length
              ? "No matching strategies. Try another compound or pit lap."
              : "Run a simulation to see ranked results."}
          </p>
        )}
      </div>
      <div className="pagination">
        <span>
          {filtered.length ? currentPage * pageSize + 1 : 0}–
          {Math.min((currentPage + 1) * pageSize, filtered.length)} of{" "}
          {filtered.length.toLocaleString()}
        </span>
        <div>
          <button
            className="btn-export"
            disabled={currentPage === 0}
            onClick={() => setPage(currentPage - 1)}
          >
            Previous
          </button>
          <span>
            Page {currentPage + 1} of {pageCount}
          </span>
          <button
            className="btn-export"
            disabled={currentPage + 1 >= pageCount}
            onClick={() => setPage(currentPage + 1)}
          >
            Next
          </button>
        </div>
      </div>
      <p className="results-note">
        P10–P90 describes the simulated race-time range. Win rate compares
        tested strategies within the model; it is not the probability of winning
        the Grand Prix. CSV includes all strategies.
      </p>
    </section>
  );
}
