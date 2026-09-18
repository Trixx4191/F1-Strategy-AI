
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type SessionData,
  type SimulateResult,
  type TimingRow,
  type RivalAnalysisResult,
  type DriverEntry,
} from "./api";
import {
  LineChart,
  ScatterChart,
  BarChart,
  EvTimeline,
  TYRE,
  TRACE_COLORS,
} from "./Charts";
import { compoundStyle, raceCountryCode, flagUrl } from "./f1ui";
import "./index.css";

function CompoundPill({ c, size = "md" }: { c?: string | null; size?: "sm" | "md" }) {
  const s = compoundStyle(c);
  return (
    <span
      className={`compound-pill${size === "sm" ? " sm" : ""}`}
      style={{ background: s.fill, color: s.text, borderColor: s.border }}
      title={s.label}
    >
      {s.label[0]}
    </span>
  );
}

function CompoundSequence({ compounds }: { compounds?: string[] }) {
  const list = compounds || [];
  if (!list.length) return <span className="muted">—</span>;
  return (
    <span className="compound-seq">
      {list.map((c, i) => (
        <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
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
      <img src={flagUrl(cc, size >= 28 ? 80 : 40)} alt="" width={size} height={Math.round(size * 0.67)} />
    </span>
  );
}


/** Fallback only when no session roster yet — teams are NEVER trusted from this map. */
const DRIVER_FALLBACK: Record<string, string> = {
  VER: "VERSTAPPEN", NOR: "NORRIS", HAM: "HAMILTON", LEC: "LECLERC",
  RUS: "RUSSELL", PIA: "PIASTRI", SAI: "SAINZ", ALO: "ALONSO",
  STR: "STROLL", GAS: "GASLY", OCO: "OCON", ALB: "ALBON",
  BOT: "BOTTAS", HUL: "HULKENBERG", TSU: "TSUNODA", PER: "PEREZ",
  MAG: "MAGNUSSEN", RIC: "RICCIARDO", LAW: "LAWSON", BEA: "BEARMAN",
  COL: "COLAPINTO", DOO: "DOOHAN", ANT: "ANTONELLI", HAD: "HADJAR",
};


function rosterMap(entries?: DriverEntry[] | null): Record<string, DriverEntry> {
  const m: Record<string, DriverEntry> = {};
  for (const e of entries || []) {
    if (e?.code) m[e.code] = e;
  }
  return m;
}

function displayName(code: string, roster: Record<string, DriverEntry>): string {
  return roster[code]?.name || DRIVER_FALLBACK[code] || code;
}

function displayTeam(code: string, roster: Record<string, DriverEntry>): string {
  return roster[code]?.team || "";
}

function displayColor(code: string, roster: Record<string, DriverEntry>, timingColor?: string | null): string {
  return timingColor || roster[code]?.team_color || "#888888";
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
  const [rivalResult, setRivalResult] = useState<RivalAnalysisResult | null>(null);
  const [rivalBusy, setRivalBusy] = useState(false);
  // Interactive rival params (dashboard Tab 5)
  const [rivalCompound, setRivalCompound] = useState("MEDIUM");
  const [rivalTyreAge, setRivalTyreAge] = useState(10);
  const [gapToRival, setGapToRival] = useState(2.0);
  const [scanFrom, setScanFrom] = useState(15);
  const [scanTo, setScanTo] = useState(30);
  const [ourCompound, setOurCompound] = useState("MEDIUM");
  const [ourTyreAge, setOurTyreAge] = useState(10);
  const [newCompound, setNewCompound] = useState("HARD");

  useEffect(() => {
    const storedUi = readFromStorage<PersistedUiState>(STORAGE_KEYS.ui);
    const storedCurrent = readFromStorage<PersistedCurrentRun>(STORAGE_KEYS.current);
    const storedSaves = readFromStorage<SavedRun[]>(STORAGE_KEYS.saved);

    if (storedUi) {
      setYear(storedUi.year || 2024);
      setRace(storedUi.race || "");
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
      setTab(storedCurrent.state?.tab || "overview");
    }

    if (Array.isArray(storedSaves)) {
      setSavedRuns(storedSaves);
    }

    setHasHydrated(true);
    api.latestSeason().then((r) => { setLatestYear(r.year); setYear((prev) => prev || r.year); }).catch(() => {});
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
  }, [hasHydrated, year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp, tab, autoPersist]);

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
        state: { year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp, tab, autoPersist },
        result: sim,
      });
      if (!ok) {
        setError(
          "Couldn't auto-save this run — browser storage is full. Delete " +
          "an old saved run, or turn off auto-save, and try again."
        );
      }
    } else {
      removeFromStorage(STORAGE_KEYS.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHydrated, autoPersist, sim]);

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
        "saved run and try again."
      );
    }
  }, [hasHydrated, savedRuns]);

  // (Duplicate `api.latestSeason()` fetch removed here — the hydration
  // effect earlier in this file already fetches it once on mount; this
  // second copy fired the same request a second time on every page load.)

  useEffect(() => {
    if (!year) return;
    api.races(year).then((r) => { setRaces(r.races); setRace((prev) => prev || r.races[0] || ""); })
      .catch((e) => setError(String(e.message || e)));
  }, [year]);

  useEffect(() => {
    if (!year || !race) return;
    setStatus("loading"); setError(null); setSim(null);
    api.session(year, race)
      .then((data) => {
        setSession(data);
        setStatus("idle");
        const codes = (data.drivers || []).map((d) => d.code);
        if (codes.length) {
          if (!codes.includes(driver)) setDriver(codes[0]);
          if (!codes.includes(rival) || rival === codes[0]) {
            setRival(codes.find((c) => c !== (codes.includes(driver) ? driver : codes[0])) || codes[0]);
          }
        }
      })
      .catch((e) => { setSession(null); setStatus("error"); setError(String(e.message || e)); });
  }, [year, race]);

  const persistCurrentRun = useCallback((result: SimulateResult) => {
    if (!autoPersist) return;
    const payload: PersistedCurrentRun = {
      savedAt: Date.now(),
      state: {
        year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp, tab, autoPersist,
      },
      result,
    };
    writeToStorage(STORAGE_KEYS.current, payload);
  }, [autoPersist, year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp, tab]);

  const saveCurrentRunToSavedList = useCallback(() => {
    if (!sim) return;
    const item: SavedRun = {
      id: makeSavedRunId(),
      label: `${sim.race} · ${sim.driver} · ${new Date().toLocaleString([], { dateStyle: "short", timeStyle: "short" })}`,
      createdAt: Date.now(),
      state: {
        year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp, tab, autoPersist,
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
    setSavedRuns((prev) => [item, ...prev].slice(0, MAX_SAVED_RUNS));
  }, [sim, year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp, tab, autoPersist]);

  const resetCurrentRun = useCallback(() => {
    setSim(null);
    setSession(null);
    setStatus("idle");
    setError(null);
    setRivalResult(null);
    setTab("overview");
    removeFromStorage(STORAGE_KEYS.current);
  }, []);

  const runSim = useCallback(async () => {
    if (!year || !race) return;
    setStatus("loading"); setError(null); setSimRunning(true);
    try {
      const result = await api.simulate({
        year, race, driver, rival,
        n_simulations: nSims, strategy_type: strategyType,
        noise_std: noise, use_live_temp: useLiveTemp,
        ...(useLiveTemp ? {} : { track_temp_override: manualTemp }),
      } as any);
      setSim(result);
      setSession({
        year: result.year, race: result.race, race_laps: result.race_laps,
        timing: result.timing, circuit: result.circuit, weather: result.weather,
        session_drivers: result.session_drivers, drivers: result.drivers,
      });
      setStatus("ready");
      setTab("overview");
      persistCurrentRun(result);
    } catch (e: unknown) {
      setStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSimRunning(false);
    }
  }, [year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp, persistCurrentRun]);

  const timing: TimingRow[] = useMemo(() => {
    const rmap = rosterMap(sim?.drivers ?? session?.drivers);
    return (sim?.timing ?? session?.timing ?? []).map((r) => ({
      ...r,
      team_color: r.team_color || rmap[r.driver]?.team_color || "#888",
      name: r.name || rmap[r.driver]?.name || DRIVER_FALLBACK[r.driver] || r.driver,
      team: r.team || rmap[r.driver]?.team || "",
    }));
  }, [session, sim]);

  const roster = useMemo(
    () => rosterMap(sim?.drivers ?? session?.drivers),
    [sim?.drivers, session?.drivers]
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
  const yearOptions = Array.from({ length: Math.max(1, latestYear - 2017) }, (_, i) => latestYear - i);
  const rivalOptions = (driverCodes.length ? driverCodes : Object.keys(DRIVER_FALLBACK)).filter((d) => d !== driver);

  const weatherStr = weather
    ? [weather.track_temp != null ? `TRK ${weather.track_temp.toFixed(0)}°C` : null,
       weather.air_temp != null ? `AIR ${weather.air_temp.toFixed(0)}°C` : null,
       weather.rainfall ? "RAIN" : null].filter(Boolean).join(" · ") || "—"
    : "—";

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "strategy", label: "Strategy" },
    { id: "tyres", label: "Tyre Model" },
    { id: "undercut", label: "Over/Undercut" },
    { id: "rival", label: "Rival Analysis" },
    { id: "backtest", label: "Backtest" },
    { id: "results", label: "Results" },
    { id: "saved", label: "Saved Sims" },
  ];

  function exportCsv() {
    if (!strategies.length) return;
    const cols = ["rank","strategy","compound_sequence","pit_laps","pit_count","mean_time","std_time","p10","p50","p90","win_rate"];
    const lines = [cols.join(",")];
    for (const s of strategies) {
      lines.push([
        s.rank,
        `"${(s.strategy || s.compound_sequence.join("→")).replace(/"/g, '""')}"`,
        `"${(s.compound_sequence || []).join("→")}"`,
        `"${(s.pit_laps || []).join(" ")}"`,
        s.pit_count ?? "",
        s.mean_time ?? "",
        s.std_time ?? "",
        s.p10 ?? "",
        s.p50 ?? "",
        s.p90 ?? "",
        s.win_rate ?? "",
      ].join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `f1_strategy_${year}_${race}_${driver}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="eyebrow">Mission Control</div>
          <h1>F1 <span>STRATEGY</span></h1>
        </div>
        <div className="sb-section">Session</div>
        <div className="sb-field">
          <label>Season</label>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div className="sb-field">
          <label>Grand Prix</label>
          <select value={race} onChange={(e) => setRace(e.target.value)}>
            {races.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div className="sb-section">Driver</div>
        <div className="sb-field">
          <label>Select driver</label>
          <select value={driver} onChange={(e) => setDriver(e.target.value)}>
            {(driverCodes.length ? driverCodes : Object.keys(DRIVER_FALLBACK)).map((d) => (
              <option key={d} value={d}>
                {d} — {displayName(d, roster)}{displayTeam(d, roster) ? ` · ${displayTeam(d, roster)}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="sb-section">Rival</div>
        <div className="sb-field">
          <label>Rival driver</label>
          <select value={rival} onChange={(e) => setRival(e.target.value)}>
            {rivalOptions.map((d) => (
              <option key={d} value={d}>
                {d} — {displayName(d, roster)}{displayTeam(d, roster) ? ` · ${displayTeam(d, roster)}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="sb-section">Simulation</div>
        <div className="sb-field">
          <label>MC iterations ({nSims})</label>
          <input type="range" min={100} max={2000} step={100} value={nSims}
            onChange={(e) => setNSims(Number(e.target.value))} />
        </div>
        <div className="sb-field">
          <label>Strategy type</label>
          <select value={strategyType} onChange={(e) => setStrategyType(e.target.value)}>
            <option value="1-stop">1-stop</option>
            <option value="2-stop">2-stop</option>
            <option value="Both">Both</option>
          </select>
        </div>
        <div className="sb-field">
          <label>Lap noise ({noise.toFixed(2)}s)</label>
          <input type="range" min={0} max={1} step={0.05} value={noise}
            onChange={(e) => setNoise(Number(e.target.value))} />
        </div>
        <div className="sb-section">Track temp</div>
        <div className="sb-field">
          <label>
            <input type="checkbox" checked={useLiveTemp}
              onChange={(e) => setUseLiveTemp(e.target.checked)} /> Use live session temp
          </label>
        </div>
        {!useLiveTemp && (
          <div className="sb-field">
            <label>Override ({manualTemp}°C)</label>
            <input type="range" min={15} max={55} step={1} value={manualTemp}
              onChange={(e) => setManualTemp(Number(e.target.value))} />
          </div>
        )}
        <button className="btn-run" disabled={simRunning || !race} onClick={runSim}>
          {simRunning ? "RUNNING…" : "▶  RUN SIMULATION"}
        </button>
        <div className="sb-field" style={{ marginTop: 12 }}>
          <label>
            <input type="checkbox" checked={autoPersist} onChange={(e) => setAutoPersist(e.target.checked)} />
            Auto-save current run in browser
          </label>
        </div>
        {sim && (
          <>
            <button className="btn-run" style={{ marginTop: 12, background: "#1f2937" }} onClick={saveCurrentRunToSavedList}>
              Save to My Sims
            </button>
            <button className="btn-run" style={{ marginTop: 8, background: "#4b5563" }} onClick={resetCurrentRun}>
              Reset current run
            </button>
          </>
        )}
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-logo"><span className="dot" /> F1 STRATEGY AI</div>
          <div className="topbar-meta">
            <span><strong>{year}</strong> SEASON</span>
            <span className="flag-chip">
              <RaceFlag race={race} size={20} />
              <strong>{(race || "—").toUpperCase()}</strong> GP
            </span>
            <span>DRIVER <strong>{driver}</strong></span>
            <span>TRACK <strong>{weather?.track_temp != null ? `${weather.track_temp.toFixed(0)}°C` : "—"}</strong></span>
            <span>{weatherStr}</span>
          </div>
          <span className={`badge ${status}`}>{status.toUpperCase()}</span>
        </header>

        {error && <div className="error-box">{error}</div>}

        <div className="tab-bar">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={`tab-btn${tab === t.id ? " active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="tab-content">
          {[
            { id: "overview", panel: (
              <Overview
                timing={timing} driver={driver} circuit={circuit} race={race}
                strategies={strategies} tyreSummary={tyreSummary}
                rivalData={rivalData} raceLaps={raceLaps} status={status} nSims={nSims}
                weather={weather} pitLoss={sim?.pit_loss} optimal={sim?.optimal_strategy}
                backtest={sim?.backtest} lapTraces={sim?.lap_traces ?? []}
                stopComparison={sim?.stop_comparison} roster={roster}
              />
            ) },
            { id: "strategy", panel: (
              <StrategyTab
                strategies={strategies}
                lapTraces={sim?.lap_traces ?? []}
                ready={status === "ready"}
                stopComparison={sim?.stop_comparison}
                optimal={sim?.optimal_strategy}
              />
            ) },
            { id: "tyres", panel: (
              <TyresTab
                curves={sim?.tyre_curves ?? []}
                scatter={sim?.stint_scatter ?? []}
                phaseSlopes={sim?.phase_slopes ?? []}
                summary={sim?.model_summary ?? []}
                tyreSummary={tyreSummary}
              />
            ) },
            { id: "undercut", panel: (
              <UndercutTab
                strategies={strategies}
                raceLaps={raceLaps}
                year={year}
                race={race}
                driver={driver}
                rival={rival}
                nSims={nSims}
                strategyType={strategyType}
                noise={noise}
                useLiveTemp={useLiveTemp}
                manualTemp={manualTemp}
              />
            ) },
            { id: "rival", panel: (
              <RivalTab
                rival={rivalData}
                fallbackRival={rival}
                rivalResult={rivalResult}
                rivalBusy={rivalBusy}
                year={year} race={race} driver={driver} raceLaps={raceLaps}
                circuit={circuit}
                rivalCompound={rivalCompound} setRivalCompound={setRivalCompound}
                rivalTyreAge={rivalTyreAge} setRivalTyreAge={setRivalTyreAge}
                gapToRival={gapToRival} setGapToRival={setGapToRival}
                scanFrom={scanFrom} setScanFrom={setScanFrom}
                scanTo={scanTo} setScanTo={setScanTo}
                ourCompound={ourCompound} setOurCompound={setOurCompound}
                ourTyreAge={ourTyreAge} setOurTyreAge={setOurTyreAge}
                newCompound={newCompound} setNewCompound={setNewCompound}
                noise={noise}
                onRunRival={async () => {
                  setRivalBusy(true); setError(null);
                  try {
                    const r = await api.rivalAnalysis({
                      year, race, driver, rival,
                      rival_compound: rivalCompound, rival_tyre_age: rivalTyreAge,
                      gap_to_rival: gapToRival, scan_from_lap: scanFrom, scan_to_lap: scanTo,
                      our_compound: ourCompound, our_tyre_age: ourTyreAge, new_compound: newCompound,
                      n_simulations: Math.min(200, nSims), noise_std: noise, run_h2h: true,
                    });
                    setRivalResult(r);
                  } catch (e: unknown) {
                    setError(e instanceof Error ? e.message : String(e));
                  } finally { setRivalBusy(false); }
                }}
              />
            ) },
            { id: "backtest", panel: <BacktestTab backtest={sim?.backtest ?? null} driver={driver} circuit={circuit} race={race} /> },
            { id: "results", panel: (
              <ResultsTab
                strategies={strategies}
                onExport={exportCsv}
                onExportBackend={async () => {
                  try {
                    const res = await api.simulateCsv({
                      year, race, driver, rival,
                      n_simulations: nSims, strategy_type: strategyType,
                      noise_std: noise, use_live_temp: useLiveTemp,
                      precomputed_strategies: strategies,
                      ...(useLiveTemp ? {} : { track_temp_override: manualTemp }),
                    } as any);
                    if (!res.ok) throw new Error(res.statusText || "CSV request failed");
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `f1_strategy_${year}_${race}_${driver}.csv`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (e) {
                    setError(e instanceof Error ? e.message : String(e));
                  }
                }}
                ready={status === "ready"}
              />
            ) },
            { id: "saved", panel: (
              <SavedRunsTab
                savedRuns={savedRuns}
                selectedIds={selectedSavedIds}
                onToggleSelect={(id) => {
                  setSelectedSavedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
                }}
                onLoad={(run) => {
                  setSim(run.result);
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
            ) }
          ].map((pane) => (
            <div key={pane.id} style={{ display: tab === pane.id ? "block" : "none" }}>
              {pane.panel}
            </div>
          ))}
        </div>

        <div className="footer-note">
          React Mission Control · Full parity with dashboard.py · Circuit from FastF1
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
  const selectedRuns = savedRuns.filter((run) => selectedIds.includes(run.id));
  const rankedRuns = [...selectedRuns].sort((a, b) => {
    const aMean = a.result.optimal_strategy?.mean_time ?? Number.POSITIVE_INFINITY;
    const bMean = b.result.optimal_strategy?.mean_time ?? Number.POSITIVE_INFINITY;
    return aMean - bMean;
  });
  const bestMeanTime = rankedRuns[0]?.result.optimal_strategy?.mean_time ?? null;
  const bestWinRate = rankedRuns.reduce((max, run) => {
    const v = run.result.optimal_strategy?.win_rate ?? 0;
    return Math.max(max, v);
  }, 0);

  return (
    <div className="grid">
      <div className="panel span-full">
        <div className="panel-header">
          <span className="title">Saved simulations</span>
          <span>{savedRuns.length} saved</span>
        </div>
        <div className="panel-body">
          {savedRuns.length === 0 ? (
            <div className="muted">No saved sims yet. Run a simulation and save it to compare later.</div>
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {savedRuns.map((run) => (
                <div key={run.id} className="strat-row" style={{ gridTemplateColumns: "48px 1.5fr 140px 120px 120px" }}>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(run.id)}
                    onChange={() => onToggleSelect(run.id)}
                    aria-label={`Select ${run.label}`}
                  />
                  <div>
                    <div style={{ fontWeight: 700 }}>{run.label}</div>
                    <div className="muted" style={{ fontSize: "0.7rem" }}>
                      {run.state.year} · {run.state.race} · {run.state.driver} vs {run.state.rival}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>{run.result.optimal_strategy?.mean_time != null ? `${run.result.optimal_strategy.mean_time.toFixed(1)}s` : "—"}</div>
                  <button className="btn-run" style={{ padding: "0.5rem 0.8rem", fontSize: "0.7rem" }} onClick={() => onLoad(run)}>
                    Load
                  </button>
                  <button className="btn-run" style={{ padding: "0.5rem 0.8rem", fontSize: "0.7rem", background: "#4b5563" }} onClick={() => onDelete(run.id)}>
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
          {savedRuns.length > 0 && (
            <div style={{ display: "flex", gap: 12, marginTop: 18, alignItems: "center", flexWrap: "wrap" }}>
              <button
                className="btn-run"
                disabled={selectedRuns.length < 2}
                onClick={() => {
                  if (selectedRuns.length >= 2) {
                    document.getElementById("saved-compare-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }
                }}
              >
                Compare selected ({selectedRuns.length})
              </button>
              <button className="btn-run" style={{ background: "#4b5563" }} onClick={onClearAll}>Clear all saved sims</button>
            </div>
          )}
          {selectedRuns.length >= 2 && (
            <div id="saved-compare-panel" className="panel" style={{ marginTop: 18 }}>
              <div className="panel-header">
                <span className="title">Side-by-side comparison</span>
                <span className="muted">{rankedRuns[0]?.label ?? "Winner"} leads</span>
              </div>
              <div className="panel-body">
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
                  {rankedRuns.map((run, index) => {
                    const best = run.result.optimal_strategy ?? run.result.strategies?.[0] ?? null;
                    const strategyText = best?.strategy || best?.compound_sequence?.join("→") || "—";
                    const meanTime = best?.mean_time ?? null;
                    const winRate = best?.win_rate ?? 0;
                    const delta = bestMeanTime != null && meanTime != null ? meanTime - bestMeanTime : 0;
                    const winnerLabel = index === 0 ? "Winner" : index === 1 ? "Runner-up" : `Rank ${index + 1}`;

                    return (
                      <div key={run.id} className="ev-block" style={{ borderLeft: "3px solid #e8002d", padding: 12 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: "0.8rem" }}>{run.label}</div>
                            <div className="muted" style={{ fontSize: "0.62rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>{winnerLabel}</div>
                          </div>
                          <button
                            className="btn-run"
                            style={{ padding: "0.45rem 0.7rem", fontSize: "0.7rem", margin: 0 }}
                            onClick={() => onLoad(run)}
                          >
                            Load
                          </button>
                        </div>
                        <div className="muted" style={{ fontSize: "0.7rem", marginTop: 6 }}>
                          {run.state.year} · {run.state.race} · {run.state.driver} vs {run.state.rival}
                        </div>
                        <div style={{ marginTop: 10, marginBottom: 8 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.68rem", marginBottom: 4 }}>
                            <span className="muted">Win rate</span>
                            <span>{winRate > 0 ? `${(winRate * 100).toFixed(0)}%` : "—"}</span>
                          </div>
                          <div style={{ height: 7, width: "100%", borderRadius: 999, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                            <div
                              style={{
                                height: "100%",
                                width: `${bestWinRate > 0 ? Math.max(8, (winRate / bestWinRate) * 100) : 0}%`,
                                borderRadius: 999,
                                background: index === 0 ? "linear-gradient(90deg, #e8002d, #ff7a7a)" : "linear-gradient(90deg, #00d2be, #7ef5e4)",
                              }}
                            />
                          </div>
                        </div>
                        <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
                          <div>
                            <div className="lbl">Best strategy</div>
                            <div className="val" style={{ color: "#fff", fontSize: "0.8rem" }}>{strategyText}</div>
                          </div>
                          <div>
                            <div className="lbl">Mean time</div>
                            <div className="val" style={{ color: index === 0 ? "#e8002d" : "#fff" }}>
                              {meanTime != null ? `${meanTime.toFixed(1)}s` : "—"}
                              {bestMeanTime != null && meanTime != null && index > 0 && (
                                <span style={{ marginLeft: 8, color: "#ffd166", fontSize: "0.7rem" }}>
                                  {`+${delta.toFixed(2)}s`}
                                </span>
                              )}
                            </div>
                          </div>
                          <div>
                            <div className="lbl">Win rate</div>
                            <div className="val" style={{ color: "#ffd700" }}>
                              {best?.win_rate != null ? `${(best.win_rate * 100).toFixed(0)}%` : "—"}
                            </div>
                          </div>
                          <div>
                            <div className="lbl">Pit laps</div>
                            <div className="val" style={{ color: "#fff", fontSize: "0.75rem" }}>
                              {(best?.pit_laps && best.pit_laps.length ? best.pit_laps.join(", ") : "—")}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Overview(props: any) {
  const { timing, driver, circuit, race, strategies, tyreSummary, rivalData, raceLaps, status, nSims, weather, pitLoss, optimal, backtest, lapTraces, roster = {} } = props;
  return (
    <div className="grid">
      {(optimal || weather || pitLoss != null) && (
        <div className="panel span-full">
          <div className="panel-header"><span className="title">Session Metrics</span></div>
          <div className="panel-body">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
              <div className="ev-block">
                <div className="lbl">Optimal</div>
                <div className="val" style={{ color: "#e8002d", fontSize: "0.85rem" }}>
                  {optimal ? <CompoundSequence compounds={optimal.compound_sequence} /> : "—"}
                </div>
                <div className="sub">{optimal?.mean_time != null ? `${optimal.mean_time.toFixed(1)}s` : "run sim"}</div>
              </div>
              <div className="ev-block">
                <div className="lbl">Pit loss</div>
                <div className="val" style={{ color: "#fff" }}>{pitLoss != null ? `${Number(pitLoss).toFixed(1)}s` : "—"}</div>
              </div>
              <div className="ev-block">
                <div className="lbl">Track temp</div>
                <div className="val" style={{ color: "#fff" }}>{weather?.track_temp != null ? `${weather.track_temp.toFixed(0)}°C` : "—"}</div>
                <div className="sub">{weather?.rainfall ? "RAIN" : "Dry"}</div>
              </div>
              <div className="ev-block">
                <div className="lbl">Cliff (SOFT)</div>
                <div className="val" style={{ color: "#e8002d" }}>
                  {(() => { const s = (tyreSummary || []).find((x: any) => x.compound === "SOFT"); return s?.cliff_lap != null ? `L${s.cliff_lap.toFixed(0)}` : "—"; })()}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-header"><span className="title">Timing Tower</span><span>{timing.length} CARS</span></div>
        <div className="panel-body no-pad">
          {timing.length === 0 ? (
            <div className="muted" style={{ padding: "1rem" }}>{status === "loading" ? "Loading…" : "No classification"}</div>
          ) : (
            <>
              <div className="tt-row" style={{ background: "var(--off)", fontSize: "0.55rem", color: "var(--dim)" }}>
                <div>POS</div><div>NO</div><div>DRIVER</div>
                <div style={{ textAlign: "right" }}>GAP</div>
                <div style={{ textAlign: "right" }}>INT</div>
                <div style={{ textAlign: "center" }}>TYRE</div>
              </div>
              {timing.map((r: TimingRow) => (
                <div key={r.driver + String(r.pos)} className={`tt-row${r.driver === driver ? " selected" : ""}`}>
                  <div className="tt-pos">{r.pos ?? "—"}</div>
                  <div className="tt-code" style={{ color: r.team_color || "#888" }}>{r.driver}</div>
                  <div style={{ fontSize: "0.68rem", color: "var(--dim)" }}>{r.name}</div>
                  <div className="tt-gap">{r.pos === 1 || r.gap === 0 ? "LEADER" : r.gap == null ? "—" : `+${r.gap.toFixed(3)}`}</div>
                  <div className="tt-int">—</div>
                  <div className="tt-age">
                    <CompoundPill c={r.compound} size="sm" />
                    <span>{r.tyre_age ?? "—"}</span>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><span className="title">Track Map</span><span>{backtest ? "SIM REPLAY" : "LIVE"}</span></div>
        <div className="panel-body no-pad">
          <TrackMap circuit={circuit} race={race} nodes={timing.slice(0, 12).map((r: TimingRow) => ({
            code: r.driver, compound: r.compound || undefined, color: r.team_color, selected: r.driver === driver,
          }))} replayLaps={backtest?.optimal?.lap_times ?? lapTraces?.[0]?.lap_times ?? []} />
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><span className="title">Driver / Rival</span></div>
        <div className="panel-body">
          <div className="drv-node selected">
            <div className="drv-node-top">
              <span className="drv-node-code" style={{ color: displayColor(driver, roster) }}>{driver}</span>
              <span className="drv-node-team">{displayTeam(driver, roster)}</span>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ marginBottom: 6 }}>vs {rivalData?.rival_code || "—"}</div>
            <div className="ev-row">
              <div className="ev-block" style={{ borderLeft: "2px solid var(--red)" }}>
                <div className="lbl">UNDERCUT</div>
                <div className="val" style={{ color: "var(--red)" }}>
                  {rivalData?.undercut_best_ev != null ? `${rivalData.undercut_best_ev >= 0 ? "+" : ""}${rivalData.undercut_best_ev.toFixed(2)}s` : "—"}
                </div>
              </div>
              <div className="ev-block" style={{ borderLeft: "2px solid var(--teal)" }}>
                <div className="lbl">OVERCUT</div>
                <div className="val" style={{ color: "var(--teal)" }}>
                  {rivalData?.overcut_best_ev != null ? `${rivalData.overcut_best_ev >= 0 ? "+" : ""}${rivalData.overcut_best_ev.toFixed(2)}s` : "—"}
                </div>
              </div>
            </div>
          </div>
          <div className="chip-row" style={{ marginTop: 12 }}>
            {tyreSummary.map((t: any) => (
              <div key={t.compound} className="chip" style={{ borderLeft: `3px solid ${compoundStyle(t.compound).fill}` }}>
                <CompoundPill c={t.compound} size="sm" />
                <span>CLIFF {t.cliff_lap != null ? t.cliff_lap.toFixed(1) : "—"}</span>
              </div>
            ))}
          </div>
          <div className="muted" style={{ marginTop: 10 }}>
            L{status === "ready" ? raceLaps : 0}/{raceLaps || "—"} · MC {status === "ready" ? nSims : 0}
          </div>
        </div>
      </div>
      <div className="panel span-full">
        <div className="panel-header"><span className="title">Top Strategies</span></div>
        <div className="panel-body">
          {strategies.length === 0 ? <div className="muted">Run simulation to populate</div> : (
            strategies.slice(0, 5).map((s: any) => (
              <div key={s.rank} className="strat-row">
                <div style={{ color: "var(--dim)" }}>#{s.rank}</div>
                <div>
                  <div><CompoundSequence compounds={s.compound_sequence} /></div>
                  <div style={{ color: "var(--dim)", fontSize: "0.58rem" }}>PIT {(s.pit_laps || []).join(",") || "—"}</div>
                </div>
                <div style={{ textAlign: "right" }}>{s.mean_time != null ? `${s.mean_time.toFixed(1)}s` : "—"}</div>
                <div style={{ textAlign: "right", color: "var(--dim)" }}>
                  {s.win_rate != null ? `${(s.win_rate * 100).toFixed(0)}%` : ""}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function StrategyTab({ strategies, lapTraces, ready, stopComparison, optimal }: any) {
  const bars = strategies.slice(0, 20).map((s: any) => ({
    label: (s.compound_sequence || []).join("→") || s.strategy || `#${s.rank}`,
    value: s.mean_time ?? 0,
    color: s.pit_count === 1 ? "#e8002d" : "#ffd700",
  }));
  const traces = (lapTraces || []).map((t: any, i: number) => ({
    name: t.label?.slice(0, 24) || `S${i + 1}`,
    color: TRACE_COLORS[i % TRACE_COLORS.length],
    points: (t.lap_times || []).map((lt: number, idx: number) => ({ x: idx + 1, y: lt })),
  }));
  return (
    <div className="detail-grid">
      {stopComparison && (stopComparison.best_1stop || stopComparison.best_2stop) && (
        <div className="panel span-full">
          <div className="panel-header"><span className="title">1-Stop vs 2-Stop</span></div>
          <div className="panel-body">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {stopComparison.best_1stop && (
                <div className="ev-block" style={{ borderLeft: "2px solid #e8002d" }}>
                  <div className="lbl">Best 1-Stop</div>
                  <div className="val" style={{ color: "#e8002d", fontSize: "0.95rem" }}>{stopComparison.best_1stop.strategy}</div>
                  <div className="sub">{stopComparison.best_1stop.mean_time.toFixed(2)}s · WR {stopComparison.best_1stop.win_rate != null ? `${(stopComparison.best_1stop.win_rate * 100).toFixed(0)}%` : "—"}</div>
                </div>
              )}
              {stopComparison.best_2stop && (
                <div className="ev-block" style={{ borderLeft: "2px solid #ffd700" }}>
                  <div className="lbl">Best 2-Stop</div>
                  <div className="val" style={{ color: "#ffd700", fontSize: "0.95rem" }}>{stopComparison.best_2stop.strategy}</div>
                  <div className="sub">{stopComparison.best_2stop.mean_time.toFixed(2)}s · WR {stopComparison.best_2stop.win_rate != null ? `${(stopComparison.best_2stop.win_rate * 100).toFixed(0)}%` : "—"}</div>
                </div>
              )}
            </div>
            {stopComparison.faster && (
              <div className="muted" style={{ marginTop: 10 }}>
                <strong style={{ color: "#fff" }}>{stopComparison.faster.toUpperCase()}</strong> faster by {stopComparison.delta_seconds?.toFixed(2)}s in expectation
              </div>
            )}
          </div>
        </div>
      )}
      <div className="panel">
        <div className="panel-header"><span className="title">Strategy Comparison</span> — Mean Race Time</div>
        <div className="panel-body">
          {!ready ? <div className="muted">Run simulation first</div> : <BarChart items={bars} height={280} />}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><span className="title">Lap Trace</span> — Top 3 Strategies</div>
        <div className="panel-body">
          {!traces.length ? <div className="muted">Run simulation first</div> : (
            <LineChart series={traces} xLabel="Lap" yLabel="Lap time (s)" height={280} />
          )}
        </div>
      </div>
      {optimal && (
        <div className="panel span-full">
          <div className="panel-header"><span className="title">Best Strategy Distribution</span></div>
          <div className="panel-body">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
              {[
                ["P10", optimal.p10],
                ["P50", optimal.p50],
                ["P90", optimal.p90],
                ["WIN", optimal.win_rate != null ? optimal.win_rate * 100 : null],
              ].map(([k, v]) => (
                <div key={String(k)} className="ev-block">
                  <div className="lbl">{k}</div>
                  <div className="val" style={{ color: "var(--white)" }}>
                    {v != null ? (k === "WIN" ? `${Number(v).toFixed(0)}%` : `${Number(v).toFixed(1)}s`) : "—"}
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
    points: (c.ages || []).map((a: number, i: number) => ({ x: a, y: c.lap_times[i] })),
  }));
  const cliffs = (curves || [])
    .filter((c: any) => c.cliff_lap != null)
    .map((c: any) => ({ x: c.cliff_lap, color: TYRE[c.compound] || "#e8002d", label: `${c.compound} cliff` }));
  const scatterPts = (scatter || []).map((p: any) => ({
    x: p.tyre_age, y: p.lap_time, color: TYRE[(p.compound || "").toUpperCase()] || "#888",
  }));
  return (
    <div className="detail-grid">
      <div className="panel">
        <div className="panel-header"><span className="title">Degradation Curves</span> — 3-Phase Piecewise</div>
        <div className="panel-body">
          {!series.length ? <div className="muted">Run simulation first</div> : (
            <LineChart series={series} cliffMarks={cliffs} xLabel="Tyre age" yLabel="Lap time (s)" height={260} />
          )}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><span className="title">Stint Scatter</span></div>
        <div className="panel-body">
          <ScatterChart points={scatterPts} height={260} />
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><span className="title">Cliff / Fit</span></div>
        <div className="panel-body">
          {(tyreSummary || []).map((t: any) => (
            <div key={t.compound} style={{ marginBottom: 10, borderBottom: "1px solid #1e1e1e", paddingBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <CompoundPill c={t.compound} size="sm" />
                <strong>{t.compound}</strong>
                <span className="muted">{t.fit_mode || ""}</span>
              </div>
              <div className="muted">
                Cliff {t.cliff_lap != null ? `L${t.cliff_lap.toFixed(1)}` : "none"}
                {t.cliff_ci_low != null && ` · CI [${t.cliff_ci_low.toFixed(1)}, ${t.cliff_ci_high.toFixed(1)}]`}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><span className="title">Phase Slopes</span> — s/lap</div>
        <div className="panel-body">
          <table className="data-table">
            <thead><tr><th>Compound</th><th>Bedding</th><th>Plateau</th><th>Cliff</th></tr></thead>
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
        <div className="panel-header"><span className="title">Model Summary</span></div>
        <div className="panel-body" style={{ overflowX: "auto" }}>
          {/* This table was previously fetched from the backend (the
              `summary` prop, i.e. model_summary from /api/simulate) but
              never rendered anywhere — a real gap versus dashboard.py's
              "Model Summary" table, found during the final parity audit
              before retiring dashboard.py. */}
          {!summary || !summary.length ? <div className="muted">Run simulation first</div> : (
            <table className="data-table">
              <thead>
                <tr>
                  {Object.keys(summary[0]).map((k) => <th key={k}>{k}</th>)}
                </tr>
              </thead>
              <tbody>
                {summary.map((row: any, i: number) => (
                  <tr key={i}>
                    {Object.keys(summary[0]).map((k) => (
                      <td key={k}>{row[k] === null || row[k] === undefined ? "—" : String(row[k])}</td>
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

function UndercutTab({ strategies, raceLaps, year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp }: any) {
  // `strategies`/`raceLaps` are used below to pass precomputed data to the
  // undercut-plot request (avoiding a full backend recompute — see
  // docs/decisions.md). `cells` (the raw heatmap grid) was previously
  // destructured here too but never used — this tab renders the
  // server-generated PNG heatmap instead of a client-side one, so that
  // prop was genuinely dead code. Removed here and at the call site
  // rather than silencing the warning with `void cells;`.
  const [imgUrlLeft, setImgUrlLeft] = useState<string | null>(null);
  const [imgUrlRight, setImgUrlRight] = useState<string | null>(null);
  const [imgUrlCompare, setImgUrlCompare] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      try {
        const body: any = {
          year: year || 2024,
          race: race || "",
          driver: driver || "VER",
          rival: rival || "NOR",
          n_simulations: nSims || 200,
          strategy_type: strategyType || "Both",
          noise_std: noise || 0.3,
          use_live_temp: useLiveTemp ?? true,
          track_temp_override: useLiveTemp ? undefined : manualTemp,
          // race_laps was previously missing entirely, so even when the
          // fast path below was taken the backend received race_laps=0
          // and generated the heatmap with a meaningless lap range.
          race_laps: raceLaps || 0,
        };
        // Use the strategies this component already received as a prop —
        // this is the same data /api/simulate returned for the CURRENT
        // year/race/driver/rival selection. The previous implementation
        // read from (window as any).__SIMULATION_PAYLOAD / .sim instead:
        // functionally similar in the common case, but it opens a real
        // staleness window — if this effect re-fires (e.g. the user
        // changed race) before a fresh /api/simulate call finishes, the
        // global could still hold the PREVIOUS race's strategies, and
        // nothing here would catch the mismatch — the backend has no way
        // to know mc_results doesn't correspond to the year/race also in
        // this same request body, so it would silently render the wrong
        // race's heatmap. Using the prop ties this directly to the same
        // render pass, and it's also just proper React data flow instead
        // of global mutable state smuggled through `window`.
        if (strategies && strategies.length) {
          body.mc_results = strategies;
        }
        // As a stronger default, try reading the global `sim` injected by the app
        // (we'll set it below when simulation completes)
        // Fetch undercut image (from MC results)
        const uReq = api.undercutPlot(body);
        // Also request rival scan to build compare plot — prefer cached sim rival data
        let rScan: RivalAnalysisResult | null = null;
        try {
          rScan = await api.rivalAnalysis({ year, race, driver, rival: rival || "NOR", rival_compound: "MEDIUM", rival_tyre_age: 10, gap_to_rival: 2.0, scan_from_lap: Math.max(8, Math.floor((raceLaps||57)/4)), scan_to_lap: Math.min((raceLaps||57)-8, Math.floor((raceLaps||57)/2)+5), our_compound: "MEDIUM", our_tyre_age: 10, new_compound: "SOFT", n_simulations: Math.min(150, Math.max(50, Math.floor(nSims/3))), noise_std: noise, run_h2h: false });
        } catch (e) {
          rScan = null;
        }

        // Fetch undercut image
        try {
          const res = await uReq;
          if (res && res.ok) {
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            if (mounted) setImgUrlLeft(url);
          }
        } catch (e) {
          console.error(e);
        }

        // Fetch overcut image (prefer precomputed rival scan if available)
        try {
          const oBody: any = { year, race, driver, rival: rival || "NOR", n_simulations: Math.min(150, Math.max(50, Math.floor(nSims/3))), noise_std: noise };
          if (rScan && rScan.overcut_timeline) oBody.overcut_timeline = rScan.overcut_timeline;
          const oRes = await api.overcutPlot(oBody);
          if (oRes && oRes.ok) {
            const b = await oRes.blob();
            const url = URL.createObjectURL(b);
            if (mounted) setImgUrlRight(url);
          }
        } catch (e) {
          console.error(e);
        }

        // If we have scan data, request compare plot (undercut vs overcut) and show below
        if (rScan && rScan.undercut_timeline && rScan.overcut_timeline) {
          try {
            const cmpRes = await api.rivalComparePlot({ undercut_scan: rScan.undercut_timeline, overcut_scan: rScan.overcut_timeline, rival: rival || "NOR", driver });
            if (cmpRes.ok) {
              const b2 = await cmpRes.blob();
              const url2 = URL.createObjectURL(b2);
              if (mounted) setImgUrlCompare(url2);
            }
          } catch (e) {
            console.error(e);
          }
        }
      } catch (e) {
        console.error(e);
      } finally { setLoading(false); }
    }
    load();
    return () => { mounted = false; if (imgUrlLeft) URL.revokeObjectURL(imgUrlLeft); if (imgUrlRight) URL.revokeObjectURL(imgUrlRight); if (imgUrlCompare) URL.revokeObjectURL(imgUrlCompare); };
    // Deliberately re-fetch whenever any input that affects the plots
    // changes — the previous empty dependency array meant switching race,
    // driver, or rival after this tab first loaded left stale PNGs on
    // screen from whatever combination was active on mount.
  }, [year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp]);

  return (
    <div className="detail-grid">
      <div className="panel span-full">
        <div className="panel-header"><span className="title">Undercut Window</span> — Exact Plot</div>
        <div className="panel-body">
          {loading ? <div className="muted">Generating plots…</div> : (
            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ width: "100%" }}>{imgUrlLeft ? <img src={imgUrlLeft} alt="Undercut window" style={{ width: "100%" }} /> : <div className="muted">No undercut image</div>}</div>
              <div style={{ width: "100%" }}>{imgUrlRight ? <img src={imgUrlRight} alt="Overcut window" style={{ width: "100%" }} /> : <div className="muted">No overcut image</div>}</div>
              <div style={{ width: "100%" }}>{imgUrlCompare ? <img src={imgUrlCompare} alt="Undercut vs Overcut" style={{ width: "100%" }} /> : <div className="muted">No compare image</div>}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RivalTab(props: any) {
  const {
    rival, fallbackRival, rivalResult, rivalBusy,
    year, race, driver, raceLaps, circuit,
    rivalCompound, setRivalCompound, rivalTyreAge, setRivalTyreAge,
    gapToRival, setGapToRival, scanFrom, setScanFrom, scanTo, setScanTo,
    ourCompound, setOurCompound, ourTyreAge, setOurTyreAge,
    newCompound, setNewCompound, onRunRival,
  } = props;
  const r = rivalResult || {};
  const underTL = r.undercut_timeline || rival?.undercut_timeline || [];
  const overTL = r.overcut_timeline || rival?.overcut_timeline || [];
  const rec = r.recommendation;

  return (
    <div className="detail-grid">
      <div className="panel span-full">
        <div className="panel-header"><span className="title">Rival Configuration</span></div>
        <div className="panel-body">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Rival compound</label>
              <select value={rivalCompound} onChange={(e) => setRivalCompound(e.target.value)}>
                {["SOFT","MEDIUM","HARD"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Rival tyre age ({rivalTyreAge})</label>
              <input type="range" min={1} max={35} value={rivalTyreAge} onChange={(e) => setRivalTyreAge(Number(e.target.value))} />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Gap to rival (s, + they lead) {gapToRival}</label>
              <input type="range" min={-10} max={15} step={0.5} value={gapToRival} onChange={(e) => setGapToRival(Number(e.target.value))} />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Our compound now</label>
              <select value={ourCompound} onChange={(e) => setOurCompound(e.target.value)}>
                {["SOFT","MEDIUM","HARD"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Our tyre age ({ourTyreAge})</label>
              <input type="range" min={1} max={35} value={ourTyreAge} onChange={(e) => setOurTyreAge(Number(e.target.value))} />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Compound after pit</label>
              <select value={newCompound} onChange={(e) => setNewCompound(e.target.value)}>
                {["SOFT","MEDIUM","HARD"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Scan from lap ({scanFrom})</label>
              <input type="range" min={1} max={Math.max(2, (raceLaps || 50) - 10)} value={scanFrom}
                onChange={(e) => setScanFrom(Number(e.target.value))} />
            </div>
            <div className="sb-field" style={{ padding: 0 }}>
              <label>Scan to lap ({scanTo})</label>
              <input type="range" min={scanFrom + 1} max={Math.max(scanFrom + 2, (raceLaps || 50) - 2)} value={scanTo}
                onChange={(e) => setScanTo(Number(e.target.value))} />
            </div>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <button className="btn-run" style={{ width: "100%", margin: 0 }} disabled={rivalBusy || !race} onClick={onRunRival}>
                {rivalBusy ? "SCANNING…" : "▶  RUN RIVAL ANALYSIS"}
              </button>
            </div>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>vs {fallbackRival} · {year} {race}</div>
        </div>
      </div>

      {rec && (
        <div className="panel span-full">
          <div className="panel-header"><span className="title">AI Recommendation</span></div>
          <div className="panel-body">
            <strong style={{ color: rec.winner === "UNDERCUT" ? "#e8002d" : "#00d2be" }}>{rec.winner}</strong>
            {" "}is the stronger play · Best EV <strong>+{rec.best_ev.toFixed(2)}s</strong>
            <div className="muted" style={{ marginTop: 4 }}>
              Favourable laps — undercut: {rec.undercut_favourable_laps} · overcut: {rec.overcut_favourable_laps}
            </div>
          </div>
        </div>
      )}

      <RivalReplay
        rivalResult={rivalResult}
        circuit={circuit}
        race={race}
        driver={driver}
        rivalCode={fallbackRival}
      />

      <div className="panel">
        <div className="panel-header"><span className="title">Undercut EV Timeline</span></div>
        <div className="panel-body">
          <EvTimeline points={underTL} color="#e8002d" label="Undercut" />
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><span className="title">Overcut EV Timeline</span></div>
        <div className="panel-body">
          <EvTimeline points={overTL} color="#00d2be" label="Overcut" />
        </div>
      </div>

      <div className="panel span-full">
        <div className="panel-header"><span className="title">Undercut vs Overcut</span></div>
        <div className="panel-body">
          <div className="ev-row">
            <div className="ev-block" style={{ borderLeft: "2px solid var(--red)" }}>
              <div className="lbl">UNDERCUT BEST</div>
              <div className="val" style={{ color: "var(--red)" }}>
                {r.best_undercut ? `${r.best_undercut.mean_ev >= 0 ? "+" : ""}${r.best_undercut.mean_ev.toFixed(2)}s` : (rival?.undercut_best_ev != null ? `${rival.undercut_best_ev.toFixed(2)}s` : "—")}
              </div>
              <div className="sub">L{r.best_undercut?.lap ?? rival?.undercut_best_lap ?? "—"}</div>
            </div>
            <div className="ev-block" style={{ borderLeft: "2px solid var(--teal)" }}>
              <div className="lbl">OVERCUT BEST</div>
              <div className="val" style={{ color: "var(--teal)" }}>
                {r.best_overcut ? `${r.best_overcut.mean_ev >= 0 ? "+" : ""}${r.best_overcut.mean_ev.toFixed(2)}s` : (rival?.overcut_best_ev != null ? `${rival.overcut_best_ev.toFixed(2)}s` : "—")}
              </div>
              <div className="sub">L{r.best_overcut?.lap ?? rival?.overcut_best_lap ?? "—"}</div>
            </div>
          </div>
        </div>
      </div>

      {(underTL.length > 0 || overTL.length > 0) && (
        <div className="panel span-full">
          <div className="panel-header"><span className="title">Raw Scan Data</span></div>
          <div className="panel-body" style={{ overflowX: "auto" }}>
            <div className="muted" style={{ marginBottom: 6 }}>Undercut</div>
            <table className="data-table">
              <thead><tr><th>Lap</th><th>Mean EV</th><th>P10</th><th>P90</th><th>Win%</th><th>Rec</th></tr></thead>
              <tbody>
                {underTL.map((row: any) => (
                  <tr key={"u"+row.lap}>
                    <td>{row.lap}</td><td>{row.mean_ev.toFixed(3)}</td><td>{row.p10_ev.toFixed(3)}</td>
                    <td>{row.p90_ev.toFixed(3)}</td><td>{(row.win_rate*100).toFixed(1)}%</td>
                    <td>{row.recommend ? "✓" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="muted" style={{ margin: "12px 0 6px" }}>Overcut</div>
            <table className="data-table">
              <thead><tr><th>Lap</th><th>Mean EV</th><th>P10</th><th>P90</th><th>Win%</th><th>Rec</th></tr></thead>
              <tbody>
                {overTL.map((row: any) => (
                  <tr key={"o"+row.lap}>
                    <td>{row.lap}</td><td>{row.mean_ev.toFixed(3)}</td><td>{row.p10_ev.toFixed(3)}</td>
                    <td>{row.p90_ev.toFixed(3)}</td><td>{(row.win_rate*100).toFixed(1)}%</td>
                    <td>{row.recommend ? "✓" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(r.h2h || []).length > 0 && (
        <div className="panel span-full">
          <div className="panel-header"><span className="title">Head-to-Head</span> — Win Rate vs {fallbackRival}</div>
          <div className="panel-body">
            <BarChart
              items={r.h2h.slice(0, 12).map((h: any) => ({
                label: String(h.strategy).slice(0, 18),
                value: (h.win_rate ?? 0) * 100,
                color: (h.win_rate ?? 0) >= 0.5 ? "#39b54a" : "#e8002d",
              }))}
              height={220}
            />
            {r.h2h[0] && (
              <div style={{ marginTop: 10 }} className="muted">
                Best: <strong style={{ color: "#fff" }}>{r.h2h[0].strategy}</strong>
                {" "}· Win rate <strong style={{ color: (r.h2h[0].win_rate ?? 0) >= 0.5 ? "#39b54a" : "#e8002d" }}>
                  {((r.h2h[0].win_rate ?? 0) * 100).toFixed(0)}%
                </strong>
                {r.h2h[0].mean_final_gap != null && ` · Mean gap ${r.h2h[0].mean_final_gap.toFixed(2)}s`}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function BacktestTab({ backtest, driver, circuit, race }: any) {
  // useState/useEffect must run unconditionally on every render — they
  // were previously declared AFTER the `if (!backtest) return ...` early
  // exit below, which is a React Rules of Hooks violation: this component
  // calls zero hooks on the first render (before a simulation has run,
  // when backtest is null) and then calls two hooks once backtest becomes
  // populated. React detects this hook-count mismatch between renders and
  // throws ("Rendered fewer hooks than expected") the first time a user
  // actually runs a simulation and opens this tab. Fixed by declaring the
  // hooks first and guarding their *internal* logic on backtest instead.
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!backtest) return;
    let mounted = true;
    async function load() {
      setLoading(true);
      try {
        if (backtest.plot_url) {
          const urlFetch = backtest.plot_url;
          const res = await fetch(urlFetch);
          if (res && res.ok) {
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            if (mounted) setImgUrl(url);
          }
        } else {
          const res = await api.backtestPlot({ backtest });
          if (res && res.ok) {
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            if (mounted) setImgUrl(url);
          }
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
    return () => { mounted = false; if (imgUrl) URL.revokeObjectURL(imgUrl); };
  }, [backtest]);

  if (!backtest) {
    return (
      <div className="panel">
        <div className="panel-header"><span className="title">Backtest</span></div>
        <div className="panel-body">
          <div className="muted">Run simulation to compare AI optimal vs actual {driver} strategy. Requires stint data in the session.</div>
        </div>
      </div>
    );
  }
  const traces = [
    {
      name: backtest.actual.label,
      color: "#4c9be8",
      points: backtest.actual.lap_times.map((lt: number, i: number) => ({ x: i + 1, y: lt })),
    },
    {
      name: backtest.optimal.label,
      color: "#e8002d",
      points: backtest.optimal.lap_times.map((lt: number, i: number) => ({ x: i + 1, y: lt })),
    },
  ];
  const d = backtest.delta_seconds;
  const dColor = d > 0.5 ? "#e8002d" : d < -0.5 ? "#39b54a" : "#ffd700";
  return (
    <div className="detail-grid">
      <div className="panel span-full">
        <div className="panel-header"><span className="title">Backtest</span> — AI vs Actual</div>
        <div className="panel-body">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 16 }}>
            <div className="ev-block">
              <div className="lbl">Actual — {driver}</div>
              <div className="val" style={{ color: "#fff", fontSize: "0.95rem" }}>{backtest.actual.strategy}</div>
              <div className="sub">Pits: {(backtest.actual.pit_laps || []).join(", ") || "none"} · {backtest.actual.total_time.toFixed(1)}s</div>
            </div>
            <div className="ev-block" style={{ borderLeft: "2px solid var(--red)" }}>
              <div className="lbl">AI Optimal</div>
              <div className="val" style={{ color: "var(--red)", fontSize: "0.95rem" }}>{backtest.optimal.strategy}</div>
              <div className="sub">Pits: {(backtest.optimal.pit_laps || []).join(", ")} · {backtest.optimal.total_time.toFixed(1)}s</div>
            </div>
            <div className="ev-block" style={{ borderLeft: `2px solid ${dColor}` }}>
              <div className="lbl">Delta</div>
              <div className="val" style={{ color: dColor }}>{d >= 0 ? "+" : ""}{d.toFixed(2)}s</div>
              <div className="sub">Actual was <strong style={{ color: dColor }}>{backtest.verdict}</strong></div>
            </div>
          </div>
          {loading ? <div className="muted">Generating backtest plot…</div> : (
            imgUrl ? <img src={imgUrl} alt="Backtest lap trace" style={{ width: "100%" }} /> : <LineChart series={traces} xLabel="Lap" yLabel="Lap time (s)" height={260} />
          )}
        </div>
      </div>
      <BacktestReplay backtest={backtest} circuit={circuit} race={race} />
    </div>
  );
}

// Given a closed polyline (the real circuit outline from get_circuit_outline
// — normalized 0-1 x/y points) and a 0-1 progress fraction around the lap,
// returns the interpolated point along the track. Uses actual segment arc
// length rather than naive index interpolation, since outline points are
// not evenly spaced around the circuit.
function interpolateAlongPath(points: { x: number; y: number }[], progress: number): { x: number; y: number } {
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
  let lo = 0, hi = n;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dist[mid] < target) lo = mid + 1; else hi = mid;
  }
  const idx = Math.max(1, lo);
  const segStart = dist[idx - 1], segEnd = dist[idx];
  const t = segEnd > segStart ? (target - segStart) / (segEnd - segStart) : 0;
  const a = points[(idx - 1) % n], b = points[idx % n];
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

// Given cumulative lap-completion times and the per-lap durations, find
// which lap a given elapsed race time falls in and how far through that
// lap the driver is (0-1) — this feeds interpolateAlongPath's progress arg.
function lapProgressAt(cumTimes: number[], lapTimes: number[], t: number): { lap: number; progress: number } {
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
// once here and reused by both BacktestReplay (Actual vs AI Optimal) and
// RivalReplay (You vs a chosen rival) — the interpolation/animation logic
// is identical between them, only the two lap-time series, labels, and
// colors differ.
function RaceReplay({
  title, subtitle, resetKey, circuit,
  aLabel, aLapTimes, aColor,
  bLabel, bLapTimes, bColor,
  emptyMessage,
}: {
  title: string;
  subtitle: string;
  resetKey: unknown; // reset+autoplay whenever this changes (e.g. a new result object)
  circuit: any;
  aLabel: string; aLapTimes: number[]; aColor: string;
  bLabel: string; bLapTimes: number[]; bColor: string;
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
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(25); // race-seconds simulated per real second
  const rafRef = useRef<number | null>(null);
  const lastTsRef = useRef<number | null>(null);

  // Reset and auto-play whenever a genuinely new result arrives — not on
  // every re-render.
  useEffect(() => {
    setElapsed(0);
    setPlaying(true);
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
    return () => { if (rafRef.current != null) cancelAnimationFrame(rafRef.current); };
  }, [playing, speed, totalDuration]);

  if (!points.length || !aLapTimes.length || !bLapTimes.length) {
    return (
      <div className="panel span-full">
        <div className="panel-header"><span className="title">{title}</span></div>
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

  const pathD = `M ${points[0].x * 100} ${points[0].y * 100} ` +
    points.slice(1).map((p) => `L ${p.x * 100} ${p.y * 100}`).join(" ") + " Z";

  return (
    <div className="panel span-full">
      <div className="panel-header">
        <span className="title">{title}</span>
        <span>{subtitle}</span>
      </div>
      <div className="panel-body no-pad">
        <div className="replay-stage" style={{ position: "relative", width: "100%", background: "radial-gradient(ellipse at center, #0d0d0d 0%, #000 100%)" }}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style={{ width: "100%", height: "100%", display: "block" }}>
            <path d={pathD} fill="none" stroke="#1a1a1a" strokeWidth="6" strokeLinejoin="round" strokeLinecap="round" />
            <path d={pathD} fill="none" stroke="#2c2c2c" strokeWidth="3.4" strokeLinejoin="round" strokeLinecap="round" />
            <path d={pathD} fill="none" stroke="#484848" strokeWidth="1" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx={aPos.x * 100} cy={aPos.y * 100} r={2.4} fill={aColor} stroke="#000" strokeWidth="0.5" />
            <circle cx={bPos.x * 100} cy={bPos.y * 100} r={2.4} fill={bColor} stroke="#000" strokeWidth="0.5" />
          </svg>
          <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 14px 10px", fontSize: "0.72rem" }}>
            <span><span style={{ color: aColor }}>●</span> {aLabel} — Lap {aState.lap}/{aLapTimes.length}</span>
            <span><span style={{ color: bColor }}>●</span> {bLabel} — Lap {bState.lap}/{bLapTimes.length}</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px 12px" }}>
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
          <span className="muted" style={{ minWidth: 46, textAlign: "right", fontSize: "0.72rem" }}>
            {elapsed.toFixed(0)}s
          </span>
          <select
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            style={{ background: "var(--panel, #111)", color: "inherit", border: "1px solid #333", fontSize: "0.72rem", padding: "2px 4px" }}
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
      subtitle={`${race} — Actual vs AI Optimal`}
      resetKey={backtest}
      circuit={circuit}
      aLabel="Actual" aLapTimes={backtest?.actual?.lap_times || []} aColor="#4c9be8"
      bLabel="AI Optimal" bLapTimes={backtest?.optimal?.lap_times || []} bColor="#e8002d"
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
      aLabel={driver || "You"} aLapTimes={trace?.our_lap_times || []} aColor="#4c9be8"
      bLabel={rivalCode || "Rival"} bLapTimes={trace?.rival_lap_times || []} bColor="#ff8000"
      emptyMessage="Run the rival analysis to generate a race trace."
    />
  );
}

function ResultsTab({ strategies, onExport, onExportBackend, ready }: any) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="title">Full Results</span>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-export" onClick={onExport} disabled={!ready}>⬇ Export CSV</button>
          <button className="btn-export" onClick={onExportBackend} disabled={!ready}>⬇ Export CSV (backend)</button>
        </div>
      </div>
      <div className="panel-body" style={{ overflowX: "auto" }}>
        {!strategies.length ? <div className="muted">Run simulation first</div> : (
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th><th>Strategy</th><th>Pits</th><th>Mean</th><th>Std</th>
                <th>P10</th><th>P50</th><th>P90</th><th>Win%</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s: any) => (
                <tr key={s.rank}>
                  <td>{s.rank}</td>
                  <td><CompoundSequence compounds={s.compound_sequence} /></td>
                  <td>{(s.pit_laps || []).join(", ") || s.pit_count}</td>
                  <td>{s.mean_time?.toFixed(2)}</td>
                  <td>{s.std_time?.toFixed(2)}</td>
                  <td>{s.p10?.toFixed(2)}</td>
                  <td>{s.p50?.toFixed(2)}</td>
                  <td>{s.p90?.toFixed(2)}</td>
                  <td>{s.win_rate != null ? `${(s.win_rate * 100).toFixed(1)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function TrackMap({ circuit, race, nodes, replayLaps = [] }: any) {
  const points = circuit?.points ?? [];
  const label = (circuit?.name || race || "CIRCUIT").toUpperCase();
  const lapTimes: number[] = replayLaps.filter((value: unknown) => Number.isFinite(Number(value))).map(Number);
  const cumulativeTimes = useMemo(() => {
    const cumulative = [0];
    for (const lapTime of lapTimes) cumulative.push(cumulative[cumulative.length - 1] + lapTime);
    return cumulative;
  }, [replayLaps]);
  const totalDuration = cumulativeTimes[cumulativeTimes.length - 1] || 0;
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(25);
  const animationRef = useRef<number | null>(null);
  const lastTimestampRef = useRef<number | null>(null);
  const replayKey = lapTimes.join(",");

  useEffect(() => {
    setElapsed(0);
    setPlaying(false);
  }, [replayKey]);

  useEffect(() => {
    if (!playing || points.length < 2 || nodes.length === 0 || totalDuration <= 0) {
      lastTimestampRef.current = null;
      return;
    }

    const animate = (timestamp: number) => {
      if (lastTimestampRef.current == null) lastTimestampRef.current = timestamp;
      const elapsedSeconds = (timestamp - lastTimestampRef.current) / 1000;
      lastTimestampRef.current = timestamp;
      setElapsed((previous) => {
        const next = previous + elapsedSeconds * speed;
        if (next >= totalDuration) {
          setPlaying(false);
          return totalDuration;
        }
        return next;
      });
      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current != null) cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
      lastTimestampRef.current = null;
    };
  }, [nodes.length, playing, points.length, speed, totalDuration]);

  let pathD = "";
  if (points.length >= 2) {
    pathD = `M ${points[0].x * 100} ${points[0].y * 100} ` +
      points.slice(1).map((p: any) => `L ${p.x * 100} ${p.y * 100}`).join(" ");
  }
  return (
    <div className="track-wrap">
      {pathD ? (
        <svg viewBox="0 0 100 100">
          <path d={pathD} fill="none" stroke="#1a1a1a" strokeWidth="6" strokeLinejoin="round" />
          <path d={pathD} fill="none" stroke="#2e2e2e" strokeWidth="3.5" strokeLinejoin="round" />
          <path d={pathD} fill="none" stroke="#4a4a4a" strokeWidth="1.1" strokeLinejoin="round" />
          {nodes.map((n: any, i: number) => {
            const fieldOffset = totalDuration > 0 ? (i / Math.max(nodes.length, 1)) * totalDuration : 0;
            const raceTime = totalDuration > 0 ? (elapsed + fieldOffset) % totalDuration : 0;
            const state = totalDuration > 0 ? lapProgressAt(cumulativeTimes, lapTimes, raceTime) : { progress: 0 };
            const position = interpolateAlongPath(points, state.progress);
            const x = position.x;
            const y = position.y;
            const col = (n.compound && TYRE[n.compound.toUpperCase()]) || n.color || "#888";
            return (
              <g key={n.code}>
                <circle cx={x * 100} cy={y * 100} r={n.selected ? 3 : 2.1} fill={col}
                  stroke={n.selected ? "#fff" : undefined} strokeWidth={n.selected ? 0.7 : undefined} />
                <text
                  x={x * 100}
                  y={y * 100 - (n.selected ? 5 : 3.8)}
                  textAnchor="middle"
                  fill={n.selected ? "#ffffff" : "#d0d0d0"}
                  fontSize={n.selected ? "3.5" : "2.7"}
                  fontFamily="Antonio,sans-serif"
                  fontWeight={n.selected ? "700" : "600"}
                  paintOrder="stroke"
                  stroke="#080808"
                  strokeWidth={n.selected ? "0.7" : "0.45"}
                >{n.code}</text>
              </g>
            );
          })}
        </svg>
      ) : (
        <div className="muted" style={{ textAlign: "center", padding: "1rem" }}>
          Circuit geometry from FastF1 when available
        </div>
      )}
      <div className="track-caption">
        <span className="flag-chip"><RaceFlag race={race} size={18} /><span>{label}</span></span>
        <span>{nodes.length || "—"} NODES · {points.length || 0} PTS · {totalDuration > 0 ? `L${lapProgressAt(cumulativeTimes, lapTimes, elapsed).lap}/${lapTimes.length}` : "NO REPLAY"}</span>
      </div>
      {totalDuration > 0 && (
        <div className="track-replay-controls">
          <button
            className="btn-export"
            onClick={() => {
              if (elapsed >= totalDuration) {
                setElapsed(0);
                lastTimestampRef.current = null;
                setPlaying(true);
              } else {
                setPlaying((current) => !current);
              }
            }}
          >
            {playing ? "Pause" : elapsed >= totalDuration ? "Replay" : "Play"}
          </button>
          <input
            type="range"
            min={0}
            max={totalDuration}
            step={0.1}
            value={Math.min(elapsed, totalDuration)}
            aria-label="Track replay position"
            onChange={(event) => {
              setElapsed(Number(event.target.value));
              setPlaying(false);
              lastTimestampRef.current = null;
            }}
          />
          <span className="muted replay-time">{elapsed.toFixed(0)}s</span>
          <select value={speed} aria-label="Track replay speed" onChange={(event) => setSpeed(Number(event.target.value))}>
            <option value={10}>10x</option>
            <option value={25}>25x</option>
            <option value={50}>50x</option>
            <option value={100}>100x</option>
          </select>
        </div>
      )}
    </div>
  );
}
