/**
 * AutoPilot — surfaces the autonomous compare+promote pipeline.
 *
 * Shows:
 *  • Pilot toggle (Watch only / Auto-promote) + Run-now button
 *  • N pending compares whose gate cleared but await user one-tap promote
 *  • Recent decisions feed (last 5)
 *
 * Connects to:
 *  - GET    /api/autopilot/status
 *  - POST   /api/autopilot/settings       { enabled, auto_promote }
 *  - POST   /api/autopilot/run-now
 *  - POST   /api/autopilot/promote        { symbol }
 *  - POST   /api/autopilot/dismiss        { symbol }
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Bot, Play, Send, Check, X as XIcon, Power, Zap, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtTimeAgo = (iso) => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};

const StatusPill = ({ status }) => {
  const cfg = {
    auto_promoted: { bg: "rgba(34,197,94,0.20)", fg: "var(--up)", label: "AUTO" },
    user_promoted: { bg: "rgba(34,197,94,0.18)", fg: "var(--up)", label: "PROMOTED" },
    pending_review: { bg: "rgba(245,158,11,0.18)", fg: "var(--warn)", label: "READY" },
    blocked: { bg: "rgba(255,255,255,0.06)", fg: "rgba(255,255,255,0.50)", label: "BLOCKED" },
    dismissed: { bg: "rgba(255,255,255,0.04)", fg: "rgba(255,255,255,0.40)", label: "DISMISSED" },
  }[status] || { bg: "rgba(255,255,255,0.04)", fg: "rgba(255,255,255,0.40)", label: status };
  return (
    <span className="px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wide tabular"
          style={{ background: cfg.bg, color: cfg.fg }}>
      {cfg.label}
    </span>
  );
};

const PendingRow = ({ row, onPromote, onDismiss, busy }) => {
  const e = row.ensemble || {};
  const s = row.single_pod || {};
  const g = row.promote_gate || {};
  return (
    <div className="rounded-lg p-3"
         style={{ background: "rgba(245,158,11,0.05)", border: "1px solid rgba(245,158,11,0.28)" }}
         data-testid={`autopilot-pending-${row.symbol}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-[12px] text-white/95 tabular">{row.symbol}</span>
          <StatusPill status={row.status} />
        </div>
        <span className="text-[9px] text-white/40">{fmtTimeAgo(row.finished_at)}</span>
      </div>
      <div className="grid grid-cols-4 gap-1.5 text-[9px] mb-2">
        <div>
          <div className="text-white/40 uppercase tracking-[0.10em]">WR</div>
          <div className="tabular">
            <span className="text-white/45">{(s.win_rate ?? 0).toFixed(0)}%</span>
            <span className="text-white/30 mx-0.5">→</span>
            <span className="font-bold" style={{ color: g.win_rate_up ? "var(--up)" : "var(--down)" }}>
              {(e.win_rate ?? 0).toFixed(0)}%
            </span>
          </div>
        </div>
        <div>
          <div className="text-white/40 uppercase tracking-[0.10em]">PF</div>
          <div className="tabular">
            <span className="text-white/45">{(s.profit_factor ?? 0).toFixed(2)}</span>
            <span className="text-white/30 mx-0.5">→</span>
            <span className="font-bold" style={{ color: g.profit_factor_up ? "var(--up)" : "var(--down)" }}>
              {(e.profit_factor ?? 0).toFixed(2)}
            </span>
          </div>
        </div>
        <div>
          <div className="text-white/40 uppercase tracking-[0.10em]">Sharpe</div>
          <div className="tabular">
            <span className="text-white/45">{(s.sharpe_ratio ?? 0).toFixed(2)}</span>
            <span className="text-white/30 mx-0.5">→</span>
            <span className="font-bold" style={{ color: g.sharpe_up ? "var(--up)" : "var(--down)" }}>
              {(e.sharpe_ratio ?? 0).toFixed(2)}
            </span>
          </div>
        </div>
        <div>
          <div className="text-white/40 uppercase tracking-[0.10em]">Max DD</div>
          <div className="tabular">
            <span className="text-white/45">{(s.max_drawdown_pct ?? 0).toFixed(1)}%</span>
            <span className="text-white/30 mx-0.5">→</span>
            <span className="font-bold" style={{ color: g.drawdown_down ? "var(--up)" : "var(--down)" }}>
              {(e.max_drawdown_pct ?? 0).toFixed(1)}%
            </span>
          </div>
        </div>
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => onPromote(row.symbol)}
          disabled={busy}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[10px] font-semibold disabled:opacity-50 transition"
          style={{ background: "linear-gradient(135deg, var(--up), #16a34a)", color: "#fff" }}
          data-testid={`autopilot-promote-${row.symbol}`}
        >
          {busy ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}
          Promote to workers
        </button>
        <button
          onClick={() => onDismiss(row.symbol)}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-[10px] font-semibold disabled:opacity-50 transition text-white/55 hover:text-white/85"
          style={{ background: "rgba(255,255,255,0.05)" }}
          data-testid={`autopilot-dismiss-${row.symbol}`}
        >
          <XIcon size={10} />
        </button>
      </div>
    </div>
  );
};

export const AutoPilot = ({ delay = 0.27 }) => {
  const [data, setData] = useState(null);
  const [runningNow, setRunningNow] = useState(false);
  const [busySymbol, setBusySymbol] = useState(null);
  const [savingToggle, setSavingToggle] = useState(false);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/autopilot/status`, { timeout: 10000 });
      setData(r.data);
    } catch {}
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  const toggleAutoPromote = async () => {
    setSavingToggle(true);
    try {
      const next = !data.settings.auto_promote;
      await axios.post(`${API}/autopilot/settings`, { auto_promote: next });
      toast.success(`Auto-promote ${next ? "ENABLED" : "DISABLED"}`, {
        description: next
          ? "Compares that clear the gate will auto-apply to workers."
          : "Compares need your tap to promote.",
      });
      await load();
    } catch (e) {
      toast.error("Failed to update", { description: String(e?.message || e) });
    } finally {
      setSavingToggle(false);
    }
  };

  const runNow = async () => {
    setRunningNow(true);
    try {
      await axios.post(`${API}/autopilot/run-now`);
      toast.success("AutoPilot scan queued", {
        description: "Will compare qualifying instruments in the background.",
      });
      // Brief delay then refresh
      setTimeout(load, 3000);
    } catch (e) {
      toast.error("Run failed", { description: String(e?.message || e) });
    } finally {
      setRunningNow(false);
    }
  };

  const promote = async (symbol) => {
    setBusySymbol(symbol);
    try {
      await axios.post(`${API}/autopilot/promote`, { symbol });
      toast.success(`Promoted ${symbol}`, {
        description: "Workers will pick up the new params on next cycle.",
      });
      await load();
    } catch (e) {
      toast.error("Promote failed", { description: String(e?.response?.data?.detail || e?.message || e) });
    } finally {
      setBusySymbol(null);
    }
  };

  const dismiss = async (symbol) => {
    setBusySymbol(symbol);
    try {
      await axios.post(`${API}/autopilot/dismiss`, { symbol });
      toast(`Dismissed ${symbol}`);
      await load();
    } catch (e) {
      toast.error("Dismiss failed", { description: String(e?.message || e) });
    } finally {
      setBusySymbol(null);
    }
  };

  if (!data) return null;
  const { settings, thresholds, pending, recent, last_run } = data;
  const autoPromote = !!settings?.auto_promote;

  return (
    <motion.section
      className="card p-4"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="autopilot-card"
    >
      <header className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(155,123,255,0.15)", color: "var(--accent-2)" }}>
            <Bot size={15} />
          </div>
          <div>
            <h3 className="text-[14px] font-semibold tracking-tight leading-none">AutoPilot</h3>
            <div className="text-[10px] text-white/45 mt-0.5">
              ≥{thresholds.min_rate_pct}% rate · ≥{thresholds.min_samples} signals · every {thresholds.interval_hours}h
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={toggleAutoPromote}
            disabled={savingToggle}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold disabled:opacity-50 transition"
            style={{
              background: autoPromote ? "rgba(34,197,94,0.16)" : "rgba(255,255,255,0.05)",
              color: autoPromote ? "var(--up)" : "rgba(255,255,255,0.55)",
              border: autoPromote ? "1px solid rgba(34,197,94,0.30)" : "1px solid rgba(255,255,255,0.08)",
            }}
            title={autoPromote ? "Auto-promote ON — compares apply themselves when gate clears" : "Auto-promote OFF — you tap to promote"}
            data-testid="autopilot-toggle"
          >
            {savingToggle ? <Loader2 size={10} className="animate-spin" /> : autoPromote ? <Zap size={10} /> : <Power size={10} />}
            {autoPromote ? "AUTO" : "WATCH"}
          </button>
          <button
            onClick={runNow}
            disabled={runningNow}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold disabled:opacity-50 transition"
            style={{ background: "rgba(108,141,255,0.16)", color: "var(--accent-1)", border: "1px solid rgba(108,141,255,0.30)" }}
            data-testid="autopilot-run-now"
          >
            {runningNow ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
            Run now
          </button>
        </div>
      </header>

      {/* Pending review queue */}
      {pending && pending.length > 0 && (
        <div className="space-y-2 mb-3">
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/45 px-0.5">
            Ready to promote · {pending.length}
          </div>
          <AnimatePresence>
            {pending.map((row) => (
              <motion.div
                key={row.symbol}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.3 }}
              >
                <PendingRow row={row} onPromote={promote} onDismiss={dismiss} busy={busySymbol === row.symbol} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Recent feed (last 5) */}
      {recent && recent.length > 0 && (
        <div>
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/45 px-0.5 mb-1.5">
            Recent decisions
          </div>
          <div className="space-y-1">
            {recent.slice(0, 5).map((r, i) => (
              <div key={`${r.symbol}-${r.finished_at}-${i}`}
                   className="flex items-center justify-between text-[10px] tabular px-2 py-1.5 rounded"
                   style={{ background: "rgba(255,255,255,0.02)" }}>
                <span className="font-medium text-white/85">{r.symbol}</span>
                <div className="flex items-center gap-2">
                  <span className="text-white/45">
                    <span className="text-white/65">{(r.ensemble?.win_rate ?? 0).toFixed(0)}%</span> WR
                  </span>
                  <StatusPill status={r.status} />
                  <span className="text-white/30 min-w-[44px] text-right">{fmtTimeAgo(r.finished_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {(!pending || pending.length === 0) && (!recent || recent.length === 0) && (
        <div className="text-[11px] text-white/45 leading-relaxed pt-1">
          AutoPilot is watching. Compares run automatically when an instrument hits {thresholds.min_rate_pct}% shadow agreement with ≥{thresholds.min_samples} signals/24h. {last_run ? `Last scan: ${fmtTimeAgo(last_run)}.` : "Waiting for first qualifying instrument."}
        </div>
      )}
    </motion.section>
  );
};

export default AutoPilot;
