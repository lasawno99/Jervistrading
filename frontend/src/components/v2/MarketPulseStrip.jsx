import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const FG_COLOR = (v) => {
  if (v <= 24) return { color: "#ef4444", label: "Extreme Fear" };
  if (v <= 44) return { color: "#f97316", label: "Fear" };
  if (v <= 55) return { color: "#a3a3a3", label: "Neutral" };
  if (v <= 74) return { color: "#22c55e", label: "Greed" };
  return { color: "#16a34a", label: "Extreme Greed" };
};

const REGIME_META = {
  bull: { color: "#22c55e", bg: "rgba(34,197,94,0.15)", border: "rgba(34,197,94,0.35)", label: "BULL", Icon: TrendingUp },
  bear: { color: "#ef4444", bg: "rgba(239,68,68,0.15)", border: "rgba(239,68,68,0.35)", label: "BEAR", Icon: TrendingDown },
  chop: { color: "#a3a3a3", bg: "rgba(163,163,163,0.12)", border: "rgba(163,163,163,0.30)", label: "CHOP", Icon: null },
};

/**
 * Compact strip combining:
 *  - Market regime pill (bull/bear/chop)
 *  - Fear & Greed score chip
 *  - Top movers marquee (8 tickers, alternating gainers and losers)
 *
 * Single ~36px row — designed to slip between TodayProfitHero and the cluster
 * without breaking the single-screen mobile constraint.
 */
export const MarketPulseStrip = ({ delay = 0.15, onRegimeClick }) => {
  const [regime, setRegime] = useState(null);
  const [fg, setFg] = useState(null);
  const [movers, setMovers] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [r, f, m] = await Promise.all([
          axios.get(`${API}/market/regime`, { timeout: 10000 }).catch(() => null),
          axios.get(`${API}/market/fear-greed`, { timeout: 10000 }).catch(() => null),
          axios.get(`${API}/market/top-movers?top_n=4`, { timeout: 10000 }).catch(() => null),
        ]);
        if (!alive) return;
        if (r?.data) setRegime(r.data);
        if (f?.data) setFg(f.data);
        if (m?.data) setMovers(m.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 90000); // align with 75s server cache
    return () => { alive = false; clearInterval(t); };
  }, []);

  const fgInfo = fg ? FG_COLOR(fg.value) : null;
  const regimeMeta = REGIME_META[regime?.regime] || REGIME_META.chop;
  const RegimeIcon = regimeMeta.Icon;

  // Interleave gainers and losers for the marquee
  const tickers = (() => {
    if (!movers) return [];
    const out = [];
    const g = movers.gainers || [];
    const l = movers.losers || [];
    const n = Math.max(g.length, l.length);
    for (let i = 0; i < n; i++) {
      if (g[i]) out.push({ ...g[i], up: true });
      if (l[i]) out.push({ ...l[i], up: false });
    }
    return out;
  })();

  return (
    <motion.div
      className="flex items-center gap-2"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="market-pulse-strip"
    >
      {/* Regime pill — clickable to open Risk-Off sheet */}
      <button
        type="button"
        onClick={onRegimeClick}
        className="flex items-center gap-1 px-2 py-1 rounded-full flex-shrink-0 hover:scale-105 transition"
        style={{ background: regimeMeta.bg, border: `1px solid ${regimeMeta.border}` }}
        data-testid="market-regime-pill"
        aria-label="Open Risk-Off controls"
      >
        {RegimeIcon && <RegimeIcon size={11} style={{ color: regimeMeta.color }} />}
        <span className="text-[10px] font-semibold tracking-[0.12em]" style={{ color: regimeMeta.color }}>
          {regimeMeta.label}
        </span>
      </button>

      {/* Fear & Greed chip */}
      {fgInfo && (
        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded-full flex-shrink-0"
          style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
          data-testid="fear-greed-chip"
          title={`Fear & Greed: ${fg.value} (${fgInfo.label})`}
        >
          <span
            className="inline-flex items-center justify-center text-[10px] font-bold tabular w-5 h-5 rounded-full"
            style={{ background: fgInfo.color, color: "#0b0b10" }}
          >
            {fg.value}
          </span>
          <span className="text-[10px] text-white/60 font-medium uppercase tracking-wider hidden sm:inline">
            {fgInfo.label}
          </span>
        </div>
      )}

      {/* Top movers marquee (scrolls horizontally if overflowing) */}
      <div
        className="flex-1 min-w-0 overflow-hidden whitespace-nowrap"
        style={{ maskImage: "linear-gradient(to right, transparent 0, #000 8%, #000 92%, transparent 100%)", WebkitMaskImage: "linear-gradient(to right, transparent 0, #000 8%, #000 92%, transparent 100%)" }}
        data-testid="top-movers-marquee"
      >
        {tickers.length > 0 ? (
          <div className="inline-flex items-center gap-3 marquee-track" style={{ animation: "marquee 28s linear infinite" }}>
            {tickers.map((t, i) => (
              <span key={`a-${t.symbol}-${i}`} className="inline-flex items-center gap-1 text-[11px]">
                <span className="font-semibold text-white/85">{t.symbol}</span>
                <span
                  className="tabular font-medium"
                  style={{ color: t.up ? "var(--up)" : "var(--down)" }}
                >
                  {t.up ? "+" : ""}{t.change_24h.toFixed(2)}%
                </span>
              </span>
            ))}
            {tickers.map((t, i) => (
              <span key={`b-${t.symbol}-${i}`} aria-hidden="true" className="inline-flex items-center gap-1 text-[11px]">
                <span className="font-semibold text-white/85">{t.symbol}</span>
                <span
                  className="tabular font-medium"
                  style={{ color: t.up ? "var(--up)" : "var(--down)" }}
                >
                  {t.up ? "+" : ""}{t.change_24h.toFixed(2)}%
                </span>
              </span>
            ))}
          </div>
        ) : (
          <span className="text-[10px] text-white/35">loading market…</span>
        )}
      </div>

      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .marquee-track:hover { animation-play-state: paused !important; }
      `}</style>
    </motion.div>
  );
};

export default MarketPulseStrip;
