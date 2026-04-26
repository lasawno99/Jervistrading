import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Bot, Send, RotateCcw } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SYMBOLS = ["BTC", "ETH", "OIL", "GOLD", "TSLA", "NVDA"];

export const BotControlPanel = ({ delay = 0, onChange }) => {
  const [status, setStatus] = useState(null);
  const [side, setSide] = useState("buy");
  const [symbol, setSymbol] = useState("BTC");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/bot/status`);
      setStatus(r.data);
    } catch {}
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const toggleAuto = async () => {
    const next = !(status?.telegram?.auto_mode);
    await axios.post(`${API}/bot/auto`, { on: next });
    toast(`auto-mode ${next ? "ON" : "OFF"}`, { description: next ? "AI will scan + post signals every 90s" : "manual mode" });
    load();
  };

  const submitTrade = async (e) => {
    e.preventDefault();
    const q = parseFloat(qty);
    if (!q || q <= 0) {
      toast.error("enter a positive qty");
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/bot/trade`, { symbol, side, qty: q });
      toast.success(`${side.toUpperCase()} ${r.data.trade.qty} ${symbol} @ $${r.data.trade.price.toFixed(2)}`);
      setQty("");
      onChange?.();
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "trade failed");
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!window.confirm("Reset paper account to $100,000 and clear all positions/trades?")) return;
    await axios.post(`${API}/bot/reset`);
    toast.success("account reset");
    onChange?.();
    load();
  };

  const tg = status?.telegram || {};
  const tgConnected = tg.configured && tg.running;

  return (
    <Panel title="BOT · CONTROL" subtitle="24/7" icon={Bot} delay={delay} testId="panel-bot-control" accent="amber">
      <div className="space-y-3">
        {/* Status row */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="border border-[#00F0FF]/15 rounded p-2">
            <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">kimi</div>
            <div className="font-display text-xs mt-0.5" style={{ color: status?.kimi_active ? "#27C93F" : "#FFB000" }}>
              {status?.kimi_active ? "● online" : "○ fallback"}
            </div>
          </div>
          <div className="border border-[#00F0FF]/15 rounded p-2">
            <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">telegram</div>
            <div className="font-display text-xs mt-0.5" style={{ color: tgConnected ? "#27C93F" : "#FF5F56" }}>
              {tgConnected ? "● connected" : tg.configured ? "○ starting" : "○ no token"}
            </div>
          </div>
          <div className="border border-[#00F0FF]/15 rounded p-2">
            <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">auto</div>
            <div className="font-display text-xs mt-0.5" style={{ color: tg.auto_mode ? "#27C93F" : "#8BABC6" }}>
              {tg.auto_mode ? "● running" : "○ paused"}
            </div>
          </div>
        </div>

        <button
          onClick={toggleAuto}
          className="w-full py-2 rounded-md border font-display text-[11px] tracking-[0.3em] uppercase transition-all"
          style={{
            color: tg.auto_mode ? "#FF007F" : "#00F0FF",
            borderColor: tg.auto_mode ? "rgba(255,0,127,0.5)" : "rgba(0,240,255,0.5)",
            background: tg.auto_mode ? "rgba(255,0,127,0.1)" : "rgba(0,240,255,0.08)",
          }}
          data-testid="toggle-auto-btn"
        >
          {tg.auto_mode ? "⏸ pause auto-trader" : "▶ start auto-trader"}
        </button>

        {/* Manual trade */}
        <form onSubmit={submitTrade} className="space-y-2 pt-2 border-t border-[#00F0FF]/15">
          <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">manual order</div>
          <div className="grid grid-cols-2 gap-2">
            <button type="button"
              onClick={() => setSide("buy")}
              className="py-1.5 rounded-md border text-[11px] font-display tracking-[0.2em] uppercase"
              style={{
                color: side === "buy" ? "#050B14" : "#27C93F",
                background: side === "buy" ? "#27C93F" : "transparent",
                borderColor: "#27C93F",
              }}
              data-testid="side-buy"
            >
              buy
            </button>
            <button type="button"
              onClick={() => setSide("sell")}
              className="py-1.5 rounded-md border text-[11px] font-display tracking-[0.2em] uppercase"
              style={{
                color: side === "sell" ? "#050B14" : "#FF5F56",
                background: side === "sell" ? "#FF5F56" : "transparent",
                borderColor: "#FF5F56",
              }}
              data-testid="side-sell"
            >
              sell
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-transparent border border-[#00F0FF]/30 rounded px-2 py-1.5 text-xs text-white outline-none"
              style={{ background: "rgba(5,11,20,0.8)" }}
              data-testid="symbol-select"
            >
              {SYMBOLS.map((s) => <option key={s} value={s} style={{ background: "#050B14" }}>{s}</option>)}
            </select>
            <input
              type="number"
              step="0.0001"
              placeholder="qty"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="bg-transparent border border-[#00F0FF]/30 rounded px-2 py-1.5 text-xs text-white outline-none placeholder:text-[#8BABC6]"
              data-testid="qty-input"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="w-full py-1.5 rounded-md font-display text-[11px] tracking-[0.3em] uppercase disabled:opacity-40 flex items-center justify-center gap-2"
            style={{ background: "#00F0FF", color: "#050B14", boxShadow: "0 0 14px rgba(0,240,255,0.4)" }}
            data-testid="submit-trade-btn"
          >
            <Send size={12} /> place order
          </button>
        </form>

        <button
          onClick={reset}
          className="w-full py-1.5 rounded-md border text-[10px] tracking-[0.3em] uppercase font-display flex items-center justify-center gap-1.5 text-[#8BABC6] border-[#8BABC6]/30 hover:text-white hover:border-white/30 transition-all"
          data-testid="reset-btn"
        >
          <RotateCcw size={10} /> reset paper account
        </button>

        {!tg.configured && (
          <div className="text-[10px] text-[#FFB000] leading-snug border-t border-[#FFB000]/20 pt-2">
            ⚠ Telegram not connected. Add <code className="text-white">TELEGRAM_BOT_TOKEN</code> to <code className="text-white">backend/.env</code> and restart backend.
          </div>
        )}
      </div>
    </Panel>
  );
};

export default BotControlPanel;
