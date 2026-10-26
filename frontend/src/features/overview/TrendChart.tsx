import { useState } from "react";

import { formatMoney } from "../../components/format";

export interface TrendPoint {
  month: string; // YYYY-MM
  currency: string;
  identified: string;
  recovered: string;
}

// Emphasis form (dataviz): cash recovered is the story (brand orange); leakage identified is context
// (recessive gray). Identity never relies on color alone: legend, tooltip and table view.
const CONTEXT = "#c7c7c7";
const EMPHASIS = "var(--brand)";
const W = 720;
const H = 220;
const PAD = { top: 12, right: 8, bottom: 26, left: 44 };
const BAR = 12;
const GAP = 2;

const monthLabel = (m: string) =>
  new Date(Number(m.slice(0, 4)), Number(m.slice(5, 7)) - 1, 1).toLocaleString(undefined, { month: "short" });

function niceMax(max: number): number {
  if (max <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(max));
  const step = [1, 2, 2.5, 5, 10].map((s) => s * exp).find((s) => s * 4 >= max) ?? 10 * exp;
  return step * 4;
}

const compact = (v: number) => (v >= 1000 ? `${+(v / 1000).toFixed(1)}K` : `${v}`);

/** Monthly columns: identified vs recovered, one currency, one axis. Geometry only uses numbers. */
export function TrendChart({ points, currency }: { points: TrendPoint[]; currency: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  // Numbers are used for bar geometry only; every displayed value is formatted from the decimal string.
  const max = niceMax(Math.max(...points.flatMap((p) => [Number(p.identified), Number(p.recovered)]), 0));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const slot = innerW / points.length;
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);

  const bar = (x: number, value: string, fill: string, key: string) => {
    const v = Number(value);
    if (v <= 0) return null;
    const top = y(v);
    const h = PAD.top + innerH - top;
    const r = Math.min(4, h);
    // 4px rounded data-end, square at the baseline.
    const d = `M${x},${PAD.top + innerH} V${top + r} Q${x},${top} ${x + r},${top} H${x + BAR - r} Q${x + BAR},${top} ${x + BAR},${top + r} V${PAD.top + innerH} Z`;
    return <path key={key} d={d} fill={fill} />;
  };

  const hovered = hover !== null ? points[hover] : null;

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 8 }}>
        <div className="legend" aria-label="Legend">
          <span>
            <i style={{ background: CONTEXT }} /> Leakage identified (by month it happened)
          </span>
          <span>
            <i style={{ background: EMPHASIS }} /> Cash recovered (by payment month)
          </span>
        </div>
        <button className="btn small" onClick={() => setTable(!table)} aria-pressed={table}>
          {table ? "Show chart" : "Show table"}
        </button>
      </div>

      {table ? (
        <table className="data">
          <thead>
            <tr>
              <th>Month</th>
              <th className="num">Identified</th>
              <th className="num">Recovered</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.month}>
                <td>{p.month}</td>
                <td className="num">{formatMoney(p.identified, currency)}</td>
                <td className="num">{formatMoney(p.recovered, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="chart-wrap">
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Monthly leakage identified and cash recovered, ${currency}`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth={1} />
                <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" className="axis">
                  {compact(t)}
                </text>
              </g>
            ))}
            {points.map((p, i) => {
              const x0 = PAD.left + i * slot + (slot - (2 * BAR + GAP)) / 2;
              return (
                <g key={p.month}>
                  {hover === i && <rect x={PAD.left + i * slot} y={PAD.top} width={slot} height={innerH} fill="var(--surface-2)" />}
                  {bar(x0, p.identified, CONTEXT, "i")}
                  {bar(x0 + BAR + GAP, p.recovered, EMPHASIS, "r")}
                  <text x={PAD.left + i * slot + slot / 2} y={H - 8} textAnchor="middle" className="axis">
                    {monthLabel(p.month)}
                  </text>
                  {/* Hit target: the whole month slot, bigger than the marks. */}
                  <rect
                    x={PAD.left + i * slot}
                    y={PAD.top}
                    width={slot}
                    height={innerH}
                    fill="transparent"
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(null)}
                  />
                </g>
              );
            })}
          </svg>
          {hovered && hover !== null && (
            <div
              className="chart-tooltip"
              style={{ left: `${((PAD.left + hover * slot + slot / 2) / W) * 100}%` }}
              role="status"
            >
              <strong>{hovered.month}</strong>
              <div>
                <i style={{ background: CONTEXT }} /> Identified {formatMoney(hovered.identified, currency)}
              </div>
              <div>
                <i style={{ background: EMPHASIS }} /> Recovered {formatMoney(hovered.recovered, currency)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
