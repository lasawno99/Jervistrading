import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Beaker, Loader2, TrendingUp, TrendingDown, Sliders, ChevronRight, X, Award, Send, Check, GitCompareArrows, Layers, Lock, Unlock, Copy } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SYMBOL_PRESETS = [
  { label: "EUR_USD (Forex)", value: "EUR_USD" },
  { label: "BTC/USD (Crypto)", value: "BTC/USD" },
  { label: "ETH/USD (Crypto)", value: "ETH/USD" },
  { label: "NVDA (Stocks)", value: "NVDA" },
  { label: "TSLA (Stocks)", value: "TSLA" },
];

const PERIOD_PRESETS = [
  { label: "60 days", value: "60d" },
  { label: "180 days", value: "180d" },
  { label: "1 year", value: "1y" },
  { label: "2 years", value: "2y" },
];

const fmtPct = (v) => (Number.isFinite(v) ? `${v.toFixed(1)}%` : "—");
const fmtSignedPct = (v) =>
  Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—";

const RunRow = ({ run, onOpen }) => {
  const wr = run.win_rate ?? 0;
  const pl = run.total_pl_pct ?? 0;
  const exp = run.expectancy ?? 0;
  const wrColor = wr >= 40 ? "var(--up)" : wr >= 25 ? "var(--warn)" : "var(--down)";
  const plColor = pl >= 0 ? "var(--up)" : "var(--down)";
  const expColor = exp >= 0 ? "var(--up)" : "var(--down)";
  return (
    <button
      onClick={() => onOpen?.(run)}
      className="w-full grid grid-cols-12 gap-2 items-center px-3 py-2 rounded-lg text-[11px] text-left hover:bg-white/[0.04] transition"
      style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.05)" }}
      data-testid={`backtest-row-${run.run_id}`}
    >
      <div className="col-span-3 font-semibold text-white/90 truncate flex items-center gap-1" title={run.symbol}>
        {run.symbol}
        <ChevronRight size={9} className="text-white/30" />
      </div>
      <div className="col-span-2 text-white/55 tabular text-right">{run.total_trades ?? 0} trades</div>
      <div className="col-span-2 tabular text-right font-semibold" style={{ color: wrColor }}>{fmtPct(wr)}</div>
      <div className="col-span-2 tabular text-right font-semibold" style={{ color: plColor }}>
        {pl >= 0 ? <TrendingUp size={9} className="inline mr-0.5" /> : <TrendingDown size={9} className="inline mr-0.5" />}
        {fmtSignedPct(pl)}
      </div>
      <div className="col-span-2 tabular text-right font-medium" style={{ color: expColor }}>
        {fmtSignedPct(exp)}
      </div>
      <div className="col-span-1 text-white/35 tabular text-right">{(run.elapsed_seconds || 0).toFixed(0)}s</div>
    </button>
  );
};

