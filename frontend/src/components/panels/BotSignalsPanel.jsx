import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Radar, Check, X } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_COLOR = {
  pending: "#FFB000",
  executed: "#27C93F",
  skipped: "#8BABC6",
  failed: "#FF5F56",
};

export const BotSignalsPanel = ({ delay = 0, onChange }) => {
  const [signals, setSignals] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/bot/signals?limit=12`);
      setSignals(r.data);
    } catch {}
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 4500);
    return () => clearInterval(t);
  }, [load]);

  const generate = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/bot/signal`);
      await load();
      onChange?.();
    } finally {
      setBusy(false);
    }
  };

  const approve = async (id) => {
    setBusy(true);
    try {
      await axios.post(`${API}/bot/signal/${id}/approve`);
      await load();
      onChange?.();
    } finally {
      setBusy(false);
    }
  };

  const skip = async (id) => {
    setBusy(true);
    try {
      await axios.post(`${API}/bot/signal/${id}/skip`);
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="AI · SIGNALS"
      subtitle={busy ? "working" : "live"}
      icon={Radar}
      delay={delay}
      testId="panel-bot-signals"
    >
      <div className="flex justify-end mb-2">
        <button
          onClick={generate}
          disabled={busy}
          className="text-[10px] tracking-[0.3em] uppercase px-3 py-1 rounded-full border transition-all disabled:opacity-40"
          style={{
            color: "#00F0FF",
            borderColor: "rgba(0,240,255,0.5)",
            background: "rgba(0,240,255,0.08)",
          }}
          data-testid="generate-signal-btn"
        >
          ⚡ generate signal
        </button>
      </div>
      <div className="space-y-2 jv-scroll overflow-y-auto pr-1" style={{ maxHeight: 280 }}>
        {signals.length === 0 && (
          <div className="text-[11px] italic text-[#8BABC6]">
            // no signals yet. tap generate or enable auto-mode_
          </div>
        )}
        {signals.map((s) => {
          const color = s.action === "BUY" ? "#27C93F" : "#FF5F56";
          return (
            <div key={s.id} className="border border-[#00F0FF]/20 rounded-md p-2" data-testid={`signal-${s.id}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="font-display text-xs tracking-[0.2em]" style={{ color }}>
                    {s.action} {s.symbol}
                  </span>
                  <span className="text-[9px] text-[#8BABC6]">
                    {s.qty} @ ${s.price?.toFixed(2)}
                  </span>
                </div>
                <span
                  className="font-display text-[9px] tracking-[0.3em] uppercase"
                  style={{ color: STATUS_COLOR[s.status] || "#8BABC6" }}
                >
                  ● {s.status}
                </span>
              </div>
              <div className="text-[10px] text-[#8BABC6] leading-snug italic mb-2">↳ {s.reason}</div>
              <div className="flex items-center justify-between">
                <span className="text-[9px] text-[#8BABC6]">
                  conv {Math.round((s.conviction || 0) * 100)}% · 24h {s.change_pct >= 0 ? "+" : ""}{s.change_pct?.toFixed(2)}%
                </span>
                {s.status === "pending" && (
                  <div className="flex gap-1">
                    <button
                      onClick={() => approve(s.id)}
                      disabled={busy}
                      className="px-2 py-0.5 rounded border text-[10px] flex items-center gap-1 disabled:opacity-40"
                      style={{ color: "#27C93F", borderColor: "rgba(39,201,63,0.5)", background: "rgba(39,201,63,0.08)" }}
                      data-testid={`approve-${s.id}`}
                    >
                      <Check size={10} /> approve
                    </button>
                    <button
                      onClick={() => skip(s.id)}
                      disabled={busy}
                      className="px-2 py-0.5 rounded border text-[10px] flex items-center gap-1 disabled:opacity-40"
                      style={{ color: "#FF5F56", borderColor: "rgba(255,95,86,0.5)", background: "rgba(255,95,86,0.08)" }}
                      data-testid={`skip-${s.id}`}
                    >
                      <X size={10} /> skip
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
};

export default BotSignalsPanel;
