import React, { useEffect, useState } from "react";
import axios from "axios";
import { AnimatePresence, motion } from "framer-motion";
import { Brain, CheckCircle2, MinusCircle, ShieldAlert, XCircle } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ACTION_META = {
  LONG: { color: "var(--up)", bg: "rgba(34,197,94,0.14)", icon: CheckCircle2 },
  SHORT: { color: "var(--down)", bg: "rgba(239,68,68,0.14)", icon: XCircle },
  HOLD: { color: "var(--warn)", bg: "rgba(245,158,11,0.14)", icon: MinusCircle },
};

const WORKER_META = {
  "jarvis-synth": { label: "OANDA Forex", color: "var(--accent-2)" },
  "jarvis-synth-alpaca": { label: "Alpaca Multi", color: "var(--accent-1)" },
};

const fmtTime = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "—";
  }
};

const fmtDate = (iso) => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMin = (now - d) / 60000;
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${Math.floor(diffMin)}m ago`;
    if (diffMin < 1440) return `${Math.floor(diffMin / 60)}h ago`;
    return d.toLocaleDateString();
  } catch {
    return "";
  }
};

const CycleRow = ({ cycle, idx }) => {
  const action = (cycle.action || "HOLD").toUpperCase();
  const meta = ACTION_META[action] || ACTION_META.HOLD;
  const Icon = meta.icon;
  const worker = WORKER_META[cycle.worker] || { label: cycle.worker, color: "var(--text-3)" };

  // Find any vetoing filter for the reason badge
  const vetoFilter = (cycle.filters || []).find((f) => !f.allowed);

  const tauricNum =
    typeof cycle.tauric_confidence === "number" ? cycle.tauric_confidence : null;
  const kronosUp =
    typeof cycle.kronos_upside_prob === "number" ? cycle.kronos_upside_prob : null;

  return (
    <motion.div
      className="grid grid-cols-12 gap-3 items-start py-3 px-1 border-b border-white/5"
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: idx * 0.03, ease: [0.22, 1, 0.36, 1] }}
      data-testid={`brain-cycle-row-${idx}`}
    >
      {/* Time + worker */}
      <div className="col-span-3 md:col-span-2 flex flex-col gap-0.5 min-w-0">
        <span className="text-[12px] tabular text-white/85 leading-none">
          {fmtTime(cycle.timestamp)}
        </span>
        <span className="text-[10px] text-white/35">{fmtDate(cycle.timestamp)}</span>
        <span
          className="text-[9px] tracking-[0.06em] uppercase mt-0.5 truncate"
          style={{ color: worker.color }}
        >
          {worker.label}
        </span>
      </div>

      {/* Action + instrument */}
      <div className="col-span-4 md:col-span-3 flex items-center gap-2 min-w-0">
        <span
          className="flex items-center gap-1 text-[11px] font-semibold px-1.5 py-0.5 rounded-md flex-shrink-0"
          style={{ background: meta.bg, color: meta.color }}
        >
          <Icon size={11} />
          {action}
        </span>
        <span className="text-[13px] font-medium tracking-tight truncate">
          {cycle.instrument}
        </span>
      </div>

      {/* Scores (only when present) */}
      <div className="col-span-5 md:col-span-3 flex flex-col gap-0.5 min-w-0">
        {tauricNum != null && (
          <div className="flex items-center gap-1.5 text-[11px]">
            <span className="text-white/40">Tauric</span>
            <span className="tabular" style={{ color: tauricNum >= 7 ? "var(--up)" : "var(--text-3)" }}>
              {cycle.tauric_verdict} · {tauricNum}/10
            </span>
          </div>
        )}
        {kronosUp != null && (
          <div className="flex items-center gap-1.5 text-[11px]">
            <span className="text-white/40">Kronos</span>
            <span className="tabular" style={{ color: kronosUp > 0.5 ? "var(--up)" : "var(--down)" }}>
              {(kronosUp * 100).toFixed(0)}%
              <span className="text-white/35"> · {cycle.kronos_confidence}</span>
            </span>
          </div>
        )}
      </div>

      {/* Reasoning */}
      <div className="col-span-12 md:col-span-4 text-[11.5px] text-white/55 leading-snug">
        {vetoFilter && (
          <span className="inline-flex items-center gap-1 mr-1.5 mb-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium"
                style={{ background: "rgba(239,68,68,0.10)", color: "var(--down)" }}>
            <ShieldAlert size={10} />
            {vetoFilter.name}
          </span>
        )}
        {cycle.reasoning}
      </div>
    </motion.div>
  );
};

export const BotBrainPanel = ({ delay = 0.5 }) => {
  const [data, setData] = useState({ cycles: [], counts: { LONG: 0, SHORT: 0, HOLD: 0 } });
  const [filter, setFilter] = useState("ALL");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/bot-brain/cycles?limit=12`);
        if (alive) setData(r.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 8000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const filtered = (data.cycles || []).filter(
    (c) => filter === "ALL" || (c.action || "").toUpperCase() === filter
  );

  return (
    <motion.section
      className="card p-5"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="bot-brain-panel"
    >
      <header className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{
              background: "rgba(155,123,255,0.18)",
              color: "var(--accent-2)",
            }}
          >
            <Brain size={15} />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold tracking-tight leading-none">
              Bot Brain
            </h3>
            <div className="text-[11px] text-white/40 mt-0.5">
              Live pipeline decisions · refreshes every 8s
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-white/[0.04] rounded-full p-1 border border-white/5">
          {["ALL", "LONG", "SHORT", "HOLD"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-[11px] px-2.5 py-1 rounded-full transition tabular ${
                filter === f
                  ? "bg-white/12 text-white"
                  : "text-white/50 hover:text-white"
              }`}
              data-testid={`brain-filter-${f.toLowerCase()}`}
            >
              {f}{" "}
              {f !== "ALL" && (
                <span className="text-white/45">{data.counts?.[f] ?? 0}</span>
              )}
            </button>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-12 gap-3 text-[10px] tracking-[0.08em] uppercase text-white/30 px-1 pb-2 border-b border-white/5">
        <div className="col-span-3 md:col-span-2">Time / Worker</div>
        <div className="col-span-4 md:col-span-3">Action</div>
        <div className="col-span-5 md:col-span-3">Scores</div>
        <div className="hidden md:block md:col-span-4">Reasoning</div>
      </div>

      {filtered.length === 0 ? (
        <div className="py-10 text-center text-[12px] text-white/40">
          {data.cycles.length === 0
            ? "Bot brain is quiet. Decisions will appear here as the Railway workers tick."
            : `No ${filter.toLowerCase()} decisions in the last batch.`}
        </div>
      ) : (
        <div className="max-h-[460px] overflow-y-auto scroll-y -mx-1 px-1">
          <AnimatePresence>
            {filtered.map((cycle, i) => (
              <CycleRow key={`${cycle.worker}-${cycle.instrument}-${cycle.timestamp}`} cycle={cycle} idx={i} />
            ))}
          </AnimatePresence>
        </div>
      )}
    </motion.section>
  );
};

export default BotBrainPanel;
