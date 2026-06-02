import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Beaker, Loader2, TrendingUp, TrendingDown, Sliders, ChevronRight, X, Award } from "lucide-react";
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

  const runTune = async () => {
    setStatus("queued"); setResult(null);
    try {
      const r = await axios.post(`${API}/backtest/tune`, { symbol, period, interval: "1h", base_units: 1000 }, { timeout: 15000 });
      const id = r.data.tune_id;
      setTuneId(id);
      setStatus("running");
      // poll
      for (let i = 0; i < 60; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const a = await axios.get(`${API}/backtest/tunes/active`, { timeout: 5000 });
        const s = a.data.runs?.[id]?.status;
        if (s === "done") {
          const detail = await axios.get(`${API}/backtest/tunes/${id}`, { timeout: 10000 });
          setResult(detail.data);
          setStatus("done");
          break;
        }
        if (s === "error") {
          setStatus("error");
          toast.error("Tune failed", { description: a.data.runs[id]?.error });
          break;
        }
      }
    } catch (e) {
      setStatus("error");
      toast.error("Tune error", { description: String(e?.message || e) });
    }
  };

  useEffect(() => {
    if (open && status === "idle") runTune();
    if (!open) { setStatus("idle"); setResult(null); setTuneId(null); }
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

export const BacktestLab = ({ delay = 0.15 }) => {
  const [symbol, setSymbol] = useState("BTC/USD");
  const [period, setPeriod] = useState("180d");
  const [interval, setInterval_] = useState("1h");
  const [useTauric, setUseTauric] = useState(false);
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState([]);
  const [drilldown, setDrilldown] = useState(null);
  const [tuneOpen, setTuneOpen] = useState(false);

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
    </motion.section>
  );
};

export default BacktestLab;
