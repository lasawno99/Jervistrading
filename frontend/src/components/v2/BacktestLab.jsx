import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Play, Beaker, Loader2, TrendingUp, TrendingDown } from "lucide-react";
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

const RunRow = ({ run }) => {
  const wr = run.win_rate ?? 0;
  const pl = run.total_pl_pct ?? 0;
  const exp = run.expectancy ?? 0;
  const wrColor = wr >= 40 ? "var(--up)" : wr >= 25 ? "var(--warn)" : "var(--down)";
  const plColor = pl >= 0 ? "var(--up)" : "var(--down)";
  const expColor = exp >= 0 ? "var(--up)" : "var(--down)";
  return (
    <div
      className="grid grid-cols-12 gap-2 items-center px-3 py-2 rounded-lg text-[11px]"
      style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.05)" }}
      data-testid={`backtest-run-${run.run_id}`}
    >
      <div className="col-span-3 font-semibold text-white/90 truncate" title={run.symbol}>
        {run.symbol}
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
          runs.map((r) => <RunRow key={r.run_id} run={r} />)
        )}
      </div>

      <div className="mt-3 text-[10px] text-white/40 leading-relaxed">
        <span className="text-white/55 font-medium">⚠ Caveats:</span> Backtest uses a deterministic Kronos surrogate
        (the live workers use the real Kronos NN). Smart mode adds a 1-call-per-signal Claude verdict instead of
        the full 7-agent debate. Past performance ≠ future performance.
      </div>
    </motion.section>
  );
};

export default BacktestLab;
