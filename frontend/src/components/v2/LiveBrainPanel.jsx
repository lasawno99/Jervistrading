/**
 * LiveBrainPanel — live observability into the 3-pod ensemble.
 *
 * Shows what Pod A (Tauric+Kronos), Pod B (Mean-Reversion), and Pod C (Momentum/Breakout)
 * are voting on each tracked instrument RIGHT NOW. Backend runs them every 5min on
 * yfinance bars; this panel just renders the latest votes + 24h agreement rate.
 *
 * Pure observability — workers untouched. This is the live evidence we need before
 * promoting Pod B/C to paper trading.
 */
import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Brain, Activity, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtTimeAgo = (iso) => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
};

const ActionPill = ({ action }) => {
  const config = action === "LONG"
    ? { bg: "rgba(34,197,94,0.14)", border: "rgba(34,197,94,0.40)", fg: "var(--up)" }
    : action === "SHORT"
    ? { bg: "rgba(239,68,68,0.14)", border: "rgba(239,68,68,0.40)", fg: "var(--down)" }
    : { bg: "rgba(255,255,255,0.04)", border: "rgba(255,255,255,0.10)", fg: "rgba(255,255,255,0.45)" };
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[9px] font-semibold tracking-wide"
      style={{ background: config.bg, border: `1px solid ${config.border}`, color: config.fg, minWidth: 38, textAlign: "center", display: "inline-block" }}
    >
      {action === "LONG" ? "↑ L" : action === "SHORT" ? "↓ S" : "—"}
    </span>
  );
};

const InstrumentRow = ({ vote, agreement }) => {
  const ens = vote?.ensemble;
  const pods = vote?.pods;
  const symbol = vote?.symbol;
  const agreementRate = agreement?.[symbol]?.agreement_rate_pct;
  const totalActions = agreement?.[symbol]?.total;
  const ensAction = ens?.action || "HOLD";
  const rowGlow = ensAction === "LONG" ? "rgba(34,197,94,0.04)" :
                  ensAction === "SHORT" ? "rgba(239,68,68,0.04)" :
                  "rgba(255,255,255,0.015)";
  return (
    <div
      className="grid grid-cols-12 gap-1 px-2 py-2 rounded-lg items-center text-[11px]"
      style={{ background: rowGlow, border: "1px solid rgba(255,255,255,0.04)" }}
      data-testid={`brain-row-${symbol}`}
    >
      <div className="col-span-2 font-semibold text-white/90 truncate">{symbol}</div>
      <div className="col-span-2 tabular text-white/55 text-[10px]">
        {vote?.last_close ? Number(vote.last_close).toFixed(symbol?.includes("USD") && !symbol.startsWith("BTC") && !symbol.startsWith("ETH") && symbol.length < 10 ? 4 : 2) : "—"}
      </div>
      <div className="col-span-4 flex items-center gap-1.5">
        <ActionPill action={pods?.A?.action || "HOLD"} />
        <ActionPill action={pods?.B?.action || "HOLD"} />
        <ActionPill action={pods?.C?.action || "HOLD"} />
      </div>
      <div className="col-span-2 flex items-center justify-center">
        <span
          className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wide"
          style={{
            background: ensAction === "LONG" ? "rgba(34,197,94,0.20)" :
                        ensAction === "SHORT" ? "rgba(239,68,68,0.20)" :
                        "rgba(255,255,255,0.05)",
            color: ensAction === "LONG" ? "var(--up)" :
                   ensAction === "SHORT" ? "var(--down)" :
                   "rgba(255,255,255,0.45)",
          }}
        >
          {ensAction}
        </span>
      </div>
      <div className="col-span-1 text-right text-[10px] text-white/45 tabular">
        {totalActions > 0
          ? <><strong className="text-white/85">{agreementRate?.toFixed(0) ?? 0}%</strong><span className="text-white/30"> /24h</span></>
          : "—"}
      </div>
      <div className="col-span-1 text-right text-[10px] text-white/45 tabular" title={vote?.ts}>
        {fmtTimeAgo(vote?.ts)}
      </div>
    </div>
  );
};

