/**
 * AutoInsights — surfaces the two things you said to "watch":
 *   1. Scaling gate clearance (≥20 trades, ≥40% WR) — auto-pings when ready
 *   2. Top firing shadow instruments (last 24h) — sorted by agreement rate
 *
 * Both auto-refresh every 60s; no manual polling required.
 */
import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Layers, Brain, Unlock, ArrowRight } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ProgressBar = ({ value, target, color = "var(--accent-1)" }) => {
  const pct = Math.min(100, Math.max(0, (value / Math.max(1, target)) * 100));
  return (
    <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      />
    </div>
  );
};

export const AutoInsights = ({ delay = 0.25, onJumpToAgents }) => {
  const [scaling, setScaling] = useState(null);
  const [agreement, setAgreement] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [s, a] = await Promise.all([
          axios.get(`${API}/scaling/readiness`),
          axios.get(`${API}/shadow/agreement?hours=24`),
        ]);
        if (!alive) return;
        setScaling(s.data);
        setAgreement(a.data?.by_symbol || {});
      } catch {}
    };
    load();
    const id = setInterval(load, 60000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const topFiring = useMemo(() => {
    if (!agreement) return [];
    return Object.entries(agreement)
      .map(([sym, d]) => ({
        symbol: sym,
        rate: d.agreement_rate_pct || 0,
        actionable: (d.LONG || 0) + (d.SHORT || 0),
        total: d.total || 0,
      }))
      .filter((d) => d.total > 0)
      .sort((a, b) => b.rate - a.rate)
      .slice(0, 3);
  }, [agreement]);

  if (!scaling) return null;

  const tradesNeeded = Math.max(0, scaling.gate.min_trades - scaling.stats.closed_trades);
  const wrNeeded = Math.max(0, scaling.gate.min_win_rate - scaling.stats.win_rate);
  const gateClear = scaling.gate.clear;

  return (
    <motion.section
      className="card p-4"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="auto-insights"
    >
      <div className="flex items-center gap-1.5 mb-3">
        <Sparkles size={11} style={{ color: "var(--accent-2)" }} />
        <span className="text-[9px] tracking-[0.16em] uppercase text-white/50 font-medium">
          Auto-Insights
        </span>
        <span className="text-[9px] text-white/30 ml-auto">refreshes 60s</span>
      </div>

      {/* Scaling Gate progress */}
      <button
        onClick={onJumpToAgents}
        className="w-full text-left p-3 rounded-lg mb-2 hover:bg-white/[0.03] transition"
        style={{
          background: gateClear ? "rgba(34,197,94,0.06)" : "rgba(255,255,255,0.02)",
          border: `1px solid ${gateClear ? "rgba(34,197,94,0.30)" : "rgba(255,255,255,0.06)"}`,
        }}
        data-testid="insight-scaling"
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-[11px]">
            {gateClear
              ? <Unlock size={12} style={{ color: "var(--up)" }} />
              : <Layers size={12} style={{ color: "var(--accent-1)" }} />}
            <span className="font-semibold text-white/85">
              {gateClear ? "Scale 5→10 ready" : "Scale 5→10 progress"}
            </span>
          </div>
          <span
            className="text-[10px] font-bold tabular"
            style={{ color: gateClear ? "var(--up)" : "var(--accent-1)" }}
          >
            {gateClear ? "TAP TO SCALE" : `${tradesNeeded}t · ${wrNeeded.toFixed(0)}% WR to go`}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-[9px] uppercase tracking-[0.10em] text-white/45">Trades</span>
              <span className="text-[10px] tabular text-white/65">
                <strong style={{ color: scaling.gate.trades_ok ? "var(--up)" : "white" }}>
                  {scaling.stats.closed_trades}
                </strong>
                <span className="text-white/35"> / {scaling.gate.min_trades}</span>
              </span>
            </div>
            <ProgressBar
              value={scaling.stats.closed_trades}
              target={scaling.gate.min_trades}
              color={scaling.gate.trades_ok ? "var(--up)" : "var(--accent-1)"}
            />
          </div>
          <div>
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-[9px] uppercase tracking-[0.10em] text-white/45">Win rate</span>
              <span className="text-[10px] tabular text-white/65">
                <strong style={{ color: scaling.gate.wr_ok ? "var(--up)" : "white" }}>
                  {scaling.stats.win_rate.toFixed(1)}%
                </strong>
                <span className="text-white/35"> / {scaling.gate.min_win_rate}%</span>
              </span>
            </div>
            <ProgressBar
              value={scaling.stats.win_rate}
              target={scaling.gate.min_win_rate}
              color={scaling.gate.wr_ok ? "var(--up)" : "var(--accent-1)"}
            />
          </div>
        </div>
      </button>

      {/* Top firing shadow instruments */}
      <button
        onClick={onJumpToAgents}
        className="w-full text-left p-3 rounded-lg hover:bg-white/[0.03] transition"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)" }}
        data-testid="insight-shadow"
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-[11px]">
            <Brain size={12} style={{ color: "var(--accent-2)" }} />
            <span className="font-semibold text-white/85">Top firing · last 24h</span>
          </div>
          <ArrowRight size={11} className="text-white/30" />
        </div>
        {topFiring.length === 0 ? (
          <div className="text-[10px] text-white/45">
            Shadow loop is gathering data… first signals usually appear within a few ticks.
          </div>
        ) : (
          <AnimatePresence>
            <div className="space-y-1.5">
              {topFiring.map((row) => (
                <motion.div
                  key={row.symbol}
                  className="flex items-center justify-between text-[11px]"
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.4 }}
                >
                  <span className="font-medium text-white/90 tabular">{row.symbol}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-white/45 tabular">
                      {row.actionable}/{row.total}
                    </span>
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-bold tabular"
                      style={{
                        background: row.rate >= 30 ? "rgba(34,197,94,0.16)"
                                  : row.rate >= 10 ? "rgba(245,158,11,0.16)"
                                  : "rgba(255,255,255,0.06)",
                        color: row.rate >= 30 ? "var(--up)"
                              : row.rate >= 10 ? "var(--warn)"
                              : "rgba(255,255,255,0.55)",
                        minWidth: 44, textAlign: "center",
                      }}
                    >
                      {row.rate.toFixed(0)}%
                    </span>
                  </div>
                </motion.div>
              ))}
            </div>
          </AnimatePresence>
        )}
      </button>
    </motion.section>
  );
};

export default AutoInsights;
