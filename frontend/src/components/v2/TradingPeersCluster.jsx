import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Info, RotateCcw } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(Number.isFinite(v) ? v : 0);

const COLORS = {
  bullish: { stroke: "#22c55e", glow: "rgba(34,197,94,0.55)" },
  bearish: { stroke: "#ef4444", glow: "rgba(239,68,68,0.55)" },
  neutral: { stroke: "#6c8dff", glow: "rgba(108,141,255,0.55)" },
  online:  { stroke: "#9b7bff", glow: "rgba(155,123,255,0.55)" },
  offline: { stroke: "#525a73", glow: "rgba(80,90,120,0.45)" },
};
const colorFor = (n) => COLORS[n.status] || COLORS.neutral;

export const TradingPeersCluster = ({ onSelect }) => {
  const [data, setData] = useState({ nodes: [] });
  const [combinedWealth, setCombinedWealth] = useState(0);
  const [active, setActive] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [p, b] = await Promise.all([
          axios.get(`${API}/dashboard/peers`),
          axios.get(`${API}/broker/all`),
        ]);
        if (!alive) return;
        setData(p.data);
        setCombinedWealth(b.data?.combined?.total_wealth ?? 0);
      } catch {}
    };
    load();
    const t = setInterval(load, 20000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const allNodes = useMemo(() => data.nodes || [], [data]);
  const nodes = useMemo(() => {
    const assets = allNodes.filter((n) => n.kind === "asset").slice(0, 6);
    return assets.length >= 6 ? assets : allNodes.slice(0, 6);
  }, [allNodes]);

  const positions = useMemo(() => {
    const count = nodes.length || 1;
    return nodes.map((n, i) => {
      const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
      return { ...n, x: 50 + 33 * Math.cos(angle), y: 50 + 33 * Math.sin(angle) };
    });
  }, [nodes]);

  return (
    <motion.section
      className="card p-3 flex flex-col"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
      data-testid="trading-peers-cluster"
    >
      <header className="flex items-center justify-between mb-0">
        <button className="w-7 h-7 rounded-lg flex items-center justify-center text-white/45 hover:text-white hover:bg-white/5 transition" aria-label="Reset">
          <RotateCcw size={13} />
        </button>
        <span className="text-[10px] tracking-[0.14em] uppercase text-white/45 font-medium">Trading Cluster</span>
        <button className="w-7 h-7 rounded-lg flex items-center justify-center text-white/45 hover:text-white hover:bg-white/5 transition" aria-label="Info">
          <Info size={13} />
        </button>
      </header>

      <div className="relative w-full mx-auto" style={{ aspectRatio: "1", maxWidth: 220, maxHeight: 220 }}>
        <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full pointer-events-none">
          {positions.map((p) => {
            const c = colorFor(p);
            return (
              <line key={`l-${p.id}`} x1="50" y1="50" x2={p.x} y2={p.y}
                stroke={c.stroke} strokeWidth="0.22" strokeOpacity="0.32" strokeDasharray="0.7 0.8" />
            );
          })}
          {positions.map((p) => {
            const c = colorFor(p);
            return <circle key={`d-${p.id}`} cx={(50 + p.x) / 2} cy={(50 + p.y) / 2} r="0.55" fill={c.stroke} opacity="0.85" />;
          })}
        </svg>

        <motion.div
          className="absolute"
          style={{ left: "50%", top: "50%", transform: "translate(-50%, -50%)" }}
          initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
        >
          <div
            className="rounded-full flex flex-col items-center justify-center node-pulse"
            style={{
              width: 80, height: 80,
              background: "radial-gradient(circle at 30% 30%, rgba(255,255,255,0.95), var(--accent-1) 40%, var(--accent-2) 100%)",
              boxShadow: "0 0 36px rgba(108,141,255,0.55), inset 0 0 16px rgba(255,255,255,0.25)",
              "--node-glow": "rgba(108,141,255,0.65)",
            }}
            data-testid="cluster-center"
          >
            <span className="text-[11px] font-semibold tracking-wide text-white/95">YOU</span>
            <span className="text-[10px] font-medium tabular text-white/85 mt-0.5">{fmtMoney(combinedWealth)}</span>
          </div>
        </motion.div>

        {positions.map((n, idx) => {
          const c = colorFor(n);
          const isActive = active === n.id;
          const up = (n.change_pct ?? 0) >= 0;
          return (
            <motion.button
              key={n.id}
              className="absolute"
              style={{ left: `${n.x}%`, top: `${n.y}%`, transform: "translate(-50%, -50%)" }}
              initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.4 + idx * 0.05, ease: [0.22, 1, 0.36, 1] }}
              onClick={() => { setActive(n.id); onSelect && onSelect(n); }}
              data-testid={`peer-node-${n.id}`}
            >
              <div
                className="rounded-full flex flex-col items-center justify-center transition-all"
                style={{
                  width: 48, height: 48,
                  background: "rgba(10,12,18,0.92)",
                  border: `2px solid ${c.stroke}`,
                  boxShadow: `0 0 ${isActive ? 18 : 11}px ${c.glow}`,
                  color: c.stroke,
                  transform: isActive ? "scale(1.1)" : "scale(1)",
                }}
              >
                <span className="text-[10px] font-bold tracking-tight leading-none">{n.label}</span>
                {n.kind === "asset" && Math.abs(n.change_pct) > 0.01 && (
                  <span className="text-[8px] tabular font-medium leading-none mt-0.5"
                        style={{ color: up ? "var(--up)" : "var(--down)" }}>
                    {up ? "+" : ""}{n.change_pct.toFixed(2)}%
                  </span>
                )}
              </div>
            </motion.button>
          );
        })}
      </div>
    </motion.section>
  );
};

export default TradingPeersCluster;
