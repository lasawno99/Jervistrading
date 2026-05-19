import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BROKER_META = {
  oanda: {
    label: "OANDA",
    tag: "FOREX",
    iconBg: "linear-gradient(135deg, #22c55e, #16a34a)",
    iconChar: "O",
    accent: "#22c55e",
  },
  alpaca: {
    label: "Alpaca",
    tag: "STOCKS",
    iconBg: "linear-gradient(135deg, #fbbf24, #f59e0b)",
    iconChar: "A",
    accent: "#fbbf24",
  },
  sim: {
    label: "JARVIS Sim",
    tag: "PAPER",
    iconBg: "linear-gradient(135deg, #9b7bff, #6c8dff)",
    iconChar: "J",
    accent: "#9b7bff",
  },
};

const fmtMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(v) ? v : 0);

const fmtSignedMoney = (v) => {
  if (!Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : "−"}${fmtMoney(Math.abs(v))}`;
};

const sparkSeries = (anchor) => {
  const out = [];
  let v = anchor * 0.98;
  for (let i = 0; i < 22; i++) {
    v *= 1 + Math.sin(i * 0.5) * 0.004 + 0.0015;
    out.push({ x: i, y: v });
  }
  return out;
};

const BrokerCard = ({ broker, data, idx }) => {
  const meta = BROKER_META[broker];
  const equity = data?.nav ?? 0;
  const pl = data?.dod_change ?? 0;
  const up = pl >= 0;
  const connected = data && data.source !== "mock";

  return (
    <motion.div
      className="flex-shrink-0 w-[84%] sm:w-[260px] rounded-2xl p-3.5 snap-start"
      style={{
        background: "rgba(255,255,255,0.025)",
        border: "1px solid rgba(255,255,255,0.07)",
        backdropFilter: "blur(20px)",
      }}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.05 * idx, ease: [0.22, 1, 0.36, 1] }}
      data-testid={`broker-card-${broker}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[13px] font-bold flex-shrink-0"
            style={{ background: meta.iconBg, color: "#fff" }}
          >
            {meta.iconChar}
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold leading-tight">{meta.label}</div>
            <div className="text-[10px] mt-0.5 flex items-center gap-1">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{ background: connected ? "var(--up)" : "var(--text-3)" }}
              />
              <span style={{ color: connected ? "var(--up)" : "var(--text-3)" }}>
                {connected ? "Connected" : "Mock"}
              </span>
            </div>
          </div>
        </div>
        <span
          className="text-[9px] font-semibold tracking-[0.10em] px-1.5 py-0.5 rounded"
          style={{ background: "rgba(108,141,255,0.18)", color: "var(--accent-1)" }}
        >
          {meta.tag}
        </span>
      </div>

      {/* EQUITY + P/L row */}
      <div className="grid grid-cols-2 gap-3 mb-1">
        <div>
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/40 mb-0.5">Equity</div>
          <div className="text-[14px] font-semibold tabular leading-tight">{fmtMoney(equity)}</div>
        </div>
        <div>
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/40 mb-0.5">P/L (24H)</div>
          <div
            className="text-[14px] font-semibold tabular leading-tight"
            style={{ color: up ? "var(--up)" : "var(--down)" }}
          >
            {fmtSignedMoney(pl)}
          </div>
        </div>
      </div>

      {/* Sparkline footer */}
      <div className="h-8 -mx-1 mt-1.5">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={sparkSeries(equity || 100)} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={`broker-spark-${broker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={meta.accent} stopOpacity={0.45} />
                <stop offset="100%" stopColor={meta.accent} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="y"
              stroke={meta.accent}
              strokeWidth={1.6}
              fill={`url(#broker-spark-${broker})`}
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  );
};

export const BrokerCarousel = () => {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/broker/all`);
        if (alive) setData(r.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  return (
    <div
      className="flex gap-3 overflow-x-auto snap-x snap-mandatory pb-2 -mx-4 px-4 scroll-y"
      style={{ scrollbarWidth: "none" }}
      data-testid="broker-carousel"
    >
      <BrokerCard broker="oanda" data={data?.oanda} idx={0} />
      <BrokerCard broker="alpaca" data={data?.alpaca} idx={1} />
      <BrokerCard broker="sim" data={data?.sim} idx={2} />
    </div>
  );
};

export default BrokerCarousel;
