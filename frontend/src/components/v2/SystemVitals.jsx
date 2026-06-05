/**
 * SystemVitals — one card, two answers:
 *   1. Am I making money? (big profit number + cash secured)
 *   2. Is the system working? (per-broker heartbeat, last trade, risk override)
 *
 * Replaces the decorative TradingPeersCluster. All-signal, no-noise.
 */
import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Activity, TrendingUp, TrendingDown, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Single source of truth — 3 brokers × $100K paper inception.
const STARTING_BALANCE = 300_000;

const fmtAbsMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(Math.abs(Number.isFinite(v) ? v : 0));

const fmtTimeAgo = (iso) => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};

const Dot = ({ ok, dim = false }) => (
  <span
    className="inline-block rounded-full"
    style={{
      width: 7, height: 7,
      background: ok ? "var(--up)" : "var(--down)",
      boxShadow: ok && !dim ? "0 0 8px rgba(34,197,94,0.65)" : "none",
      opacity: dim ? 0.55 : 1,
    }}
  />
);

export const SystemVitals = ({ onOpenRisk }) => {
  const [brokers, setBrokers] = useState(null);
  const [recent, setRecent] = useState(null);
  const [risk, setRisk] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [b, t, r] = await Promise.all([
          axios.get(`${API}/broker/all`),
          axios.get(`${API}/dashboard/recent-trades?limit=1`),
          axios.get(`${API}/risk/status`),
        ]);
        if (!alive) return;
        setBrokers(b.data);
        setRecent(t.data?.trades?.[0] || null);
        setRisk(r.data);
      } catch {}
    };
    load();
    const id = setInterval(load, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const totalWealth = brokers?.combined?.total_wealth ?? 0;
  const lockedCash = brokers?.combined?.locked_profits ?? 0;
  const profit = totalWealth - STARTING_BALANCE;
  const isUp = profit >= 0;
  const loaded = !!brokers;

  // Per-broker freshness — "as_of" within last 5 minutes = live, else stale.
  const brokerStates = useMemo(() => {
    if (!brokers) return [];
    return ["oanda", "alpaca", "sim"].map((k) => {
      const b = brokers[k] || {};
      const ts = b.as_of ? new Date(b.as_of).getTime() : 0;
      const fresh = Date.now() - ts < 5 * 60 * 1000;
      return {
        key: k,
        label: k === "oanda" ? "OANDA" : k === "alpaca" ? "Alpaca" : "Sim",
        live: fresh && !!ts,
      };
    });
  }, [brokers]);

  const liveCount = brokerStates.filter((b) => b.live).length;
  const allLive = liveCount === brokerStates.length && liveCount > 0;

  const riskActive = !!risk?.active;
  const riskManual = risk?.manual_override;

  return (
    <motion.section
      className="card p-4"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
      data-testid="system-vitals"
    >
      {/* Top row: profit hero + systems heartbeat */}
      <div className="grid grid-cols-5 gap-3 items-stretch mb-3">
        <div className="col-span-3 flex flex-col justify-center">
          <div className="text-[9px] tracking-[0.14em] uppercase text-white/45 mb-1 flex items-center gap-1">
            <Sparkles size={9} style={{ color: "var(--accent-1)" }} />
            Profit
          </div>
          <div className="flex items-baseline gap-1.5">
            <span
              className="text-[28px] font-bold tabular leading-none tracking-tight"
              style={{
                color: isUp ? "var(--up)" : "var(--down)",
                textShadow: `0 0 18px ${isUp ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)"}`,
              }}
              data-testid="vitals-profit"
            >
              {!loaded ? "—" : `${isUp ? "+" : "−"}${fmtAbsMoney(profit)}`}
            </span>
            {loaded && (isUp
              ? <TrendingUp size={14} style={{ color: "var(--up)" }} />
              : <TrendingDown size={14} style={{ color: "var(--down)" }} />)}
          </div>
          {lockedCash > 0 && (
            <div className="text-[11px] mt-1.5 tabular" style={{ color: "var(--accent-1)" }}
                 data-testid="vitals-cash">
              {fmtAbsMoney(lockedCash)} cash secured
            </div>
          )}
        </div>

        <div className="col-span-2 flex flex-col items-end justify-center">
          <div className="text-[9px] tracking-[0.14em] uppercase text-white/45 mb-1 flex items-center gap-1">
            <Activity size={9} style={{ color: allLive ? "var(--up)" : "var(--warn)" }} />
            Systems
          </div>
          <div className="flex items-center gap-1.5 mb-1"
               data-testid="vitals-broker-dots">
            {brokerStates.map((b) => (
              <Dot key={b.key} ok={b.live} dim={!b.live} />
            ))}
          </div>
          <div className="text-[10px] tabular"
               style={{ color: allLive ? "var(--up)" : liveCount > 0 ? "var(--warn)" : "var(--down)" }}>
            {liveCount}/{brokerStates.length} live
          </div>
        </div>
      </div>

      {/* Bottom rows: status lines — last trade, risk override */}
      <div className="space-y-1.5 pt-3 border-t border-white/[0.06]">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-white/45">Last trade</span>
          {recent ? (
            <span className="tabular text-white/85">
              <span className="text-white/40">{fmtTimeAgo(recent.ts)} ·</span>{" "}
              <strong className="text-white">{recent.symbol}</strong>{" "}
              <span style={{ color: recent.side?.toLowerCase() === "buy" ? "var(--up)" : "var(--down)" }}>
                {recent.side?.toUpperCase()}
              </span>{" "}
              <span style={{
                color: (recent.pl_pct ?? 0) >= 0 ? "var(--up)" : "var(--down)",
              }}>
                {(recent.pl_pct ?? 0) >= 0 ? "+" : ""}{Number(recent.pl_pct ?? 0).toFixed(2)}%
              </span>
            </span>
          ) : (
            <span className="text-white/35">none yet</span>
          )}
        </div>

        <button
          onClick={onOpenRisk}
          className="w-full flex items-center justify-between text-[11px] -mx-1 px-1 py-0.5 rounded hover:bg-white/[0.04] transition"
          data-testid="vitals-risk-row"
        >
          <span className="text-white/45">Risk gate</span>
          <span className="flex items-center gap-1.5">
            {riskActive
              ? <ShieldAlert size={11} style={{ color: "var(--down)" }} />
              : <ShieldCheck size={11} style={{ color: "var(--up)" }} />}
            <span className="font-medium" style={{ color: riskActive ? "var(--down)" : "var(--up)" }}>
              {riskActive ? "PAUSED" : "OPEN"}
            </span>
            {riskManual && (
              <span className="text-[9px] uppercase tracking-[0.10em] text-white/40 ml-1">
                · {riskManual === "off" ? "forced off" : "forced on"}
              </span>
            )}
          </span>
        </button>
      </div>
    </motion.section>
  );
};

export default SystemVitals;
