import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Zap } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(v) ? v : 0);

const fmtPct = (v) =>
  Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—";

const fmtSignedMoney = (v) => {
  if (!Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : "−"}${fmtMoney(Math.abs(v))}`;
};

const AnimatedMoney = ({ value, formatter = fmtSignedMoney, className = "", color }) => {
  const mv = useMotionValue(0);
  const display = useTransform(mv, (v) => formatter(v));
  useEffect(() => {
    const c = animate(mv, Number.isFinite(value) ? value : 0, {
      duration: 1.1,
      ease: [0.22, 1, 0.36, 1],
    });
    return c.stop;
  }, [value, mv]);
  return <motion.span className={`tabular ${className}`} style={color ? { color } : undefined}>{display}</motion.span>;
};

const BrokerChip = ({ label, value, pct, up, iconBg, iconChar }) => (
  <div className="flex items-center gap-2.5 min-w-0 flex-1">
    <div
      className="w-9 h-9 rounded-xl flex items-center justify-center text-[14px] font-bold flex-shrink-0"
      style={{ background: iconBg, color: "#fff" }}
    >
      {iconChar}
    </div>
    <div className="flex flex-col min-w-0">
      <span className="text-[11px] text-white/55 font-medium uppercase tracking-wide">{label}</span>
      <div className="flex items-baseline gap-1.5">
        <span
          className="text-[15px] font-semibold tabular"
          style={{ color: up ? "var(--up)" : "var(--down)" }}
        >
          {fmtSignedMoney(value)}
        </span>
        <span
          className="text-[11px] tabular"
          style={{ color: up ? "var(--up)" : "var(--down)" }}
        >
          ▲ {fmtPct(pct).replace("+", "")}
        </span>
      </div>
    </div>
  </div>
);

const buildSparkSeries = (anchor, count = 28, drift = 0.012) => {
  const series = [];
  let v = anchor * 0.985;
  for (let i = 0; i < count; i++) {
    const noise = Math.sin(i * 0.62) * 0.006 + Math.cos(i * 1.1) * 0.003;
    v *= 1 + drift / count + noise;
    series.push({ x: i, y: v });
  }
  return series;
};

/**
 * TodayProfitHero — the centerpiece green-gradient card.
 * Shows: combined day profit, sparkline, % vs yesterday, sub-broker chips.
 */
export const TodayProfitHero = () => {
  const [hero, setHero] = useState(null);
  const [allBrokers, setAllBrokers] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [h, b] = await Promise.all([
          axios.get(`${API}/dashboard/hero`),
          axios.get(`${API}/broker/all`),
        ]);
        if (!alive) return;
        setHero(h.data);
        setAllBrokers(b.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const dayPl = hero?.day_pl ?? 0;
  const dayPct = hero?.day_pl_pct ?? 0;
  const up = dayPl >= 0;
  const oandaDelta = allBrokers?.oanda?.dod_change ?? 0;
  const oandaPct = allBrokers?.oanda?.dod_pct ?? 0;
  const alpacaDelta = allBrokers?.alpaca?.dod_change ?? 0;
  const alpacaPct = allBrokers?.alpaca?.dod_pct ?? 0;

  const sparkData = buildSparkSeries(Math.abs(dayPl) || 100, 30, up ? 0.04 : -0.04);
  const accent = up ? "#22c55e" : "#ef4444";
  const accentSoft = up ? "rgba(34,197,94,0.10)" : "rgba(239,68,68,0.10)";

  return (
    <motion.section
      className="relative overflow-hidden rounded-3xl px-5 py-4"
      style={{
        background: `linear-gradient(180deg, ${accentSoft} 0%, rgba(15,16,22,0.6) 100%)`,
        border: `1px solid ${up ? "rgba(34,197,94,0.30)" : "rgba(239,68,68,0.30)"}`,
        boxShadow: `0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.06)`,
      }}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      data-testid="today-profit-hero"
    >
      {/* Top row */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] tracking-[0.14em] uppercase text-white/55 font-medium">
            Today's Profit (Combined)
          </span>
          <Zap size={11} className="text-white/40" />
        </div>
        <div
          className="flex items-center gap-1.5 px-2 py-0.5 rounded-full"
          style={{ background: "rgba(34,197,94,0.14)", border: "1px solid rgba(34,197,94,0.35)" }}
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
          </span>
          <span className="text-[10px] font-medium tracking-wide" style={{ color: "var(--up)" }}>
            LIVE
          </span>
        </div>
      </div>

      {/* Big number + sparkline */}
      <div className="flex items-end justify-between gap-3 mb-1.5">
        <AnimatedMoney
          value={dayPl}
          color={up ? "var(--up)" : "var(--down)"}
          className="text-[40px] sm:text-[48px] font-semibold tracking-tight leading-none"
        />
        <div className="w-[110px] h-12 -mb-1 flex-shrink-0" style={{ minWidth: 110, minHeight: 48 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData} margin={{ top: 6, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="hero-spark" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={accent} stopOpacity={0.45} />
                  <stop offset="100%" stopColor={accent} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="y"
                stroke={accent}
                strokeWidth={1.8}
                fill="url(#hero-spark)"
                isAnimationActive={false}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* % vs yesterday */}
      <div className="flex items-center gap-2 mb-3">
        <span
          className="text-[12px] font-medium tabular"
          style={{ color: up ? "var(--up)" : "var(--down)" }}
        >
          ▲ {fmtPct(dayPct).replace("+", "")}
        </span>
        <span className="text-[12px] text-white/45">vs yesterday</span>
      </div>

      {/* Broker mini-chips */}
      <div className="flex items-center gap-4">
        <BrokerChip
          label="OANDA"
          value={oandaDelta}
          pct={oandaPct}
          up={oandaDelta >= 0}
          iconBg="linear-gradient(135deg, #22c55e, #16a34a)"
          iconChar="O"
        />
        <BrokerChip
          label="Alpaca"
          value={alpacaDelta}
          pct={alpacaPct}
          up={alpacaDelta >= 0}
          iconBg="linear-gradient(135deg, #fbbf24, #f59e0b)"
          iconChar="A"
        />
      </div>
    </motion.section>
  );
};

export default TodayProfitHero;
