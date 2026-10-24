/** Lightweight SVG charts — no external chart lib required */

const TYRE: Record<string, string> = {
  SOFT: "#E10600",
  MEDIUM: "#FFD12E",
  HARD: "#F0F0F0",
  INTER: "#39B54A",
  WET: "#0067FF",
};

const TRACE_COLORS = ["#e8002d", "#00d2be", "#ffd700", "#4c9be8"];

type Pt = { x: number; y: number };

function scale(pts: Pt[], w: number, h: number, pad = 28) {
  if (!pts.length)
    return { sx: (_x: number) => 0, sy: (_y: number) => 0, minY: 0, maxY: 1 };
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const dx = Math.max(maxX - minX, 1e-9);
  const dy = Math.max(maxY - minY, 1e-9);
  return {
    sx: (x: number) => pad + ((x - minX) / dx) * (w - 2 * pad),
    sy: (y: number) => h - pad - ((y - minY) / dy) * (h - 2 * pad),
    minY,
    maxY,
    minX,
    maxX,
  };
}

export function LineChart({
  series,
  width = 560,
  height = 220,
  xLabel = "",
  yLabel = "",
  cliffMarks = [],
}: {
  series: { name: string; color: string; points: Pt[] }[];
  width?: number;
  height?: number;
  xLabel?: string;
  yLabel?: string;
  cliffMarks?: { x: number; color: string; label?: string }[];
}) {
  const all = series.flatMap((s) => s.points);
  if (!all.length) {
    return <div className="muted">No data</div>;
  }
  const { sx, sy, minY, maxY } = scale(all, width, height);
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      style={{ maxHeight: height }}
    >
      {/* grid */}
      {[0.25, 0.5, 0.75].map((t) => {
        const y = height * t;
        return (
          <line
            key={t}
            x1={28}
            x2={width - 28}
            y1={y}
            y2={y}
            stroke="#30363d"
            strokeWidth={1}
          />
        );
      })}
      {series.map((s) => {
        if (s.points.length < 2) return null;
        const d = s.points
          .map(
            (p, i) =>
              `${i === 0 ? "M" : "L"} ${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`,
          )
          .join(" ");
        return (
          <path
            key={s.name}
            d={d}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
          />
        );
      })}
      {cliffMarks.map((m, i) => (
        <g key={i}>
          <line
            x1={sx(m.x)}
            x2={sx(m.x)}
            y1={28}
            y2={height - 28}
            stroke={m.color}
            strokeWidth={1}
            strokeDasharray="4 3"
            opacity={0.8}
          />
          <text
            x={sx(m.x) + 3}
            y={40}
            fill={m.color}
            fontSize={10}
            fontFamily="system-ui"
          >
            {m.label || `cliff ${m.x.toFixed(0)}`}
          </text>
        </g>
      ))}
      <text
        x={width / 2}
        y={height - 6}
        textAnchor="middle"
        fill="#a5adb7"
        fontSize={10}
      >
        {xLabel}
      </text>
      <text
        x={12}
        y={height / 2}
        textAnchor="middle"
        fill="#a5adb7"
        fontSize={10}
        transform={`rotate(-90 12 ${height / 2})`}
      >
        {yLabel} ({minY.toFixed(1)}–{maxY.toFixed(1)})
      </text>
      {/* legend */}
      {series.map((s, i) => (
        <g key={s.name} transform={`translate(${40 + i * 90}, 14)`}>
          <rect width={12} height={3} y={-2} fill={s.color} />
          <text
            x={16}
            y={2}
            fill="#a5adb7"
            fontSize={10}
            fontFamily="system-ui"
          >
            {s.name}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function ScatterChart({
  points,
  width = 560,
  height = 220,
}: {
  points: { x: number; y: number; color: string }[];
  width?: number;
  height?: number;
}) {
  if (!points.length) return <div className="muted">No stint points</div>;
  const { sx, sy } = scale(
    points.map((p) => ({ x: p.x, y: p.y })),
    width,
    height,
  );
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      style={{ maxHeight: height }}
    >
      {points.map((p, i) => (
        <circle
          key={i}
          cx={sx(p.x)}
          cy={sy(p.y)}
          r={3}
          fill={p.color}
          opacity={0.75}
        />
      ))}
      <text
        x={width / 2}
        y={height - 6}
        textAnchor="middle"
        fill="#a5adb7"
        fontSize={10}
      >
        Tyre age (laps)
      </text>
    </svg>
  );
}

export function BarChart({
  items,
  width = 560,
  height = 320,
  unit = "",
}: {
  items: { label: string; value: number; color?: string }[];
  width?: number;
  height?: number;
  unit?: string;
}) {
  if (!items.length) return <div className="muted">No strategies</div>;
  const max = Math.max(...items.map((item) => Math.abs(item.value)), 1);
  const labelWidth = 150;
  const rowHeight = (height - 20) / items.length;
  const usableWidth = width - labelWidth - 75;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      role="img"
      aria-label={`Strategy comparison in ${unit || "values"}`}
    >
      {items.map((item, index) => {
        const y = index * rowHeight + 10;
        const barWidth = Math.max(
          2,
          (Math.abs(item.value) / max) * usableWidth,
        );
        return (
          <g key={index}>
            <title>
              {item.label}: {item.value.toFixed(2)} {unit}
            </title>
            <text
              x={0}
              y={y + rowHeight / 2 + 3}
              fill="#a5adb7"
              fontSize={11}
              fontFamily="monospace"
            >
              {item.label.slice(0, 22)}
            </text>
            <rect
              x={labelWidth}
              y={y + rowHeight * 0.18}
              width={barWidth}
              height={rowHeight * 0.64}
              rx={2}
              fill={item.color || "#ee6258"}
              opacity={0.8}
            />
            <text
              x={labelWidth + barWidth + 8}
              y={y + rowHeight / 2 + 3}
              fill="#f0f2f4"
              fontSize={11}
              fontFamily="monospace"
            >
              {item.value.toFixed(2)}
              {unit}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function HeatStrip({
  cells,
}: {
  cells: {
    pit_lap: number | null;
    mean_time: number | null;
    pair: string;
    win_rate: number | null;
  }[];
}) {
  const valid = cells.filter((c) => c.pit_lap != null && c.mean_time != null);
  if (!valid.length)
    return <div className="muted">No 1-stop data for heatmap</div>;
  const times = valid.map((c) => c.mean_time!);
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  const byLap = new Map<number, typeof valid>();
  for (const c of valid) {
    const lap = c.pit_lap!;
    if (!byLap.has(lap)) byLap.set(lap, []);
    byLap.get(lap)!.push(c);
  }
  const laps = [...byLap.keys()].sort((a, b) => a - b);
  return (
    <div style={{ overflowX: "auto" }}>
      <div style={{ display: "flex", gap: 2, minWidth: laps.length * 28 }}>
        {laps.map((lap) => {
          const group = byLap.get(lap)!;
          const best = group.reduce((a, b) =>
            (a.mean_time ?? 1e9) < (b.mean_time ?? 1e9) ? a : b,
          );
          const t = best.mean_time!;
          const norm = (t - minT) / Math.max(maxT - minT, 1e-9);
          // green (fast) → red (slow)
          const r = Math.round(50 + norm * 180);
          const g = Math.round(180 - norm * 140);
          const b = 40;
          return (
            <div
              key={lap}
              title={`L${lap} ${best.pair}\n${t.toFixed(1)}s · WR ${((best.win_rate ?? 0) * 100).toFixed(0)}%`}
              style={{
                width: 26,
                height: 64,
                background: `rgb(${r},${g},${b})`,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "flex-end",
                fontSize: 9,
                fontFamily: "JetBrains Mono,monospace",
                color: "#fff",
                paddingBottom: 4,
              }}
            >
              {lap}
            </div>
          );
        })}
      </div>
      <div className="muted" style={{ marginTop: 6 }}>
        Pit lap → color = relative race time (green faster · red slower). Hover
        for pair details.
      </div>
    </div>
  );
}

export function EvTimeline({
  points,
  color,
  label,
}: {
  points: {
    lap: number;
    mean_ev: number;
    p10_ev: number;
    p90_ev: number;
    recommend: boolean;
  }[];
  color: string;
  label: string;
}) {
  if (!points.length) return <div className="muted">No {label} scan data</div>;
  const series = [
    {
      name: label,
      color,
      points: points.map((p) => ({ x: p.lap, y: p.mean_ev })),
    },
  ];
  // band as extra series roughly
  return (
    <div>
      <LineChart
        series={series}
        xLabel="Candidate pit lap"
        yLabel="EV (s)"
        height={180}
      />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
        {points
          .filter((p) => p.recommend)
          .map((p) => (
            <span
              key={p.lap}
              className="chip"
              style={{ borderLeft: `3px solid ${color}` }}
            >
              L{p.lap} · {p.mean_ev >= 0 ? "+" : ""}
              {p.mean_ev.toFixed(2)}s
            </span>
          ))}
      </div>
    </div>
  );
}

export { TYRE, TRACE_COLORS };
