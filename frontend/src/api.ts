const BASE = import.meta.env.VITE_API_URL ?? "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch { /* */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export type DriverEntry = {
  code: string;
  name: string;
  team: string;
  team_color: string | null;
  number: number | null;
};

export type TimingRow = {
  pos: number | null;
  driver: string;
  name?: string;
  team?: string;
  team_color?: string;
  gap?: number | null;
  interval?: number | null;
  compound?: string | null;
  tyre_age?: number | null;
  last_lap?: number | null;
  status?: string;
};

export type CircuitOutline = {
  name: string;
  points: { x: number; y: number }[];
  corners: { x: number; y: number; number: number }[];
};

export type StrategyRow = {
  rank: number;
  strategy?: string;
  compound_sequence: string[];
  pit_laps: number[];
  pit_count?: number;
  mean_time: number | null;
  std_time?: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  win_rate?: number | null;
};

export type TyreCurve = {
  compound: string;
  ages: number[];
  lap_times: number[];
  cliff_lap: number | null;
  cliff_ci: [number, number] | null;
  phase_slopes: Record<string, number>;
  fit_mode?: string | null;
};

export type StintPoint = {
  tyre_age: number;
  lap_time: number;
  compound: string;
  lap_number?: number | null;
};

export type LapTrace = {
  label: string;
  lap_times: number[];
  pit_laps: number[];
  total_time: number;
};

export type HeatCell = {
  pit_lap: number | null;
  compounds: string[];
  pair: string;
  mean_time: number | null;
  win_rate: number | null;
};

export type RivalTimelinePoint = {
  lap: number;
  mean_ev: number;
  p10_ev: number;
  p50_ev: number;
  p90_ev: number;
  win_rate: number;
  recommend: boolean;
};

export type RivalResult = {
  rival_code: string;
  undercut_best_ev: number | null;
  undercut_best_lap: number | null;
  overcut_best_ev: number | null;
  overcut_best_lap: number | null;
  win_rate_under: number | null;
  win_rate_over: number | null;
  recommended_window: [number, number] | null;
  undercut_timeline: RivalTimelinePoint[];
  overcut_timeline: RivalTimelinePoint[];
};

export type Backtest = {
  actual: {
    label: string;
    strategy: string;
    compound_sequence: string[];
    pit_laps: number[];
    total_time: number;
    lap_times: number[];
  };
  optimal: {
    label: string;
    strategy: string;
    pit_laps: number[];
    total_time: number;
    lap_times: number[];
    win_rate?: number | null;
  };
  delta_seconds: number;
  verdict: string;
};

export type SessionData = {
  year: number;
  race: string;
  race_laps: number;
  timing: TimingRow[];
  circuit: CircuitOutline;
  weather: { track_temp?: number; air_temp?: number; rainfall?: boolean } | null;
  session_drivers?: string[];
  drivers?: DriverEntry[];
};

export type SimulateResult = SessionData & {
  driver: string;
  strategies: StrategyRow[];
  tyre_summary: {
    compound: string;
    cliff_lap: number | null;
    cliff_ci_low: number | null;
    cliff_ci_high: number | null;
    fit_mode?: string | null;
  }[];
  tyre_curves: TyreCurve[];
  phase_slopes: { compound: string; bedding?: number; plateau?: number; cliff?: number }[];
  stint_scatter: StintPoint[];
  lap_traces: LapTrace[];
  undercut_heatmap: HeatCell[];
  backtest: Backtest | null;
  model_summary: Record<string, unknown>[];
  rival: RivalResult;
  n_simulations: number;
  pit_loss?: number;
  stop_comparison?: {
    best_1stop: { strategy: string; mean_time: number; win_rate: number | null; std_time: number | null } | null;
    best_2stop: { strategy: string; mean_time: number; win_rate: number | null; std_time: number | null } | null;
    faster?: string;
    delta_seconds?: number;
  } | null;
  optimal_strategy?: StrategyRow | null;
};

export type RivalAnalysisResult = {
  rival: string;
  driver: string;
  undercut_timeline: RivalTimelinePoint[];
  overcut_timeline: RivalTimelinePoint[];
  best_undercut: RivalTimelinePoint | null;
  best_overcut: RivalTimelinePoint | null;
  recommendation: {
    winner: string;
    best_ev: number;
    undercut_favourable_laps: number;
    overcut_favourable_laps: number;
  } | null;
  h2h: { strategy: string; win_rate: number | null; mean_final_gap?: number | null }[];
  scan_from_lap: number;
  scan_to_lap: number;
  pit_loss: number;
  race_laps: number;
  race_trace: {
    our_lap_times: number[];
    rival_lap_times: number[];
    our_pit_laps: number[];
    rival_pit_laps: number[];
    final_gap: number;
    we_won_position: boolean;
  } | null;
};


export const api = {
  demoRun: () => req<SimulateResult>("/api/demo/run"),
  health: () => req<{ status: string }>("/api/health"),
  latestSeason: () => req<{ year: number }>("/api/seasons/latest"),
  races: (year: number) =>
    req<{ year: number; races: string[] }>(`/api/seasons/${year}/races`),
  session: (year: number, race: string) =>
    req<SessionData>(`/api/session?year=${year}&race=${encodeURIComponent(race)}`),
  simulate: (body: {
    year: number;
    race: string;
    driver: string;
    rival: string;
    n_simulations: number;
    strategy_type: string;
    noise_std: number;
    use_live_temp: boolean;
  }) =>
    req<SimulateResult>("/api/simulate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  simulateCsv: (body: {
    year: number;
    race: string;
    driver: string;
    rival: string;
    n_simulations: number;
    strategy_type: string;
    noise_std: number;
    use_live_temp: boolean;
    track_temp_override?: number | null;
  }) =>
    fetch(`${BASE}/api/simulate/csv`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  undercutPlot: (body: {
    year: number;
    race: string;
    driver: string;
    rival: string;
    n_simulations: number;
    strategy_type: string;
    noise_std: number;
    use_live_temp: boolean;
    track_temp_override?: number | null;
  }) =>
    fetch(`${BASE}/api/undercut/plot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  rivalComparePlot: (body: Record<string, unknown>) =>
    fetch(`${BASE}/api/rival/compare-plot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  overcutPlot: (body: Record<string, unknown>) =>
    fetch(`${BASE}/api/overcut/plot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  backtestPlot: (body: Record<string, unknown>) =>
    fetch(`${BASE}/api/backtest/plot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  rivalAnalysis: (body: Record<string, unknown>) =>
    req<RivalAnalysisResult>("/api/rival-analysis", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
