import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip } from "recharts";
import { TrendingUp, Target } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtPct = (v) => (Number.isFinite(v) ? `${v.toFixed(1)}%` : "—");
const fmtShortDate = (iso) => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
};

const TooltipBox = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div
      className="text-[11px] px-2.5 py-1.5 rounded-lg"
      style={{ background: "rgba(20,20,28,0.94)", border: "1px solid var(--border-hi)" }}
    >
      <div className="text-white/85 font-medium">{fmtShortDate(p.date)}</div>
      <div className="text-white/55 tabular">
        {p.wins}/{p.total} · <span style={{ color: (p.win_rate ?? 0) >= 40 ? "var(--up)" : "var(--warn)" }}>{p.win_rate != null ? fmtPct(p.win_rate) : "no trades"}</span>
      </div>
    </div>
  );
};

/**
 * Win-Rate Trend — daily win-rate sparkline over the last 14 days plus
 * progress toward the 40% × 20-trade scale threshold. Sits above BotBrainPanel
 * in the Agents tab so you can see if filter quality is trending up well before
 * the scale decision.
 */
export const WinRateTrendCard = ({ delay = 0.1 }) => {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/dashboard/win-rate-trend`, { timeout: 10000 });
        if (alive) setData(r.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 60000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const series = data?.series ?? [];
  const cumPoints = useMemo(
    () => series.filter((s) => s.cum_total > 0).map((s) => ({
      date: s.date,
      cum_win_rate: s.cum_win_rate ?? 0,
      win_rate: s.win_rate,
      wins: s.cum_wins,
      total: s.cum_total,
    })),
    [series]
  );

  const totals = data?.totals ?? { wins: 0, total: 0, win_rate: null };
  const thresholdPct = data?.threshold_pct ?? 40.0;
  const thresholdTrades = data?.threshold_trades ?? 20;

  const wr = totals.win_rate;
  const wrAboveThreshold = wr != null && wr >= thresholdPct;
  const tradesPct = Math.min(100, (totals.total / thresholdTrades) * 100);
  const wrPct = wr == null ? 0 : Math.min(100, (wr / thresholdPct) * 100);

  // 7-day trajectory: compare last 7 days WR to prior 7 days WR
  const trajectory = useMemo(() => {
    if (series.length < 14) return null;
    const recent = series.slice(-7);
    const prior = series.slice(0, 7);
    const sumWins = (xs) => xs.reduce((a, b) => a + (b.wins || 0), 0);
    const sumTotal = (xs) => xs.reduce((a, b) => a + (b.total || 0), 0);
    const rw = sumWins(recent), rt = sumTotal(recent);
    const pw = sumWins(prior), pt = sumTotal(prior);
    if (rt === 0) return null;
    const r = rw / rt * 100;
    const p = pt > 0 ? pw / pt * 100 : null;
    return { recent_wr: r, prior_wr: p, delta: p == null ? null : r - p };
  }, [series]);

  return (
    <motion.section
      className="card p-5"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="win-rate-trend-card"
    >
      <header className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(34,197,94,0.16)", color: "var(--up)" }}
          >
            <Target size={15} />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold tracking-tight leading-none">
              Win-Rate Trend
            </h3>
            <div className="text-[11px] text-white/40 mt-0.5">
              Last 14 days · scale threshold {thresholdPct}% × {thresholdTrades} trades
            </div>
          </div>
        </div>
        {trajectory?.delta != null && (
          <div
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-full"
            style={{
              background: trajectory.delta >= 0 ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
              color: trajectory.delta >= 0 ? "var(--up)" : "var(--down)",
              border: `1px solid ${trajectory.delta >= 0 ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
            }}
            data-testid="win-rate-trajectory"
          >
            <TrendingUp size={11} style={trajectory.delta < 0 ? { transform: "scaleY(-1)" } : undefined} />
            <span className="tabular font-semibold">
              {trajectory.delta >= 0 ? "+" : ""}{trajectory.delta.toFixed(1)}pp
            </span>
            <span className="text-white/55 hidden sm:inline">vs prior 7d</span>
          </div>
        )}
      </header>

      {/* Stat row */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div>
          <div className="text-[10px] tracking-[0.10em] uppercase text-white/40 mb-1">Cumulative WR</div>
          <div
            className="text-[22px] font-semibold tabular leading-none"
            style={{ color: wrAboveThreshold ? "var(--up)" : wr == null ? "var(--text-3)" : "var(--warn)" }}
            data-testid="win-rate-cumulative"
          >
            {fmtPct(wr)}
          </div>
        </div>
        <div>
          <div className="text-[10px] tracking-[0.10em] uppercase text-white/40 mb-1">Closed Trades</div>
          <div className="text-[22px] font-semibold tabular leading-none text-white/90" data-testid="win-rate-total">
            {totals.total}
            <span className="text-[12px] text-white/40 ml-1">/ {thresholdTrades}</span>
          </div>
        </div>
        <div>
          <div className="text-[10px] tracking-[0.10em] uppercase text-white/40 mb-1">Wins</div>
          <div className="text-[22px] font-semibold tabular leading-none" style={{ color: "var(--up)" }}>
            {totals.wins}
          </div>
        </div>
      </div>

      {/* Progress bars */}
      <div className="space-y-2 mb-4">
        <div>
          <div className="flex items-center justify-between text-[10px] mb-1">
            <span className="text-white/45">Sample size progress</span>
            <span className="text-white/65 tabular">{totals.total} / {thresholdTrades}</span>
          </div>
          <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{
                width: `${tradesPct}%`,
                background: "linear-gradient(90deg, var(--accent-1), var(--accent-2))",
                transition: "width 600ms cubic-bezier(0.22, 1, 0.36, 1)",
              }}
            />
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between text-[10px] mb-1">
            <span className="text-white/45">Win-rate vs {thresholdPct}% threshold</span>
            <span className="text-white/65 tabular">{fmtPct(wr)}</span>
          </div>
          <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{
                width: `${wrPct}%`,
                background: wrAboveThreshold
                  ? "linear-gradient(90deg, var(--up), #16a34a)"
                  : "linear-gradient(90deg, var(--warn), var(--down))",
                transition: "width 600ms cubic-bezier(0.22, 1, 0.36, 1)",
              }}
            />
          </div>
        </div>
      </div>

      {/* Sparkline */}
      <div className="h-28 -mx-1">
        {cumPoints.length === 0 ? (
          <div className="h-full flex items-center justify-center text-[12px] text-white/35">
            No closed trades yet — chart will populate as workers tick.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={cumPoints} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <defs>
                <linearGradient id="wr-trend" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--up)" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="var(--up)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Tooltip content={<TooltipBox />} cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: "3 3" }} />
              <ReferenceLine
                y={thresholdPct}
                stroke="var(--warn)"
                strokeDasharray="3 4"
                strokeOpacity={0.55}
                label={{ value: `${thresholdPct}%`, fill: "var(--warn)", fontSize: 10, position: "right" }}
              />
              <Area
                type="monotone"
                dataKey="cum_win_rate"
                stroke="var(--up)"
                strokeWidth={2}
                fill="url(#wr-trend)"
                isAnimationActive={true}
                dot={{ r: 2.5, fill: "var(--up)", strokeWidth: 0 }}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {totals.total > 0 && totals.total < thresholdTrades && (
        <div className="mt-3 text-[11px] text-white/45 text-center">
          {thresholdTrades - totals.total} more closed {thresholdTrades - totals.total === 1 ? "trade" : "trades"} to reach the scale-decision threshold.
        </div>
      )}
      {totals.total >= thresholdTrades && wrAboveThreshold && (
        <div
          className="mt-3 text-[11px] text-center px-3 py-2 rounded-lg font-medium"
          style={{ background: "rgba(34,197,94,0.14)", border: "1px solid rgba(34,197,94,0.32)", color: "var(--up)" }}
          data-testid="scale-ready-banner"
        >
          ✓ Scale threshold reached — safe to bump INSTRUMENTS to 10 on Railway.
        </div>
      )}
    </motion.section>
  );
};

export default WinRateTrendCard;
