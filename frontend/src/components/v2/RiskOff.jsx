import React, { useEffect, useState } from "react";
import axios from "axios";
import { AnimatePresence, motion } from "framer-motion";
import { ShieldAlert, ShieldCheck, Loader2, X } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const useRiskStatus = (refreshMs = 60000) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/risk/status`, { timeout: 10000 });
      setStatus(r.data);
    } catch {}
  };

  useEffect(() => {
    load();
    const t = setInterval(load, refreshMs);
    return () => clearInterval(t);
  }, [refreshMs]);

  const setMode = async (mode) => {
    setLoading(true);
    try {
      const r = await axios.post(`${API}/risk/override`, { mode, by: "dashboard-user" }, { timeout: 10000 });
      setStatus(r.data);
      toast(`Risk-Off: ${r.data.active ? "ACTIVE" : "STANDBY"}`, { description: r.data.reason });
    } catch (e) {
      toast.error("Couldn't update Risk-Off", { description: String(e?.message || e) });
    } finally {
      setLoading(false);
    }
  };

  return { status, setMode, loading, refresh: load };
};

/**
 * Slim banner shown on Dashboard when Risk-Off is active.
 * Auto-hides when standby. Receives status from parent (single source of truth).
 */
export const RiskOffBanner = ({ status, onOpenControls }) => {
  return (
    <AnimatePresence>
      {status?.active && (
        <motion.button
          onClick={onOpenControls}
          className="w-full flex items-center justify-between gap-3 px-4 py-2.5 rounded-2xl text-left"
          style={{
            background: "linear-gradient(90deg, rgba(239,68,68,0.18), rgba(239,68,68,0.08))",
            border: "1px solid rgba(239,68,68,0.35)",
            boxShadow: "0 8px 24px rgba(239,68,68,0.18)",
          }}
          initial={{ opacity: 0, y: -8, height: 0 }}
          animate={{ opacity: 1, y: 0, height: "auto" }}
          exit={{ opacity: 0, y: -8, height: 0 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          data-testid="risk-off-banner"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <ShieldAlert size={18} style={{ color: "var(--down)" }} />
            <div className="min-w-0">
              <div className="text-[12px] font-semibold tracking-wide" style={{ color: "var(--down)" }}>
                RISK-OFF ACTIVE · workers paused
              </div>
              <div className="text-[11px] text-white/55 truncate">{status.reason}</div>
            </div>
          </div>
          <span className="text-[10px] text-white/45 flex-shrink-0">tap to manage</span>
        </motion.button>
      )}
    </AnimatePresence>
  );
};

/**
 * Sheet modal: shows live risk status + 3 mode buttons (Auto / Force On / Force Off).
 * Accepts status + setMode from parent so banner stays in sync.
 */
export const RiskOffSheet = ({ open, onClose, status, setMode, loading }) => {
  const isManualOn = status?.manual_override === "on";
  const isManualOff = status?.manual_override === "off";
  const isAuto = !status?.manual_override;
  const active = !!status?.active;

  const Pill = ({ active: a, label, sub, onClick, color, testId }) => (
    <button
      onClick={onClick}
      disabled={loading}
      className="flex-1 min-w-0 flex flex-col items-start text-left p-3 rounded-xl transition disabled:opacity-60"
      style={{
        background: a ? color.bg : "rgba(255,255,255,0.03)",
        border: `1px solid ${a ? color.border : "rgba(255,255,255,0.07)"}`,
      }}
      data-testid={testId}
    >
      <span className="text-[12px] font-semibold" style={{ color: a ? color.fg : "rgba(255,255,255,0.85)" }}>
        {label}
      </span>
      <span className="text-[10px] text-white/55 mt-0.5">{sub}</span>
    </button>
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          style={{ background: "rgba(8,8,12,0.6)", backdropFilter: "blur(14px)" }}
          onClick={onClose}
          data-testid="risk-off-sheet"
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-2xl p-5"
            style={{
              background: "rgba(18,18,26,0.96)",
              border: "1px solid var(--border-hi)",
              boxShadow: "0 32px 80px rgba(0,0,0,0.7)",
            }}
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <header className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div
                  className="w-9 h-9 rounded-xl flex items-center justify-center"
                  style={{
                    background: active ? "rgba(239,68,68,0.18)" : "rgba(34,197,94,0.16)",
                    color: active ? "var(--down)" : "var(--up)",
                  }}
                >
                  {active ? <ShieldAlert size={18} /> : <ShieldCheck size={18} />}
                </div>
                <div>
                  <h3 className="text-[15px] font-semibold tracking-tight leading-none">Risk-Off Mode</h3>
                  <div className="text-[11px] text-white/45 mt-0.5">
                    Pauses new entries when markets get ugly
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-white/55 hover:text-white"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </header>

            {/* Live status */}
            <div
              className="px-3 py-2.5 rounded-xl mb-4"
              style={{
                background: active ? "rgba(239,68,68,0.10)" : "rgba(34,197,94,0.08)",
                border: `1px solid ${active ? "rgba(239,68,68,0.30)" : "rgba(34,197,94,0.24)"}`,
              }}
              data-testid="risk-off-current"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] tracking-[0.12em] uppercase text-white/50">Current</span>
                <span
                  className="text-[10px] font-semibold tracking-wide"
                  style={{ color: active ? "var(--down)" : "var(--up)" }}
                >
                  {active ? "RISK-OFF · PAUSED" : "STANDBY · ACTIVE"}
                </span>
              </div>
              <div className="text-[12px] text-white/85 leading-snug">{status?.reason || "Loading…"}</div>
              {status && (
                <div className="flex items-center gap-3 mt-2 text-[10px] text-white/50">
                  <span>Regime: <strong style={{ color: "white" }}>{(status.regime || "?").toUpperCase()}</strong></span>
                  <span>F&amp;G: <strong style={{ color: "white" }}>{status.fg_value ?? "?"}</strong></span>
                  {status.mc_pct_24h != null && (
                    <span>Mkt 24h: <strong style={{ color: status.mc_pct_24h >= 0 ? "var(--up)" : "var(--down)" }}>
                      {status.mc_pct_24h >= 0 ? "+" : ""}{status.mc_pct_24h.toFixed(2)}%
                    </strong></span>
                  )}
                </div>
              )}
            </div>

            <div className="text-[10px] tracking-[0.12em] uppercase text-white/40 mb-2">Mode</div>
            <div className="flex gap-2 mb-3">
              <Pill
                active={isAuto}
                label="🤖 Auto"
                sub="CMC regime + Fear&Greed"
                onClick={() => setMode("auto")}
                color={{ bg: "rgba(108,141,255,0.15)", border: "rgba(108,141,255,0.35)", fg: "var(--accent-1)" }}
                testId="risk-mode-auto"
              />
              <Pill
                active={isManualOn}
                label="🛡 Force On"
                sub="Pause new entries"
                onClick={() => setMode("on")}
                color={{ bg: "rgba(239,68,68,0.16)", border: "rgba(239,68,68,0.40)", fg: "var(--down)" }}
                testId="risk-mode-on"
              />
              <Pill
                active={isManualOff}
                label="🟢 Force Off"
                sub="Always allow trades"
                onClick={() => setMode("off")}
                color={{ bg: "rgba(34,197,94,0.16)", border: "rgba(34,197,94,0.36)", fg: "var(--up)" }}
                testId="risk-mode-off"
              />
            </div>

            <div className="text-[10px] text-white/40 leading-relaxed">
              When Risk-Off is active, Railway workers should poll <code className="text-white/55">/api/risk/status</code> and skip new entries.
              Open positions keep their stops — only entries pause.
              {loading && <span className="ml-2"><Loader2 size={10} className="inline animate-spin" /> updating…</span>}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export { useRiskStatus };
