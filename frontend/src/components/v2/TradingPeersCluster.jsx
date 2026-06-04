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

// Starting balance = 3 brokers × $100K paper-trading inception.
// Single source of truth — adjust here when real broker accounts are added.
const STARTING_BALANCE = 300_000;

const fmtAbsMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(Math.abs(Number.isFinite(v) ? v : 0));

export const TradingPeersCluster = ({ onSelect }) => {
  const [data, setData] = useState({ nodes: [] });
  const [combinedWealth, setCombinedWealth] = useState(0);
  const [lockedProfits, setLockedProfits] = useState(0);
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
        setLockedProfits(b.data?.combined?.locked_profits ?? 0);
      } catch {}
    };
    load();
    const t = setInterval(load, 20000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const profit = combinedWealth - STARTING_BALANCE;
  const isUp = profit >= 0;
  const profitColor = isUp ? "var(--up)" : "var(--down)";
  const profitGlow = isUp ? "rgba(34,197,94,0.45)" : "rgba(239,68,68,0.45)";

  const allNodes = useMemo(() => data.nodes || [], [data]);
  const nodes = useMemo(() => {
    const assets = allNodes.filter((n) => n.kind === "asset").slice(0, 6);
    return assets.length >= 6 ? assets : allNodes.slice(0, 6);
  }, [allNodes]);

  const positions = useMemo(() => {
    const count = nodes.length || 1;
    return nodes.map((n, i) => {
      const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
      // Deterministic per-index drift params so peers don't move in lockstep
      // but stay stable across re-renders. ~6s loop, ±3.5% box, slight rotation.
      const seed = (i * 9301 + 49297) % 233280;
      const phase = (seed / 233280) * 2 * Math.PI;
      const driftX = 3.2 + (i % 3) * 0.9;          // px, ±range
      const driftY = 2.6 + ((i + 1) % 3) * 0.9;
      const duration = 5.5 + (i * 0.7) % 3.5;       // 5.5..9s
      return {
        ...n,
        x: 50 + 33 * Math.cos(angle),
        y: 50 + 33 * Math.sin(angle),
        driftX, driftY, duration, phase,
      };
    });
  }, [nodes]);

  // 12 background "twinkle" stars at fixed positions inside the cluster panel.
  const stars = useMemo(() => {
    const seedRand = (i) => {
      const s = Math.sin(i * 12.9898) * 43758.5453;
      return s - Math.floor(s);
    };
    return Array.from({ length: 12 }, (_, i) => ({
      id: i,
      x: 10 + seedRand(i) * 80,
      y: 8 + seedRand(i + 7) * 84,
      r: 0.25 + seedRand(i + 13) * 0.45,
      delay: seedRand(i + 21) * 4,
      duration: 2.4 + seedRand(i + 31) * 2.6,
    }));
  }, []);

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
          {/* Galaxy twinkle stars — fixed positions, async pulsing opacity */}
          {stars.map((s) => (
            <circle key={`star-${s.id}`} cx={s.x} cy={s.y} r={s.r} fill="#cdd3ff">
              <animate attributeName="opacity"
                values="0.15;0.85;0.15"
                dur={`${s.duration}s`}
                begin={`${s.delay}s`}
                repeatCount="indefinite" />
            </circle>
          ))}
          {positions.map((p) => {
            const c = colorFor(p);
            return (
              <line key={`l-${p.id}`} x1="50" y1="50" x2={p.x} y2={p.y}
                stroke={c.stroke} strokeWidth="0.18" strokeOpacity="0.22" strokeDasharray="0.7 0.9" />
            );
          })}
          {positions.map((p) => {
            const c = colorFor(p);
            return <circle key={`d-${p.id}`} cx={(50 + p.x) / 2} cy={(50 + p.y) / 2} r="0.45" fill={c.stroke} opacity="0.7" />;
          })}
        </svg>

        <motion.div
          className="absolute pointer-events-none"
          style={{ left: "50%", top: "50%", transform: "translate(-50%, -50%)" }}
          initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
        >
          <div
            className="flex flex-col items-center justify-center text-center"
            style={{ minWidth: 96 }}
            data-testid="cluster-center"
          >
            <span
              className="text-[20px] font-bold tabular leading-none tracking-tight"
              style={{
                color: profitColor,
                textShadow: `0 0 18px ${profitGlow}, 0 0 6px ${profitGlow}`,
              }}
              data-testid="cluster-profit"
            >
              {isUp ? "+" : "−"}{fmtAbsMoney(profit)}
            </span>
            <span className="text-[8px] tracking-[0.16em] uppercase text-white/40 mt-1.5 font-medium">
              Profit
            </span>
            {lockedProfits > 0 && (
              <span
                className="text-[10px] tabular font-semibold mt-2"
                style={{ color: "var(--accent-1)" }}
                data-testid="cluster-cash"
              >
                {fmtAbsMoney(lockedProfits)} cash
              </span>
            )}
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
              style={{
                left: `${n.x}%`, top: `${n.y}%`,
                transform: "translate(-50%, -50%)",
                width: 36, height: 36, padding: 0, background: "transparent", border: "none",
              }}
              initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.4 + idx * 0.05, ease: [0.22, 1, 0.36, 1] }}
              onClick={() => { setActive(n.id); onSelect && onSelect(n); }}
              data-testid={`peer-node-${n.id}`}
            >
              {/* Galaxy drift — independent, looping micro-orbit per peer */}
              <motion.div
                animate={{
                  x: [-n.driftX, n.driftX, -n.driftX * 0.6, n.driftX * 0.8, -n.driftX],
                  y: [n.driftY, -n.driftY * 0.7, n.driftY * 0.4, -n.driftY, n.driftY],
                  opacity: [0.92, 1, 0.88, 1, 0.92],
                }}
                transition={{
                  duration: n.duration,
                  repeat: Infinity,
                  ease: "easeInOut",
                  delay: n.phase * 0.5,
                }}
              >
                <div
                  className="rounded-full flex flex-col items-center justify-center transition-all"
                  style={{
                    width: 36, height: 36,
                    background: "rgba(10,12,18,0.92)",
                    border: `1.5px solid ${c.stroke}`,
                    boxShadow: `0 0 ${isActive ? 14 : 8}px ${c.glow}`,
                    color: c.stroke,
                    transform: isActive ? "scale(1.12)" : "scale(1)",
                  }}
                >
                  <span className="text-[8.5px] font-bold tracking-tight leading-none">{n.label}</span>
                  {n.kind === "asset" && Math.abs(n.change_pct) > 0.01 && (
                    <span className="text-[6.5px] tabular font-medium leading-none mt-0.5"
                          style={{ color: up ? "var(--up)" : "var(--down)" }}>
                      {up ? "+" : ""}{n.change_pct.toFixed(2)}%
                    </span>
                  )}
                </div>
              </motion.div>
            </motion.button>
          );
        })}
      </div>
    </motion.section>
  );
};

export default TradingPeersCluster;
