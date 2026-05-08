import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import {
  ArrowDownRight,
  ArrowUpRight,
  Banknote,
  Bitcoin,
  Layers,
  Wallet,
  Zap,
} from "lucide-react";

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
export const Money = ({ value, currency = "USD", className = "" }) => {
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

const BROKER_META = {
  oanda: {
    label: "OANDA",
    sublabel: "Forex",
    Icon: Banknote,
    accent: "rgba(123,97,255,0.6)", // violet
    accentSoft: "rgba(123,97,255,0.10)",
    cells: ["Live NAV", "Locked Profits", "Open Positions", "Margin Used"],
  },
  alpaca: {
    label: "Alpaca",
    sublabel: "Stocks · Crypto",
    Icon: Bitcoin,
    accent: "rgba(0,229,255,0.6)", // cyan
    accentSoft: "rgba(0,229,255,0.10)",
    cells: ["Live NAV", "Locked Profits", "Open Positions", "Buying Power"],
  },
};

/**
 * Single-broker card. Used twice inside MultiBrokerHero.
 * Pure presentational — receives data + broker key.
 */
const BrokerCard = ({ broker, data, error, delay = 0 }) => {
  const meta = BROKER_META[broker];
  const { Icon } = meta;

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

  // Per-broker fourth cell
  const fourthCell =
    broker === "oanda"
      ? { label: "Margin Used", value: fmt(data?.margin_used ?? 0, currency), accent: "muted" }
      : { label: "Buying Power", value: fmt(data?.margin_available ?? 0, currency), accent: "muted" };

  return (
    <motion.section
      className="jv-hero relative px-5 md:px-7 py-6 md:py-7 overflow-hidden"
      data-testid={`broker-hero-${broker}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1], delay: delay / 1000 }}
      style={{
        // soft accent glow on top edge per broker
        background: `radial-gradient(120% 50% at 50% -10%, ${meta.accentSoft} 0%, transparent 55%), linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%)`,
      }}
    >
      {/* Top row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon size={14} className="text-white/55" />
          <span className="font-mono text-[10px] tracking-[0.28em] uppercase text-white/55">
            {meta.label}
          </span>
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/30">
            · {meta.sublabel}
          </span>
          {isMock && (
            <span className="font-mono text-[9px] tracking-[0.22em] uppercase text-amber-300/80 ml-1">
              · mock
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5">
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping"
              style={{ background: meta.accent }}
            />
            <span
              className="relative inline-flex rounded-full h-1.5 w-1.5"
              style={{ background: meta.accent }}
            />
          </span>
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/40">
            paper
          </span>
        </div>
      </div>

      {error && (
        <div className="text-xs text-[var(--jv-down)] font-mono mb-3">! {error}</div>
      )}

      {/* Wealth number */}
      <div className="flex items-baseline gap-3 flex-wrap">
        <Money
          value={totalWealth}
          currency={currency}
          className="font-heading text-4xl md:text-5xl lg:text-6xl font-light text-white tracking-[-0.03em]"
        />
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/30">
          wealth
        </span>
      </div>

      {/* Pills */}
      <div className="mt-4 flex flex-wrap items-stretch gap-2">
        {showDod ? (
          <div
            className={`flex items-center gap-2 rounded-full px-3 py-1.5 border ${
              dodIsUp
                ? "border-[rgba(0,255,133,0.35)] bg-[rgba(0,255,133,0.08)]"
                : "border-[rgba(255,59,110,0.35)] bg-[rgba(255,59,110,0.08)]"
            }`}
          >
            {dodIsUp ? (
              <ArrowUpRight size={13} className="text-[var(--jv-up)]" />
            ) : (
              <ArrowDownRight size={13} className="text-[var(--jv-down)]" />
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
            <Zap size={11} className="text-white/45" />
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
      <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-px bg-white/5 rounded-2xl overflow-hidden border border-white/5">
        <Cell label="Live NAV" value={fmt(nav, currency)} />
        <Cell
          label="Locked Profits"
          value={fmt(locked, currency)}
          accent={locked > 0 ? "up" : "muted"}
        />
        <Cell label="Open Positions" value={String(positions)} />
        <Cell label={fourthCell.label} value={fourthCell.value} accent={fourthCell.accent} />
      </div>

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between font-mono text-[10px] tracking-[0.22em] uppercase text-white/30">
        <span>
          {currency}
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
    <div className="bg-[#0a0a0a]/60 backdrop-blur-sm px-4 py-3 flex flex-col gap-1">
      <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/35">
        {label}
      </span>
      <span className={`font-mono text-sm md:text-base tabular ${valueClass}`}>
        {value}
      </span>
    </div>
  );
};

/**
 * MultiBrokerHero — combined header + two stacked broker cards (OANDA + Alpaca).
 * Single fetch to /api/broker/all every 15s.
 */
export const MultiBrokerHero = ({ refreshKey }) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/broker/all`);
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
    load();
  }, [refreshKey]);

  const oanda = data?.oanda;
  const alpaca = data?.alpaca;
  const combinedWealth = data?.combined?.total_wealth ?? 0;
  const combinedPositions = data?.combined?.open_positions ?? 0;

  return (
    <div className="flex flex-col gap-4" data-testid="multi-broker-hero">
      {/* Combined supercard — slim hero showing total across both brokers */}
      <motion.section
        className="jv-hero relative px-6 md:px-8 py-5 md:py-6 overflow-hidden"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        data-testid="broker-hero-combined"
        style={{
          background:
            "radial-gradient(120% 60% at 50% -20%, rgba(123,97,255,0.10) 0%, rgba(0,229,255,0.06) 40%, transparent 70%), linear-gradient(180deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.01) 100%)",
        }}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Layers size={14} className="text-white/65" />
            <span className="font-mono text-[10px] tracking-[0.32em] uppercase text-white/65">
              Combined Wealth
            </span>
            <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/30">
              · OANDA + Alpaca
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/35">
              {combinedPositions} positions
            </span>
            <span className="flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
              </span>
              <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/45">
                live
              </span>
            </span>
          </div>
        </div>

        {error && (
          <div className="text-xs text-[var(--jv-down)] font-mono mb-2">! {error}</div>
        )}

        <div className="flex items-baseline gap-3 flex-wrap">
          <Wallet size={18} className="text-white/55 mr-1" />
          <Money
            value={combinedWealth}
            className="font-heading text-5xl md:text-6xl lg:text-7xl font-light text-white tracking-[-0.03em]"
          />
          <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-white/35">
            total
          </span>
        </div>
      </motion.section>

      {/* Two stacked broker cards */}
      <BrokerCard broker="oanda" data={oanda} error={null} delay={120} />
      <BrokerCard broker="alpaca" data={alpaca} error={null} delay={220} />
    </div>
  );
};

export default MultiBrokerHero;
