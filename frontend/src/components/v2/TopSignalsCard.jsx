import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Bitcoin, Flame, Droplet, ChevronRight } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SIGNAL_META = {
  BUY: { color: "var(--up)", bg: "rgba(34,197,94,0.12)" },
  SELL: { color: "var(--down)", bg: "rgba(239,68,68,0.12)" },
  HOLD: { color: "var(--warn)", bg: "rgba(245,158,11,0.12)" },
};

const fallback = [
  { symbol: "BTC/USD", desc: "Strong momentum", action: "BUY", Icon: Bitcoin, color: "#f59e0b" },
  { symbol: "ETH/USD", desc: "Breakout", action: "BUY", Icon: Droplet, color: "#6c8dff" },
  { symbol: "Crude Oil", desc: "Watching", action: "HOLD", Icon: Flame, color: "#ef4444" },
];

export const TopSignalsCard = ({ delay = 0.4 }) => {
  const [signals, setSignals] = useState(fallback);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/bot/signals?limit=3`).then((r) => {
      if (!alive) return;
      const arr = r.data?.signals || r.data || [];
      if (Array.isArray(arr) && arr.length) {
        setSignals(
          arr.slice(0, 3).map((s, i) => ({
            symbol: s.symbol || s.instrument || fallback[i].symbol,
            desc: s.rationale || s.reason || fallback[i].desc,
            action: (s.action || s.side || "HOLD").toString().toUpperCase(),
            Icon: fallback[i % fallback.length].Icon,
            color: fallback[i % fallback.length].color,
          }))
        );
      }
    }).catch(() => {});
    return () => { alive = false; };
  }, []);

  return (
    <motion.div
      className="card p-4"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="top-signals-card"
    >
      <div className="card-title mb-3">Top Signals</div>
      <div className="space-y-3">
        {signals.map((s, i) => {
          const meta = SIGNAL_META[s.action] || SIGNAL_META.HOLD;
          return (
            <div key={i} className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center"
                style={{ background: `${s.color}22`, color: s.color }}
              >
                <s.Icon size={16} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-medium leading-tight truncate">
                  {s.symbol}
                </div>
                <div className="text-[11px] text-white/50 mt-0.5 truncate">{s.desc}</div>
              </div>
              <span
                className="text-[11px] font-semibold px-2 py-0.5 rounded-md"
                style={{ background: meta.bg, color: meta.color }}
              >
                {s.action}
              </span>
            </div>
          );
        })}
      </div>
      <button
        className="mt-4 w-full text-[13px] font-medium py-2 rounded-xl transition"
        style={{
          background: "rgba(108,141,255,0.12)",
          color: "var(--accent-1)",
        }}
        data-testid="view-all-signals"
      >
        View All Signals <ChevronRight size={13} className="inline -mt-0.5" />
      </button>
    </motion.div>
  );
};

export default TopSignalsCard;