// --- Run drill-down modal: shows trade ledger ---
const RunDrilldownModal = ({ run, onClose }) => {
  const trades = run?.trades || [];
  const wins = trades.filter((t) => t.pl_pct > 0);
  return (
    <AnimatePresence>
      {run && (
        <motion.div
          className="fixed inset-0 z-[80] flex items-center justify-center p-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          style={{ background: "rgba(8,8,12,0.65)", backdropFilter: "blur(14px)" }}
          onClick={onClose}
          data-testid="backtest-drilldown"
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-2xl rounded-2xl p-5 max-h-[85vh] overflow-y-auto"
            style={{ background: "rgba(18,18,26,0.96)", border: "1px solid var(--border-hi)" }}
            initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 30, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <header className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-[15px] font-semibold tracking-tight">{run.symbol} · Trade Ledger</h3>
                <div className="text-[11px] text-white/45 mt-0.5">
                  {trades.length} trades · {wins.length} wins ({((wins.length / Math.max(1, trades.length)) * 100).toFixed(1)}% WR) · {fmtSignedPct(run.total_pl_pct)} cumulative
                </div>
              </div>
              <button onClick={onClose} className="w-7 h-7 rounded-lg flex items-center justify-center text-white/55 hover:text-white" aria-label="Close">
                <X size={16} />
              </button>
            </header>
            {run.params && (
              <div className="text-[10px] text-white/45 mb-3">
                Params: Tauric≥{run.params.tauric_floor} · Up≥{run.params.upside_high}/≤{run.params.upside_low} · ATR×{run.params.atr_mult} · R:R {run.params.rr_base}
              </div>
            )}
            <div className="grid grid-cols-12 gap-1 px-2 pb-1 text-[9px] tracking-[0.10em] uppercase text-white/40">
              <div className="col-span-1">#</div>
              <div className="col-span-3">Entry</div>
              <div className="col-span-2">Side</div>
              <div className="col-span-2 text-right">Entry $</div>
              <div className="col-span-2 text-right">Exit $</div>
              <div className="col-span-1 text-center">Why</div>
              <div className="col-span-1 text-right">P/L</div>
            </div>
            <div className="space-y-1">
              {trades.map((t, i) => (
                <div key={i} className="grid grid-cols-12 gap-1 px-2 py-1.5 rounded text-[11px] tabular"
                     style={{ background: t.pl_pct > 0 ? "rgba(34,197,94,0.06)" : "rgba(239,68,68,0.06)" }}>
                  <div className="col-span-1 text-white/55">{i + 1}</div>
                  <div className="col-span-3 text-white/65 truncate text-[10px]" title={t.entry_time}>
                    {String(t.entry_time).split(" ")[0]}
                  </div>
                  <div className="col-span-2" style={{ color: t.side === "LONG" ? "var(--up)" : "var(--down)" }}>
                    {t.side === "LONG" ? "↑ LONG" : "↓ SHORT"}
                  </div>
                  <div className="col-span-2 text-right text-white/75">{Number(t.entry_price).toFixed(4)}</div>
                  <div className="col-span-2 text-right text-white/75">{Number(t.exit_price).toFixed(4)}</div>
                  <div className="col-span-1 text-center text-[9px] uppercase text-white/55">{t.exit_reason}</div>
                  <div className="col-span-1 text-right font-semibold"
                       style={{ color: t.pl_pct > 0 ? "var(--up)" : "var(--down)" }}>
                    {fmtSignedPct(t.pl_pct)}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

// --- Auto-tune sheet ---
const TuneSheet = ({ open, symbol, period, onClose }) => {
  const [tuneId, setTuneId] = useState(null);
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  const applyConfig = async () => {
    if (!result?.best) return;
    setApplying(true);
    try {
      await axios.post(`${API}/instrument-configs/apply`, {
        symbol,
        params: result.best.params,
        source_tune_id: tuneId,
        notes: `Auto-tuned ${period} window — WR=${result.best.win_rate}% PL=${result.best.total_pl_pct}%`,
      }, { timeout: 10000 });
      setApplied(true);
      toast.success(`Applied to live workers · ${symbol}`, {
        description: "Next worker cycle will use these params.",
      });
    } catch (e) {
      toast.error("Apply failed", { description: String(e?.response?.data?.detail || e?.message || e) });
    } finally {
      setApplying(false);
    }
  };

  const cancelRef = React.useRef({ cancelled: false });

  const runTune = async () => {
    cancelRef.current = { cancelled: false };
    setStatus("queued"); setResult(null);
    let id;
    try {
      const r = await axios.post(`${API}/backtest/tune`, { symbol, period, interval: "1h", base_units: 1000 }, { timeout: 15000 });
      id = r.data.tune_id;
      if (!id) throw new Error("Backend returned no tune_id");
      setTuneId(id);
      setStatus("running");
    } catch (e) {
      if (!cancelRef.current.cancelled) {
        setStatus("error");
        toast.error("Tune failed to start", { description: String(e?.response?.data?.detail || e?.message || e) });
      }
      return;
    }

    // Poll the PERSISTED endpoint — once the doc lands in MongoDB we know we're done.
    // 60 attempts × 3s = 180s max wait. Symbol/period heavy combos may still need more.
    for (let i = 0; i < 60; i++) {
      if (cancelRef.current.cancelled) return;
      await new Promise((res) => setTimeout(res, 3000));
      if (cancelRef.current.cancelled) return;
      try {
        const detail = await axios.get(`${API}/backtest/tunes/${id}`, { timeout: 10000 });
        // Result is persisted only after run completes
        if (detail.data?.best) {
          setResult(detail.data);
          setStatus("done");
          return;
        }
      } catch (e) {
        if (e?.response?.status === 404) {
          // Not yet persisted — keep waiting
          continue;
        }
        // Transient network blip — keep trying unless we've burned our budget
      }
    }
    if (!cancelRef.current.cancelled) {
      setStatus("error");
      toast.error("Tune timed out", { description: "Took longer than 3 minutes. Try a shorter period." });
    }
  };

  useEffect(() => {
    if (open && status === "idle") runTune();
    if (!open) {
      cancelRef.current.cancelled = true;
      setStatus("idle"); setResult(null); setTuneId(null); setApplied(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[80] flex items-center justify-center p-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          style={{ background: "rgba(8,8,12,0.65)", backdropFilter: "blur(14px)" }}
          onClick={onClose}
          data-testid="tune-sheet"
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-2xl rounded-2xl p-5 max-h-[85vh] overflow-y-auto"
            style={{ background: "rgba(18,18,26,0.96)", border: "1px solid var(--border-hi)" }}
            initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 30, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <header className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                     style={{ background: "rgba(245,158,11,0.16)", color: "var(--warn)" }}>
                  <Sliders size={15} />
                </div>
                <div>
                  <h3 className="text-[15px] font-semibold tracking-tight leading-none">Auto-Tune · {symbol}</h3>
                  <div className="text-[11px] text-white/45 mt-0.5">
                    Grid search over 54 (Tauric, Upside, ATR, R:R) combos · {period} window
                  </div>
                </div>
              </div>
              <button onClick={onClose} className="w-7 h-7 rounded-lg flex items-center justify-center text-white/55 hover:text-white" aria-label="Close">
                <X size={16} />
              </button>
            </header>

            {status !== "done" && (
              <div className="py-8 text-center">
                <Loader2 size={24} className="animate-spin inline-block text-white/55 mb-3" />
                <div className="text-[12px] text-white/55">
                  {status === "queued" && "Queueing…"}
                  {status === "running" && "Running 54 backtests in parallel — ~30-60s…"}
                  {status === "error" && "Tune failed. Try again."}
                </div>
              </div>
            )}

            {status === "done" && result && (
              <>
                <div className="rounded-xl p-4 mb-3"
                     style={{ background: "linear-gradient(135deg, rgba(34,197,94,0.16), rgba(155,123,255,0.12))",
                              border: "1px solid rgba(34,197,94,0.3)" }}
                     data-testid="tune-best">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.12em] text-white/55 mb-1">
                    <Award size={11} style={{ color: "var(--up)" }} /> Best Config Found
                  </div>
                  <div className="grid grid-cols-2 gap-3 mt-2">
                    <div>
                      <div className="text-[9px] uppercase text-white/40">Win Rate</div>
                      <div className="text-[20px] font-semibold tabular" style={{ color: "var(--up)" }}>
                        {fmtPct(result.best.win_rate)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] uppercase text-white/40">Total P/L</div>
                      <div className="text-[20px] font-semibold tabular" style={{ color: "var(--up)" }}>
                        {fmtSignedPct(result.best.total_pl_pct)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] uppercase text-white/40">Expectancy</div>
                      <div className="text-[16px] font-semibold tabular" style={{ color: "var(--up)" }}>
                        {fmtSignedPct(result.best.expectancy)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[9px] uppercase text-white/40">Max DD</div>
                      <div className="text-[16px] font-semibold tabular text-white/85">
                        {fmtPct(result.best.max_drawdown_pct)}
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 pt-3 border-t border-white/10 text-[11px] text-white/75">
                    <strong className="text-white">Tauric ≥{result.best.params.tauric_floor}</strong>
                    {" · "}<strong className="text-white">Upside ≥{result.best.params.upside_high} / ≤{result.best.params.upside_low}</strong>
                    {" · "}<strong className="text-white">ATR × {result.best.params.atr_mult}</strong>
                    {" · "}<strong className="text-white">R:R {result.best.params.rr_base}</strong>
                  </div>
                  <div className="mt-2 text-[10px] text-white/45">
                    {result.best.total_trades} trades over {result.combos_tested} configs tested in {result.elapsed_seconds}s.
                  </div>
                  <button
                    onClick={applyConfig}
                    disabled={applying || applied}
                    className="mt-3 w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-semibold transition disabled:opacity-70"
                    style={{
                      background: applied
                        ? "rgba(34,197,94,0.20)"
                        : "linear-gradient(135deg, var(--up), #16a34a)",
                      color: "#fff",
                      border: applied ? "1px solid rgba(34,197,94,0.45)" : "none",
                      boxShadow: applied ? "none" : "0 6px 14px rgba(34,197,94,0.35)",
                    }}
                    data-testid="tune-apply-button"
                  >
                    {applying && <Loader2 size={13} className="animate-spin" />}
                    {!applying && applied && <Check size={13} />}
                    {!applying && !applied && <Send size={13} />}
                    {applying ? "Applying…" : applied ? "Applied · workers will use next cycle" : "Apply to Live Workers"}
                  </button>
                </div>

                <div className="text-[10px] tracking-[0.12em] uppercase text-white/40 mb-2">Top 10</div>
                <div className="grid grid-cols-12 gap-1 px-2 pb-1 text-[9px] tracking-[0.10em] uppercase text-white/40">
                  <div className="col-span-4">Config</div>
                  <div className="col-span-2 text-right">Trades</div>
                  <div className="col-span-2 text-right">WR</div>
                  <div className="col-span-2 text-right">P/L</div>
                  <div className="col-span-2 text-right">Score</div>
                </div>
                <div className="space-y-1">
                  {(result.results || []).slice(0, 10).map((r, i) => {
                    const p = r.params;
                    return (
                      <div key={i} className="grid grid-cols-12 gap-1 px-2 py-1.5 rounded text-[10px] tabular"
                           style={{ background: i === 0 ? "rgba(34,197,94,0.08)" : "rgba(255,255,255,0.02)" }}>
                        <div className="col-span-4 text-white/75">T{p.tauric_floor} · U{p.upside_high} · ATR{p.atr_mult} · RR{p.rr_base}</div>
                        <div className="col-span-2 text-right text-white/55">{r.total_trades}</div>
                        <div className="col-span-2 text-right" style={{ color: r.win_rate >= 40 ? "var(--up)" : "var(--warn)" }}>{fmtPct(r.win_rate)}</div>
                        <div className="col-span-2 text-right" style={{ color: r.total_pl_pct >= 0 ? "var(--up)" : "var(--down)" }}>{fmtSignedPct(r.total_pl_pct)}</div>
                        <div className="col-span-2 text-right text-white/85">{r.score.toFixed(2)}</div>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-4 text-[10px] text-white/45 leading-relaxed">
                  <strong>How to use:</strong> the best config above is what you'd set as Railway env vars (or in synth.py) for this symbol.
                  Different symbols often want different configs — re-run for each. Past results ≠ future.
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

// --- Compare A vs Ensemble sheet (one-tap head-to-head + promote) ---
const MetricCell = ({ label, single, ensemble, fmt = (v) => v, betterIfHigher = true }) => {
  const sNum = Number.isFinite(single) ? single : 0;
  const eNum = Number.isFinite(ensemble) ? ensemble : 0;
  const better = betterIfHigher ? eNum > sNum : eNum < sNum;
  const color = (eNum === sNum) ? "var(--text-2)" : better ? "var(--up)" : "var(--down)";
  return (
    <div className="grid grid-cols-3 gap-2 px-2 py-1.5 rounded text-[11px] tabular items-center"
         style={{ background: "rgba(255,255,255,0.025)" }}>
      <div className="text-white/55 uppercase tracking-[0.08em] text-[9px]">{label}</div>
      <div className="text-right text-white/75">{fmt(sNum)}</div>
      <div className="text-right font-semibold" style={{ color }}>{fmt(eNum)}</div>
    </div>
  );
};

const GateLight = ({ ok, label }) => (
  <div className="flex items-center gap-1.5 text-[10px]">
    <span
      className="w-2 h-2 rounded-full"
      style={{
        background: ok ? "var(--up)" : "var(--down)",
        boxShadow: ok ? "0 0 8px rgba(34,197,94,0.6)" : "none",
      }}
    />
    <span className="text-white/65">{label}</span>
  </div>
);

const CompareSheet = ({ open, symbol, period, interval, onClose }) => {
  const [status, setStatus] = useState("idle"); // idle|running|done|error
  const [result, setResult] = useState(null);
  const [promoting, setPromoting] = useState(false);
  const [promoted, setPromoted] = useState(false);
  const cancelRef = React.useRef({ cancelled: false });

  useEffect(() => {
    if (open) { setStatus("idle"); setResult(null); setPromoted(false); }
    return () => { cancelRef.current.cancelled = true; };
  }, [open]);

  const runCompare = async () => {
    cancelRef.current = { cancelled: false };
    setStatus("running"); setResult(null); setPromoted(false);
    let cmpId;
    try {
      const r = await axios.post(`${API}/backtest/ensemble/compare`, {
        symbol, period, interval, base_units: 1000,
      }, { timeout: 15000 });
      cmpId = r.data.compare_id;
      if (!cmpId) throw new Error("No compare_id");
    } catch (e) {
      setStatus("error");
      toast.error("Compare failed to start", { description: String(e?.response?.data?.detail || e?.message || e) });
      return;
    }
    // Poll persisted endpoint
    for (let i = 0; i < 60; i++) {
      if (cancelRef.current.cancelled) return;
      await new Promise((res) => setTimeout(res, 3000));
      if (cancelRef.current.cancelled) return;
      try {
        const detail = await axios.get(`${API}/backtest/ensemble/compares/${cmpId}`, { timeout: 10000 });
        if (detail.data?.single_pod && detail.data?.ensemble) {
          setResult(detail.data);
          setStatus("done");
          return;
        }
      } catch (e) {
        if (e?.response?.status !== 404) {
          setStatus("error");
          toast.error("Compare poll failed", { description: String(e?.message || e) });
          return;
        }
      }
    }
    setStatus("error");
    toast.error("Compare timed out", { description: "Try a shorter period." });
  };

  const promote = async () => {
    if (!result?.promote_to_paper || !result?.request) return;
    setPromoting(true);
    try {
      await axios.post(`${API}/instrument-configs/apply`, {
        symbol,
        params: {
          tauric_floor: result.request.tauric_floor,
          upside_high: result.request.upside_high,
          upside_low: result.request.upside_low,
          atr_mult: result.request.atr_mult,
          rr_base: result.request.rr_base,
        },
        notes: `Promoted via ensemble compare (${period}/${interval}) · WR ${result.ensemble.win_rate}% PF ${result.ensemble.profit_factor}`,
      }, { timeout: 10000 });
      setPromoted(true);
      toast.success(`Promoted ${symbol} to live workers`, {
        description: "Workers will pick up these params on next cycle.",
      });
    } catch (e) {
      toast.error("Promote failed", { description: String(e?.response?.data?.detail || e?.message || e) });
    } finally {
      setPromoting(false);
    }
  };

  const fmtPct1 = (v) => (Number.isFinite(v) ? `${v.toFixed(1)}%` : "—");
  const fmtNum3 = (v) => (Number.isFinite(v) ? v.toFixed(3) : "—");
  const fmtSigned1 = (v) => (Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—");

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[80] flex items-center justify-center p-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          style={{ background: "rgba(8,8,12,0.65)", backdropFilter: "blur(14px)" }}
          onClick={() => { cancelRef.current.cancelled = true; onClose?.(); }}
          data-testid="backtest-compare-sheet"
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-xl rounded-2xl p-5 max-h-[88vh] overflow-y-auto"
            style={{ background: "rgba(18,18,26,0.96)", border: "1px solid var(--border-hi)" }}
            initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 30, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <header className="flex items-start justify-between mb-3 gap-2">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                     style={{ background: "rgba(155,123,255,0.15)", color: "var(--accent-2)" }}>
                  <GitCompareArrows size={15} />
                </div>
                <div>
                  <h3 className="text-[15px] font-semibold tracking-tight leading-none">
                    Pod A vs 3-Pod Ensemble
                  </h3>
                  <div className="text-[10px] text-white/45 mt-1">
                    {symbol} · {period} · {interval} · 2-of-3 unanimous voting
                  </div>
                </div>
              </div>
              <button onClick={() => { cancelRef.current.cancelled = true; onClose?.(); }}
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-white/55 hover:text-white"
                      aria-label="Close">
                <X size={16} />
              </button>
            </header>

            {status === "idle" && (
              <div className="text-center py-6">
                <div className="text-[12px] text-white/65 leading-relaxed mb-4">
                  Runs single-pod (Tauric+Kronos) AND 3-pod ensemble back-to-back on the same
                  data window. Promote-gate clears when ≥3 of 4 metrics improve:
                  <span className="block mt-2 text-[10px] text-white/45">
                    WR↑ · Profit Factor↑ · Sharpe↑ · Max Drawdown↓
                  </span>
                </div>
                <button
                  onClick={runCompare}
                  className="px-5 py-2.5 rounded-lg text-[12px] font-semibold"
                  style={{
                    background: "linear-gradient(135deg, var(--accent-1), var(--accent-2))",
                    color: "#fff",
                    boxShadow: "0 6px 14px rgba(108,141,255,0.35)",
                  }}
                  data-testid="compare-run-button"
                >
                  <Play size={12} className="inline mr-1.5" />
                  Run Head-to-Head
                </button>
              </div>
            )}

            {status === "running" && (
              <div className="flex flex-col items-center py-10">
                <Loader2 size={28} className="animate-spin text-white/65" />
                <div className="text-[12px] text-white/65 mt-3">Running both backtests…</div>
                <div className="text-[10px] text-white/35 mt-1">Up to ~2 min for 180d 1h</div>
              </div>
            )}

            {status === "error" && (
              <div className="text-center py-6">
                <div className="text-[12px] text-white/65 mb-3">Compare failed.</div>
                <button onClick={runCompare}
                        className="px-4 py-2 rounded-lg text-[11px] font-semibold bg-white/10 hover:bg-white/15">
                  Retry
                </button>
              </div>
            )}

            {status === "done" && result && (
              <>
                <div className="grid grid-cols-3 gap-2 px-2 pb-1 text-[9px] tracking-[0.10em] uppercase text-white/40">
                  <div>Metric</div>
                  <div className="text-right">Single (Pod A)</div>
                  <div className="text-right">Ensemble</div>
                </div>
                <div className="space-y-1 mb-3" data-testid="compare-metrics">
                  <MetricCell label="Trades" single={result.single_pod.total_trades} ensemble={result.ensemble.total_trades} fmt={(v) => v} betterIfHigher={true} />
                  <MetricCell label="Win Rate" single={result.single_pod.win_rate} ensemble={result.ensemble.win_rate} fmt={fmtPct1} />
                  <MetricCell label="Net P/L" single={result.single_pod.total_pl_pct} ensemble={result.ensemble.total_pl_pct} fmt={fmtSigned1} />
                  <MetricCell label="Profit Factor" single={result.single_pod.profit_factor} ensemble={result.ensemble.profit_factor} fmt={fmtNum3} />
                  <MetricCell label="Sharpe" single={result.single_pod.sharpe_ratio} ensemble={result.ensemble.sharpe_ratio} fmt={fmtNum3} />
                  <MetricCell label="Max Drawdown" single={result.single_pod.max_drawdown_pct} ensemble={result.ensemble.max_drawdown_pct} fmt={fmtPct1} betterIfHigher={false} />
                </div>

                <div className="rounded-lg p-3 mb-3"
                     style={{
                       background: result.promote_to_paper ? "rgba(34,197,94,0.08)" : "rgba(245,158,11,0.06)",
                       border: `1px solid ${result.promote_to_paper ? "rgba(34,197,94,0.35)" : "rgba(245,158,11,0.30)"}`,
                     }}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] tracking-[0.12em] uppercase text-white/55">Promote Gate</span>
                    <span className="text-[11px] font-semibold"
                          style={{ color: result.promote_to_paper ? "var(--up)" : "var(--warn)" }}>
                      {result.promote_to_paper ? "✓ Cleared (≥3 of 4)" : "✗ Not cleared"}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <GateLight ok={result.promote_gate.win_rate_up} label="Win rate ↑" />
                    <GateLight ok={result.promote_gate.profit_factor_up} label="Profit factor ↑" />
                    <GateLight ok={result.promote_gate.sharpe_up} label="Sharpe ↑" />
                    <GateLight ok={result.promote_gate.drawdown_down} label="Max drawdown ↓" />
                  </div>
                </div>

                <button
                  onClick={promote}
                  disabled={!result.promote_to_paper || promoting || promoted}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-[12px] font-semibold transition disabled:opacity-50"
                  style={{
                    background: promoted ? "rgba(34,197,94,0.20)" :
                                result.promote_to_paper ? "linear-gradient(135deg, var(--up), #16a34a)" :
                                "rgba(255,255,255,0.04)",
                    color: result.promote_to_paper ? "#fff" : "var(--text-2)",
                    border: promoted ? "1px solid rgba(34,197,94,0.45)" : "none",
                    boxShadow: promoted ? "none" :
                               result.promote_to_paper ? "0 6px 14px rgba(34,197,94,0.35)" : "none",
                  }}
                  data-testid="compare-promote-button"
                >
                  {promoting && <Loader2 size={13} className="animate-spin" />}
                  {!promoting && promoted && <Check size={13} />}
                  {!promoting && !promoted && (result.promote_to_paper ? <Send size={13} /> : <Lock size={13} />)}
                  {promoting ? "Promoting…" :
                   promoted ? "Promoted · workers will use these params" :
                   result.promote_to_paper ? "Promote to Live Workers" :
                   "Gate locked — at least 3 of 4 metrics must improve"}
                </button>

                <div className="mt-3 text-[10px] text-white/45 leading-relaxed">
                  Promote writes the validated params to <code className="text-white/65">instrument_configs</code>.
                  Workers poll this on their next cycle and adopt the new floor/upside/ATR/R:R automatically.
                  Pod B & C votes are evaluation-only — they don't run live yet.
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

// --- Scaling readiness panel (5 → 10 instruments gate) ---
const ScalingReadinessPanel = () => {
  const [data, setData] = useState(null);
  const [promoting, setPromoting] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/scaling/readiness`, { timeout: 10000 });
      setData(r.data);
    } catch {}
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  const onPromote = async () => {
    setPromoting(true);
    try {
      const r = await axios.post(`${API}/scaling/promote`, { confirm: true }, { timeout: 10000 });
      toast.success("Scaled to 10 instruments", {
        description: "Copy the Railway env command below and update INSTRUMENTS.",
      });
      setData((d) => ({ ...d, already_promoted: true, promoted_at: r.data.promoted_at }));
    } catch (e) {
      toast.error("Scale failed", { description: String(e?.response?.data?.detail || e?.message || e) });
    } finally {
      setPromoting(false);
    }
  };

  if (!data) return null;
  const { stats, gate, current_instruments, proposed_instruments, scaled_instruments, already_promoted } = data;
  const ready = gate.clear;
  const railwayCmd = `INSTRUMENTS=${scaled_instruments.join(",")}`;

  const copyCmd = async () => {
    try {
      await navigator.clipboard.writeText(railwayCmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Copy failed");
    }
  };

  return (
    <div
      className="mt-4 rounded-xl p-4"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: `1px solid ${ready ? "rgba(34,197,94,0.30)" : "rgba(255,255,255,0.08)"}`,
      }}
      data-testid="scaling-readiness-panel"
    >
      <header className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(34,197,94,0.12)", color: "var(--up)" }}>
            <Layers size={13} />
          </div>
          <div>
            <h4 className="text-[13px] font-semibold tracking-tight leading-none">
              Scale jarvis-synth · 5 → 10 instruments
            </h4>
            <div className="text-[10px] text-white/45 mt-1">
              Gate: ≥{gate.min_trades} closed trades · ≥{gate.min_win_rate}% WR
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-[0.10em] text-white/40">Status</div>
          <div className="text-[12px] font-semibold"
               style={{ color: ready ? "var(--up)" : "var(--warn)" }}>
            {already_promoted ? "✓ Promoted" : ready ? "✓ Ready" : "✗ Locked"}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="rounded-lg p-2.5" style={{ background: "rgba(255,255,255,0.025)" }}>
          <div className="text-[9px] uppercase tracking-[0.10em] text-white/40">Closed Trades</div>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-[16px] font-semibold tabular"
                  style={{ color: gate.trades_ok ? "var(--up)" : "var(--warn)" }}>
              {stats.closed_trades}
            </span>
            <span className="text-[10px] text-white/40">/ {gate.min_trades}</span>
          </div>
        </div>
        <div className="rounded-lg p-2.5" style={{ background: "rgba(255,255,255,0.025)" }}>
          <div className="text-[9px] uppercase tracking-[0.10em] text-white/40">Win Rate</div>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-[16px] font-semibold tabular"
                  style={{ color: gate.wr_ok ? "var(--up)" : "var(--warn)" }}>
              {stats.win_rate.toFixed(1)}%
            </span>
            <span className="text-[10px] text-white/40">/ {gate.min_win_rate}%</span>
          </div>
        </div>
        <div className="rounded-lg p-2.5 flex flex-col justify-center items-center" style={{ background: "rgba(255,255,255,0.025)" }}>
          {ready ? <Unlock size={16} className="text-[var(--up)]" /> : <Lock size={16} className="text-white/35" />}
          <div className="text-[9px] uppercase tracking-[0.10em] mt-1 text-white/40">
            {ready ? "Unlocked" : "Locked"}
          </div>
        </div>
      </div>

      <div className="mb-3">
        <div className="text-[9px] uppercase tracking-[0.10em] text-white/40 mb-1">Current (5)</div>
        <div className="flex flex-wrap gap-1">
          {current_instruments.map((s) => (
            <span key={s} className="text-[10px] px-2 py-0.5 rounded tabular"
                  style={{ background: "rgba(108,141,255,0.10)", color: "var(--accent-1)" }}>
              {s}
            </span>
          ))}
        </div>
        <div className="text-[9px] uppercase tracking-[0.10em] text-white/40 mb-1 mt-2">+ Proposed (5)</div>
        <div className="flex flex-wrap gap-1">
          {proposed_instruments.map((s) => (
            <span key={s} className="text-[10px] px-2 py-0.5 rounded tabular"
                  style={{
                    background: ready ? "rgba(34,197,94,0.10)" : "rgba(255,255,255,0.04)",
                    color: ready ? "var(--up)" : "var(--text-2)",
                  }}>
              {s}
            </span>
          ))}
        </div>
      </div>

      <button
        onClick={onPromote}
        disabled={!ready || promoting || already_promoted}
        className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-semibold transition disabled:opacity-50 mb-2"
        style={{
          background: already_promoted ? "rgba(34,197,94,0.20)" :
                      ready ? "linear-gradient(135deg, var(--up), #16a34a)" :
                      "rgba(255,255,255,0.04)",
          color: ready || already_promoted ? "#fff" : "var(--text-2)",
          border: already_promoted ? "1px solid rgba(34,197,94,0.45)" : "none",
          boxShadow: ready && !already_promoted ? "0 6px 14px rgba(34,197,94,0.35)" : "none",
        }}
        data-testid="scaling-promote-button"
      >
        {promoting && <Loader2 size={13} className="animate-spin" />}
        {!promoting && already_promoted && <Check size={13} />}
        {!promoting && !already_promoted && (ready ? <Send size={13} /> : <Lock size={13} />)}
        {promoting ? "Promoting…" :
         already_promoted ? "Promoted · update Railway INSTRUMENTS below" :
         ready ? "Scale to 10 Instruments" :
         `Locked — need ${Math.max(0, gate.min_trades - stats.closed_trades)} more trades & ${Math.max(0, gate.min_win_rate - stats.win_rate).toFixed(1)}% higher WR`}
      </button>

      {already_promoted && (
        <div className="rounded-lg p-2.5" style={{ background: "rgba(8,8,12,0.55)", border: "1px solid rgba(255,255,255,0.08)" }}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[9px] uppercase tracking-[0.10em] text-white/45">Railway env command</span>
            <button onClick={copyCmd}
                    className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded hover:bg-white/5"
                    data-testid="scaling-copy-env">
              {copied ? <Check size={10} className="text-[var(--up)]" /> : <Copy size={10} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <code className="block text-[10px] text-white/75 break-all leading-relaxed font-mono">
            {railwayCmd}
          </code>
          <div className="text-[9px] text-white/40 mt-1.5">
            Paste this into Railway → jarvis-synth → Variables → INSTRUMENTS, then restart the worker.
          </div>
        </div>
      )}
    </div>
  );
};

export const BacktestLab = ({ delay = 0.15 }) => {
  const [symbol, setSymbol] = useState("BTC/USD");
  const [period, setPeriod] = useState("180d");
  const [interval, setInterval_] = useState("1h");
  const [useTauric, setUseTauric] = useState(false);
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState([]);
  const [drilldown, setDrilldown] = useState(null);
  const [tuneOpen, setTuneOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);

  const openRun = async (run) => {
    try {
      const r = await axios.get(`${API}/backtest/runs/${run.run_id}`, { timeout: 10000 });
      setDrilldown(r.data);
    } catch (e) {
      toast.error("Could not load trade ledger", { description: String(e?.message || e) });
    }
  };

  const loadRuns = async () => {
    try {
      const r = await axios.get(`${API}/backtest/runs?limit=10`, { timeout: 10000 });
      setRuns(r.data.runs || []);
    } catch {}
  };

  useEffect(() => { loadRuns(); }, []);

  const runBacktest = async () => {
    setRunning(true);
    const tid = toast.loading(`Running backtest: ${symbol} · ${period}`);
    try {
      const r = await axios.post(`${API}/backtest/run`, {
        symbol, period, interval, base_units: 1000,
        use_tauric: useTauric, max_llm_calls: 50,
      }, { timeout: 15000 });
      const runId = r.data.run_id;
      // Poll active endpoint up to ~120s
      let attempts = 0;
      while (attempts < 60) {
        await new Promise((res) => setTimeout(res, 2000));
        const a = await axios.get(`${API}/backtest/active`, { timeout: 5000 });
        const status = a.data.runs?.[runId]?.status;
        if (status === "done" || status === "error") {
          if (status === "error") {
            toast.error("Backtest failed", { id: tid, description: a.data.runs?.[runId]?.error });
          } else {
            const ad = a.data.runs[runId];
            toast.success(`${symbol}: ${(ad.win_rate || 0).toFixed(1)}% WR over ${ad.trades || 0} trades`, { id: tid });
          }
          break;
        }
        attempts += 1;
      }
      await loadRuns();
    } catch (e) {
      toast.error("Backtest error", { id: tid, description: String(e?.message || e) });
    } finally {
      setRunning(false);
    }
  };

  return (
    <motion.section
      className="card p-5"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="backtest-lab"
    >
      <header className="flex items-center justify-between gap-2 mb-4 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(155,123,255,0.15)", color: "var(--accent-2)" }}>
            <Beaker size={15} />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold tracking-tight leading-none">Backtest Lab</h3>
            <div className="text-[11px] text-white/40 mt-0.5">
              Replay the live signal pipeline against historical data — validate WR in seconds, not days.
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCompareOpen(true)}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold disabled:opacity-50 transition"
            style={{
              background: "rgba(155,123,255,0.16)",
              color: "var(--accent-2)",
              border: "1px solid rgba(155,123,255,0.32)",
            }}
            data-testid="backtest-compare-button"
            title="Head-to-head: single-pod (Pod A) vs 3-pod ensemble (2-of-3 voting)"
          >
            <GitCompareArrows size={12} />
            Compare A vs Ensemble
          </button>
          <button
            onClick={() => setTuneOpen(true)}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold disabled:opacity-50 transition"
            style={{
              background: "rgba(245,158,11,0.16)",
              color: "var(--warn)",
              border: "1px solid rgba(245,158,11,0.32)",
            }}
            data-testid="backtest-tune-button"
            title="Find the best config for this symbol via grid search"
          >
            <Sliders size={12} />
            Auto-Tune
          </button>
          <button
            onClick={runBacktest}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold disabled:opacity-50 transition"
            style={{
              background: "linear-gradient(135deg, var(--accent-1), var(--accent-2))",
              color: "#fff",
              boxShadow: "0 6px 14px rgba(108,141,255,0.35)",
            }}
            data-testid="backtest-run-button"
          >
            {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            {running ? "Running…" : "Run Backtest"}
          </button>
        </div>
      </header>

      {/* Controls */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        <div>
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/40 mb-1">Symbol</div>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            disabled={running}
            className="w-full px-2 py-1.5 text-[12px] rounded-lg bg-white/5 border border-white/10 text-white"
            data-testid="backtest-symbol"
          >
            {SYMBOL_PRESETS.map((p) => <option key={p.value} value={p.value} style={{ background: "#181820" }}>{p.label}</option>)}
          </select>
        </div>
        <div>
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/40 mb-1">Period</div>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            disabled={running}
            className="w-full px-2 py-1.5 text-[12px] rounded-lg bg-white/5 border border-white/10 text-white"
            data-testid="backtest-period"
          >
            {PERIOD_PRESETS.map((p) => <option key={p.value} value={p.value} style={{ background: "#181820" }}>{p.label}</option>)}
          </select>
        </div>
        <div>
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/40 mb-1">Interval</div>
          <select
            value={interval}
            onChange={(e) => setInterval_(e.target.value)}
            disabled={running}
            className="w-full px-2 py-1.5 text-[12px] rounded-lg bg-white/5 border border-white/10 text-white"
            data-testid="backtest-interval"
          >
            <option value="1h" style={{ background: "#181820" }}>1 hour</option>
            <option value="1d" style={{ background: "#181820" }}>1 day</option>
          </select>
        </div>
        <div>
          <div className="text-[9px] tracking-[0.10em] uppercase text-white/40 mb-1">Mode</div>
          <button
            type="button"
            onClick={() => setUseTauric((v) => !v)}
            disabled={running}
            className="w-full px-2 py-1.5 text-[12px] rounded-lg text-left"
            style={{
              background: useTauric ? "rgba(108,141,255,0.20)" : "rgba(255,255,255,0.05)",
              border: `1px solid ${useTauric ? "var(--accent-1)" : "rgba(255,255,255,0.10)"}`,
              color: useTauric ? "var(--accent-1)" : "rgba(255,255,255,0.85)",
            }}
            data-testid="backtest-tauric-toggle"
          >
            {useTauric ? "🧠 Smart (LLM ≤50)" : "⚡ Fast (deterministic)"}
          </button>
        </div>
      </div>

      {/* Header row */}
      <div className="grid grid-cols-12 gap-2 px-3 pb-1 text-[9px] tracking-[0.10em] uppercase text-white/40">
        <div className="col-span-3">Symbol</div>
        <div className="col-span-2 text-right">Trades</div>
        <div className="col-span-2 text-right">Win Rate</div>
        <div className="col-span-2 text-right">Net P/L</div>
        <div className="col-span-2 text-right">Expectancy</div>
        <div className="col-span-1 text-right">Time</div>
      </div>
      {/* Results */}
      <div className="space-y-1" data-testid="backtest-results">
        {runs.length === 0 ? (
          <div className="text-[11px] text-white/40 text-center py-4">
            No backtests yet. Pick a symbol + period above and hit Run.
          </div>
        ) : (
          runs.map((r) => <RunRow key={r.run_id} run={r} onOpen={openRun} />)
        )}
      </div>

      <div className="mt-3 text-[10px] text-white/40 leading-relaxed">
        <span className="text-white/55 font-medium">⚠ Caveats:</span> Backtest uses a deterministic Kronos surrogate
        (the live workers use the real Kronos NN). Smart mode adds a 1-call-per-signal Claude verdict instead of
        the full 7-agent debate. Past performance ≠ future performance.
      </div>

      <RunDrilldownModal run={drilldown} onClose={() => setDrilldown(null)} />
      <TuneSheet open={tuneOpen} symbol={symbol} period={period} onClose={() => setTuneOpen(false)} />
      <CompareSheet open={compareOpen} symbol={symbol} period={period} interval={interval} onClose={() => setCompareOpen(false)} />

      {/* Instrument scaling readiness — P1 gate (5 → 10 instruments) */}
      <ScalingReadinessPanel />
    </motion.section>
  );
};

export default BacktestLab;
