import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Wallet, Zap } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const fmt = (v, currency = "USD") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(v) ? v : 0);

const fmtPct = (v) =>
  Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—";

const fmtSignedMoney = (v, currency = "USD") => {
  if (!Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${fmt(Math.abs(v), currency)}`;
};

/** Smooth count-up number renderer */
const Money = ({ value, currency = "USD", className = "" }) => {
  const mv = useMotionValue(0);
  const display = useTransform(mv, (latest) => fmt(latest, currency));
  useEffect(() => {
    const controls = animate(mv, Number.isFinite(value) ? value : 0, {
      duration: 1.0,
      ease: [0.22, 1, 0.36, 1],
    });
    return controls.stop;
  }, [value, mv]);
  return <motion.span className={`tabular ${className}`}>{display}</motion.span>;
};

/**
 * BrokerHeroPanel — the most visually arresting widget.
 * Shows: Total Wealth (NAV + Locked), with NAV / Locked breakdown and DoD change badge.
 */
export const BrokerHeroPanel = ({ refreshKey }) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/broker/summary`);
      if (r.data?.error) {
        setError(r.data.error);
      } else {
        setError(null);
        setData(r.data);
      }
    } catch (e) {
      setError(e?.message || "fetch failed");
    }
  };

  useEffect(() => {
    load();
    intervalRef.current = setInterval(load, 15000);
    return () => clearInterval(intervalRef.current);
  }, []);

  useEffect(() => {
    load(); // refresh when parent bumps key
  }, [refreshKey]);

  const currency = data?.currency || "USD";
  const totalWealth = data?.total_wealth ?? 0;
  const nav = data?.nav ?? 0;
  const locked = data?.locked_profits ?? 0;
  const unrealized = data?.unrealized_pl ?? 0;
  const positions = data?.open_positions ?? 0;
  const dodChange = data?.dod_change;
  const dodPct = data?.dod_pct;
  const isMock = data?.source === "mock";

  const dodIsUp = (dodChange ?? 0) >= 0;
  const showDod = Number.isFinite(dodChange);

  return (
    <motion.section
      className="jv-hero relative px-6 md:px-8 py-7 md:py-8 overflow-hidden"
      data-testid="broker-hero"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
    >
      {/* Top row */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Wallet size={14} className="text-white/45" />
          <span className="font-mono text-[10px] tracking-[0.28em] uppercase text-white/45">
            Broker Account
          </span>
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/25">
            · OANDA {isMock ? "MOCK" : "PRACTICE"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
          </span>
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/45">
            live
          </span>
        </div>
      </div>

      {error && (
        <div className="text-xs text-[var(--jv-down)] font-mono mb-3">
          ! {error}
        </div>
      )}

      {/* Hero number */}
      <div className="flex items-baseline gap-3 flex-wrap">
        <Money
          value={totalWealth}
          currency={currency}
          className="font-heading text-5xl md:text-6xl lg:text-7xl font-light text-white tracking-[-0.03em]"
        />
        <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-white/35">
          total wealth
        </span>
      </div>

      {/* DoD badge + breakdown */}
      <div className="mt-5 flex flex-wrap items-stretch gap-3">
        {showDod ? (
          <div
            className={`flex items-center gap-2 rounded-full px-3 py-1.5 border ${
              dodIsUp
                ? "border-[rgba(0,255,133,0.35)] bg-[rgba(0,255,133,0.08)]"
                : "border-[rgba(255,59,110,0.35)] bg-[rgba(255,59,110,0.08)]"
            }`}
            data-testid="broker-dod"
          >
            {dodIsUp ? (
              <ArrowUpRight size={14} className="text-[var(--jv-up)]" />
            ) : (
              <ArrowDownRight size={14} className="text-[var(--jv-down)]" />
            )}
            <span
              className={`font-mono text-xs tabular ${dodIsUp ? "val-up" : "val-down"}`}
            >
              {fmtSignedMoney(dodChange, currency)}
            </span>
            <span className="font-mono text-[10px] text-white/50">·</span>
            <span
              className={`font-mono text-xs tabular ${dodIsUp ? "val-up" : "val-down"}`}
            >
              {fmtPct(dodPct)}
            </span>
            <span className="font-mono text-[9px] tracking-[0.24em] uppercase text-white/40 ml-1">
              today
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-full px-3 py-1.5 border border-white/10 bg-white/[0.02]">
            <span className="font-mono text-[10px] tracking-[0.24em] uppercase text-white/35">
              banking first NAV snapshot…
            </span>
          </div>
        )}

        {Number.isFinite(unrealized) && (
          <div className="flex items-center gap-2 rounded-full px-3 py-1.5 border border-white/10 bg-white/[0.02]">
            <Zap size={12} className="text-white/45" />
            <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/40">
              unrealized
            </span>
            <span
              className={`font-mono text-xs tabular ${
                unrealized >= 0 ? "val-up" : "val-down"
              }`}
            >
              {fmtSignedMoney(unrealized, currency)}
            </span>
          </div>
        )}
      </div>

      {/* Breakdown grid */}
      <div className="mt-7 grid grid-cols-2 md:grid-cols-4 gap-px bg-white/5 rounded-2xl overflow-hidden border border-white/5">
        <Cell label="Live NAV" value={fmt(nav, currency)} />
        <Cell label="Locked Profits" value={fmt(locked, currency)} accent={locked > 0 ? "up" : "muted"} />
        <Cell label="Open Positions" value={String(positions)} />
        <Cell
          label="Margin Used"
          value={fmt(data?.margin_used ?? 0, currency)}
          accent="muted"
        />
      </div>

      {/* Footer micro-line */}
      <div className="mt-4 flex items-center justify-between font-mono text-[10px] tracking-[0.22em] uppercase text-white/30">
        <span>
          paper · {currency}
          {isMock && " · keys not configured"}
        </span>
        <span>
          {data?.as_of
            ? `as of ${new Date(data.as_of).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}`
            : "—"}
        </span>
      </div>
    </motion.section>
  );
};

const Cell = ({ label, value, accent = "default" }) => {
  const valueClass =
    accent === "up"
      ? "val-up"
      : accent === "down"
      ? "val-down"
      : accent === "muted"
      ? "text-white/75"
      : "text-white";
  return (
    <div className="bg-[#0a0a0a]/60 backdrop-blur-sm px-4 py-3.5 flex flex-col gap-1">
      <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/35">
        {label}
      </span>
      <span className={`font-mono text-base md:text-lg tabular ${valueClass}`}>
        {value}
      </span>
    </div>
  );
};

export default BrokerHeroPanel;
