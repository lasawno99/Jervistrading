import React, { useEffect, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Wallet } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const BotPositionsPanel = ({ delay = 0, refreshKey = 0 }) => {
  const [data, setData] = useState({ equity: 0, cash: 0, total_pl: 0, total_pl_pct: 0, positions: [] });

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/bot/positions`);
        if (alive) setData(r.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 4000);
    return () => { alive = false; clearInterval(t); };
  }, [refreshKey]);

  const plUp = data.total_pl >= 0;

  return (
    <Panel title="BOT · ACCOUNT" subtitle="paper" icon={Wallet} delay={delay} testId="panel-bot-positions">
      <div className="space-y-3">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">equity</div>
            <div className="font-display text-2xl text-white glow-cyan" data-testid="bot-equity">
              ${data.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">P/L</div>
            <div
              className="font-display text-sm"
              style={{ color: plUp ? "#27C93F" : "#FF5F56" }}
              data-testid="bot-pl"
            >
              {plUp ? "▲" : "▼"} ${Math.abs(data.total_pl).toFixed(2)} ({data.total_pl_pct.toFixed(2)}%)
            </div>
          </div>
        </div>
        <div className="text-[10px] tracking-[0.2em] uppercase text-[#8BABC6]">
          cash <span className="text-white/80">${data.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>

        <div className="border-t border-[#00F0FF]/15 pt-2">
          <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6] mb-1">
            positions ({data.positions.length})
          </div>
          {data.positions.length === 0 ? (
            <div className="text-[11px] italic text-[#8BABC6]">// flat. waiting for signal_</div>
          ) : (
            <div className="space-y-1.5 jv-scroll overflow-y-auto" style={{ maxHeight: 160 }}>
              {data.positions.map((p) => (
                <div key={p.symbol} className="flex justify-between text-[11px]" data-testid={`pos-${p.symbol}`}>
                  <span className="text-white">{p.symbol} <span className="text-[#8BABC6]">×{p.qty}</span></span>
                  <span style={{ color: p.pl >= 0 ? "#27C93F" : "#FF5F56" }}>
                    {p.pl >= 0 ? "+" : ""}${p.pl.toFixed(2)} ({p.pl_pct.toFixed(2)}%)
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
};

export default BotPositionsPanel;