export const LiveBrainPanel = ({ delay = 0.1 }) => {
  const [latest, setLatest] = useState(null);
  const [agreement, setAgreement] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [a, b] = await Promise.all([
          axios.get(`${API}/shadow/latest`, { timeout: 10000 }),
          axios.get(`${API}/shadow/agreement?hours=24`, { timeout: 10000 }),
        ]);
        if (!alive) return;
        setLatest(a.data);
        setAgreement(b.data?.by_symbol || {});
        setLoaded(true);
      } catch {}
    };
    load();
    const t = setInterval(load, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // Headline tally — across all symbols right now, how many longs/shorts/holds?
  const headline = useMemo(() => {
    const v = latest?.votes || [];
    const tally = { LONG: 0, SHORT: 0, HOLD: 0 };
    v.forEach((row) => {
      const a = row?.ensemble?.action;
      if (a === "LONG" || a === "SHORT" || a === "HOLD") tally[a] += 1;
    });
    return tally;
  }, [latest]);

  const total24h = useMemo(() => {
    if (!agreement) return { actionable: 0, total: 0 };
    let actionable = 0, total = 0;
    Object.values(agreement).forEach((d) => {
      actionable += (d.LONG || 0) + (d.SHORT || 0);
      total += d.total || 0;
    });
    return { actionable, total };
  }, [agreement]);

  return (
    <motion.section
      className="card p-5"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="live-brain-panel"
    >
      <header className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(155,123,255,0.15)", color: "var(--accent-2)" }}>
            <Brain size={15} />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold tracking-tight leading-none">Live Brain</h3>
            <div className="text-[11px] text-white/45 mt-0.5">
              3-pod ensemble · what the system is thinking right now
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {!loaded ? (
            <Loader2 size={12} className="animate-spin text-white/50" />
          ) : (
            <>
              <div className="flex items-center gap-2 text-[10px]">
                <span className="px-1.5 py-0.5 rounded font-semibold tabular"
                      style={{ background: "rgba(34,197,94,0.16)", color: "var(--up)" }}>
                  ↑ {headline.LONG}
                </span>
                <span className="px-1.5 py-0.5 rounded font-semibold tabular"
                      style={{ background: "rgba(239,68,68,0.16)", color: "var(--down)" }}>
                  ↓ {headline.SHORT}
                </span>
                <span className="px-1.5 py-0.5 rounded font-semibold tabular"
                      style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.55)" }}>
                  — {headline.HOLD}
                </span>
              </div>
              <div className="flex items-center gap-1 text-[10px] text-white/45">
                <Activity size={10} style={{ color: "var(--up)" }} />
                <span className="tabular">
                  <strong className="text-white/85">{total24h.actionable}</strong>/{total24h.total} signals/24h
                </span>
              </div>
            </>
          )}
        </div>
      </header>

      <div className="grid grid-cols-12 gap-1 px-2 pb-1 text-[9px] tracking-[0.10em] uppercase text-white/40">
        <div className="col-span-2">Symbol</div>
        <div className="col-span-2">Last</div>
        <div className="col-span-4">A · B · C</div>
        <div className="col-span-2 text-center">Ensemble</div>
        <div className="col-span-1 text-right">Fire/24h</div>
        <div className="col-span-1 text-right">Age</div>
      </div>

      <div className="space-y-1" data-testid="brain-rows">
        {(latest?.votes || []).map((v) => (
          <InstrumentRow key={v.symbol} vote={v} agreement={agreement} />
        ))}
        {loaded && (latest?.votes || []).length === 0 && (
          <div className="text-[11px] text-white/45 text-center py-4">
            Shadow loop just started — votes will appear within 5 min.
          </div>
        )}
      </div>

      <div className="mt-3 text-[10px] text-white/40 leading-relaxed">
        <strong className="text-white/55">How to read:</strong> Pod A = Tauric+Kronos (your live strategy).
        Pod B = Mean-Reversion (calm markets). Pod C = Momentum/Breakout (volatile markets).
        Ensemble = ≥2 of 3 must agree. <strong className="text-white/65">Fire/24h</strong> tells you how often
        the ensemble actually triggered an entry (rest were HOLD).
        Refreshes every 30s · backend re-evaluates every 5 min.
      </div>
    </motion.section>
  );
};

export default LiveBrainPanel;
