import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Info } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const COLORS = {
  bullish: { stroke: "#22c55e", glow: "rgba(34,197,94,0.55)" },
  bearish: { stroke: "#ef4444", glow: "rgba(239,68,68,0.55)" },
  neutral: { stroke: "#6c8dff", glow: "rgba(108,141,255,0.55)" },
  online:  { stroke: "#9b7bff", glow: "rgba(155,123,255,0.6)" },
  offline: { stroke: "#525a73", glow: "rgba(80,90,120,0.45)" },
};

const colorFor = (node) => COLORS[node.status] || COLORS.neutral;

export const TradingPeersCluster = ({ onSelect }) => {
  const [data, setData] = useState({ center: null, nodes: [] });
  const [active, setActive] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/dashboard/peers`);
        if (alive) setData(r.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 20000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // Lay out the (up to) 8 nodes on a circle. Larger viewBox so labels don't clip.
  const nodes = useMemo(() => data.nodes || [], [data]);
  const positions = useMemo(() => {
    const count = nodes.length || 1;
    return nodes.map((n, i) => {
      const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
      return {
        ...n,
        x: 50 + 33 * Math.cos(angle),
        y: 50 + 33 * Math.sin(angle),
      };
    });
  }, [nodes]);

  const stats = useMemo(() => {
    const high = nodes.filter((n) => n.status === "bullish").length;
    const neutral = nodes.filter(
      (n) => n.status === "neutral" || n.status === "online"
    ).length;
    const low = nodes.filter((n) => n.status === "bearish").length;
    return { high, neutral, low };
  }, [nodes]);

  const handleClick = (n) => {
    setActive(n.id);
    if (onSelect) onSelect(n);
  };

  return (
    <motion.section
      className="card p-5 flex flex-col"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
      data-testid="trading-peers-cluster"
    >
      <header className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-semibold tracking-tight">Trading Peers</h3>
          <Info size={13} className="text-white/35" />
        </div>
        <span
          className="text-[11px] font-medium px-2 py-0.5 rounded-md"
          style={{
            background: "rgba(155,123,255,0.15)",
            color: "var(--accent-2)",
          }}
        >
          {nodes.length}
        </span>
      </header>

      <div className="relative w-full" style={{ aspectRatio: "1" }}>
        {/* SVG layer for the connecting lines */}
        <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full pointer-events-none">
          {positions.map((p) => {
            const c = colorFor(p);
            return (
              <line
                key={`line-${p.id}`}
                x1="50"
                y1="50"
                x2={p.x}
                y2={p.y}
                stroke={c.stroke}
                strokeWidth="0.18"
                strokeOpacity="0.32"
                strokeDasharray="0.6 0.8"
              />
            );
          })}
        </svg>

        {/* Center node — JARVIS */}
        <motion.div
          className="absolute"
          style={{ left: "50%", top: "50%", transform: "translate(-50%, -50%)" }}
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
        >
          <div
            className="rounded-full flex items-center justify-center text-[12px] font-semibold node-pulse"
            style={{
              width: 64,
              height: 64,
              background:
                "radial-gradient(circle at 30% 30%, rgba(255,255,255,0.95), var(--accent-1) 40%, var(--accent-2) 100%)",
              color: "#fff",
              boxShadow:
                "0 0 38px rgba(108,141,255,0.55), inset 0 0 16px rgba(255,255,255,0.25)",
              "--node-glow": "rgba(108,141,255,0.65)",
            }}
            data-testid="cluster-center"
          >
            You
          </div>
        </motion.div>

        {/* Surrounding nodes */}
        {positions.map((n, idx) => {
          const c = colorFor(n);
          const isActive = active === n.id;
          const up = (n.change_pct ?? 0) >= 0;
          return (
            <motion.button
              key={n.id}
              className="absolute group"
              style={{
                left: `${n.x}%`,
                top: `${n.y}%`,
                transform: "translate(-50%, -50%)",
              }}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{
                duration: 0.5,
                delay: 0.4 + idx * 0.05,
                ease: [0.22, 1, 0.36, 1],
              }}
              onClick={() => handleClick(n)}
              data-testid={`peer-node-${n.id}`}
            >
              <div
                className="rounded-full flex items-center justify-center text-[11px] font-semibold transition-all"
                style={{
                  width: 44,
                  height: 44,
                  background: "rgba(15,15,20,0.85)",
                  border: `1.5px solid ${c.stroke}`,
                  boxShadow: `0 0 ${isActive ? 22 : 12}px ${c.glow}`,
                  color: c.stroke,
                  transform: isActive ? "scale(1.12)" : "scale(1)",
                }}
              >
                {n.label}
              </div>
              {n.kind === "asset" && Math.abs(n.change_pct) > 0.01 && (
                <div
                  className="absolute left-1/2 -translate-x-1/2 mt-1 text-[10px] tabular font-medium whitespace-nowrap"
                  style={{ color: up ? "var(--up)" : "var(--down)", top: "100%" }}
                >
                  {up ? "+" : ""}
                  {n.change_pct.toFixed(1)}%
                </div>
              )}
              {n.kind === "agent" && (
                <div
                  className="absolute left-1/2 -translate-x-1/2 mt-1 text-[9px] tracking-[0.06em] uppercase whitespace-nowrap"
                  style={{ color: "var(--text-3)", top: "100%" }}
                >
                  agent
                </div>
              )}
            </motion.button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-4 pt-3 border-t border-white/5">
        <LegendDot color="var(--up)" label={`High Perf · ${stats.high}`} />
        <LegendDot color="var(--accent-1)" label={`Neutral · ${stats.neutral}`} />
        <LegendDot color="var(--down)" label={`Low Perf · ${stats.low}`} />
      </div>
    </motion.section>
  );
};

const LegendDot = ({ color, label }) => (
  <div className="flex items-center gap-1.5">
    <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: color }} />
    <span className="text-[11px] text-white/55">{label}</span>
  </div>
);

export default TradingPeersCluster;
