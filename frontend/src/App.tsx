
import { useCallback, useEffect, useMemo, useState } from "react";
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
  HeatStrip,
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
  | "results";

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
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<SessionData | null>(null);
  const [sim, setSim] = useState<SimulateResult | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [useLiveTemp, setUseLiveTemp] = useState(true);
  const [manualTemp, setManualTemp] = useState(35);
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
    api.latestSeason().then((r) => { setLatestYear(r.year); setYear(r.year); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!year) return;
    api.races(year).then((r) => { setRaces(r.races); setRace(r.races[0] ?? ""); })
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

  const runSim = useCallback(async () => {
    if (!year || !race) return;
    setStatus("loading"); setError(null);
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
      });
      setStatus("ready");
      setTab("overview");
    } catch (e: unknown) {
      setStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp]);

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
        <button className="btn-run" disabled={status === "loading" || !race} onClick={runSim}>
          {status === "loading" ? "RUNNING…" : "▶  RUN SIMULATION"}
        </button>
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
          {tab === "overview" && (
            <Overview
              timing={timing} driver={driver} circuit={circuit} race={race}
              strategies={strategies} tyreSummary={tyreSummary}
              rivalData={rivalData} raceLaps={raceLaps} status={status} nSims={nSims}
              weather={weather} pitLoss={sim?.pit_loss} optimal={sim?.optimal_strategy}
              stopComparison={sim?.stop_comparison} roster={roster}
            />
          )}
          {tab === "strategy" && (
            <StrategyTab
              strategies={strategies}
              lapTraces={sim?.lap_traces ?? []}
              ready={status === "ready"}
              stopComparison={sim?.stop_comparison}
              optimal={sim?.optimal_strategy}
            />
          )}
          {tab === "tyres" && (
            <TyresTab
              curves={sim?.tyre_curves ?? []}
              scatter={sim?.stint_scatter ?? []}
              phaseSlopes={sim?.phase_slopes ?? []}
              summary={sim?.model_summary ?? []}
              tyreSummary={tyreSummary}
            />
          )}
          {tab === "undercut" && (
            <UndercutTab
              cells={sim?.undercut_heatmap ?? []}
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
          )}
          {tab === "rival" && (
            <RivalTab
              rival={rivalData}
              fallbackRival={rival}
              rivalResult={rivalResult}
              rivalBusy={rivalBusy}
              year={year} race={race} driver={driver} raceLaps={raceLaps}
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
          )}
          {tab === "backtest" && <BacktestTab backtest={sim?.backtest ?? null} driver={driver} />}
          {tab === "results" && (
            <ResultsTab
              strategies={strategies}
              onExport={exportCsv}
              onExportBackend={async () => {
                try {
                  const res = await api.simulateCsv({
                    year, race, driver, rival,
                    n_simulations: nSims, strategy_type: strategyType,
                    noise_std: noise, use_live_temp: useLiveTemp,
                    // Strategies are already computed and sitting in state
                    // from the initial simulate() call that rendered this
                    // tab — passing them through lets the backend skip a
                    // full session-reload + Monte Carlo re-run just to
                    // regenerate a CSV of data it already sent us once.
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
          )}
        </div>

        <div className="footer-note">
          React Mission Control · Full parity with dashboard.py · Circuit from FastF1
        </div>
      </div>
    </div>
  );
}

function Overview(props: any) {
  const { timing, driver, circuit, race, strategies, tyreSummary, rivalData, raceLaps, status, nSims, weather, pitLoss, optimal, stopComparison, roster = {} } = props;
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
        <div className="panel-header"><span className="title">Track Map</span><span>LIVE</span></div>
        <div className="panel-body no-pad">
          <TrackMap circuit={circuit} race={race} nodes={timing.slice(0, 12).map((r: TimingRow) => ({
            code: r.driver, compound: r.compound || undefined, color: r.team_color, selected: r.driver === driver,
          }))} />
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

function UndercutTab({ cells, strategies, raceLaps, year, race, driver, rival, nSims, strategyType, noise, useLiveTemp, manualTemp }: any) {
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
    year, race, driver, raceLaps,
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

function BacktestTab({ backtest, driver }: any) {
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
    </div>
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

function TrackMap({ circuit, race, nodes }: any) {
  const points = circuit?.points ?? [];
  const label = (circuit?.name || race || "CIRCUIT").toUpperCase();
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
            const angle = (2 * Math.PI * i) / Math.max(nodes.length, 1) - Math.PI / 2;
            const x = n.x ?? 0.5 + 0.32 * Math.cos(angle);
            const y = n.y ?? 0.5 + 0.28 * Math.sin(angle);
            const col = (n.compound && TYRE[n.compound.toUpperCase()]) || n.color || "#888";
            return (
              <g key={n.code}>
                <circle cx={x * 100} cy={y * 100} r={n.selected ? 3 : 2.1} fill={col}
                  stroke={n.selected ? "#fff" : undefined} strokeWidth={n.selected ? 0.7 : undefined} />
                {n.selected && (
                  <text x={x * 100} y={y * 100 - 5} textAnchor="middle" fill="#f5f5f5" fontSize="3.5"
                    fontFamily="Antonio,sans-serif" fontWeight="700">{n.code}</text>
                )}
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
        <span>{nodes.length || "—"} NODES · {points.length || 0} PTS</span>
      </div>
    </div>
  );
}
