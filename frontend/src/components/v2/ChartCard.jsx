import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChevronRight, Star } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const TIMEFRAMES = ["1H", "1D", "1W", "1M", "3M", "1Y"];

// Build a deterministic illustrative price series for the focal symbol so the
// chart looks alive even when broker history isn't backed yet.
const buildSeries = (symbol, anchor = 100) => {
  const seed = Array.from(symbol).reduce((a, c) => a + c.charCodeAt(0), 0);
  const data = [];
  let v = anchor;
  for (let i = 0; i < 60; i++) {
    const noise = Math.sin((seed + i) * 0.37) * 0.012 + Math.cos((seed + i) * 0.91) * 0.006;
    v = v * (1 + noise);
    data.push({
      t: i,
      label: `t${i}`,
      price: Math.round(v * 100) / 100,
    });
  }
  return data;
};

const fmtMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(v) ? v : 0);

export const ChartCard = ({ symbol = "BTC", name = "Bitcoin", anchor = 80000 }) => {
  const [tf, setTf] = useState("1D");
  const [data, setData] = useState([]);
  const [price, setPrice] = useState(anchor);

  useEffect(() => {
    const series = buildSeries(`${symbol}${tf}`, anchor);
    setData(series);
    setPrice(series[series.length - 1].price);
  }, [symbol, tf, anchor]);

  const first = data[0]?.price || price;
  const change = price - first;
  const changePct = first ? (change / first) * 100 : 0;
  const up = change >= 0;
  const high = data.length ? Math.max(...data.map((d) => d.price)) : 0;
  const low = data.length ? Math.min(...data.map((d) => d.price)) : 0;

  return (
    <motion.section
      className="card p-5"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
      data-testid="chart-card"
    >
      <header className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center text-[13px] font-semibold flex-shrink-0"
            style={{
              background:
                "linear-gradient(135deg, rgba(108,141,255,0.22), rgba(155,123,255,0.22))",
              border: "1px solid var(--border)",
            }}
          >
            {symbol[0]}
          </div>
          <div className="min-w-0">
            <h3 className="text-[15px] font-semibold tracking-tight truncate">
              {name} <span className="text-white/40 font-normal">· {symbol}</span>
            </h3>
            <div className="text-[11px] text-white/40 mt-0.5">
              {symbol}/USD · {tf} · LIVE
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 ml-2 mb-px" />
            </div>
          </div>
        </div>
        <button className="text-white/45 hover:text-white transition">
          <Star size={16} />
        </button>
      </header>

      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-[26px] font-semibold tracking-tight tabular">
          {fmtMoney(price)}
        </span>
        <span
          className="text-[12px] tabular"
          style={{ color: up ? "var(--up)" : "var(--down)" }}
        >
          {up ? "▲" : "▼"} {fmtMoney(Math.abs(change))} ({changePct >= 0 ? "+" : ""}
          {changePct.toFixed(2)}%)
        </span>
      </div>

      <div className="h-36 sm:h-44 md:h-52 -mx-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={up ? "var(--up)" : "var(--down)"} stopOpacity={0.35} />
                <stop offset="100%" stopColor={up ? "var(--up)" : "var(--down)"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" hide />
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <Tooltip
              cursor={{ stroke: "rgba(255,255,255,0.18)", strokeWidth: 1 }}
              contentStyle={{
                background: "rgba(15,15,20,0.96)",
                border: "1px solid var(--border-hi)",
                borderRadius: 10,
                fontSize: 12,
                padding: "6px 10px",
              }}
              labelStyle={{ display: "none" }}
              formatter={(v) => [fmtMoney(v), "Price"]}
            />
            <Area
              type="monotone"
              dataKey="price"
              stroke={up ? "var(--up)" : "var(--down)"}
              strokeWidth={2}
              fill="url(#chart-fill)"
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center justify-between mt-3">
        <div className="flex items-center gap-1 bg-white/[0.04] rounded-full p-1 border border-white/5">
          {TIMEFRAMES.map((t) => (
            <button
              key={t}
              onClick={() => setTf(t)}
              className={`text-[11px] px-2.5 py-1 rounded-full transition ${
                tf === t
                  ? "bg-white/12 text-white"
                  : "text-white/50 hover:text-white"
              }`}
              data-testid={`tf-${t}`}
            >
              {t}
            </button>
          ))}
        </div>
        <button className="text-[11px] text-white/45 hover:text-white flex items-center gap-1 transition">
          Expand <ChevronRight size={12} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-white/5">
        <Stat label="High" value={fmtMoney(high)} />
        <Stat label="Low" value={fmtMoney(low)} />
        <Stat label="Range" value={fmtMoney(high - low)} />
      </div>
    </motion.section>
  );
};

const Stat = ({ label, value }) => (
  <div>
    <div className="text-[10px] tracking-[0.12em] uppercase text-white/35">{label}</div>
    <div className="text-[13px] font-medium tabular mt-0.5 text-white/85">{value}</div>
  </div>
);

export default ChartCard;
