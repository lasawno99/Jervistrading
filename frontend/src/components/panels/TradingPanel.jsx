import React, { useEffect, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { TrendingUp } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const TradingPanel = ({ delay = 0 }) => {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await axios.get(`${API}/feed/trading`);
        setRows(r.data);
      } catch (e) {
        console.error(e);
      }
    };
    load();
    const t = setInterval(load, 4500);
    return () => clearInterval(t);
  }, []);

  return (
    <Panel
      title="TRADING · STRATEGY"
      subtitle="adaptive"
      icon={TrendingUp}
      delay={delay}
      testId="panel-trading"
    >
      <div className="space-y-2 jv-scroll overflow-y-auto pr-1" style={{ maxHeight: 320 }}>
        {rows.map((r) => {
          const up = r.change >= 0;
          return (
            <div
              key={r.symbol}
              className="flex items-center justify-between py-2 border-b border-[#00F0FF]/10 last:border-0"
              data-testid={`ticker-${r.symbol}`}
            >
              <div>
                <div className="font-display text-sm tracking-wider text-white">
                  {r.symbol}
                </div>
                <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">
                  {r.posture}
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-xs text-white">
                  ${r.price.toLocaleString()}
                </div>
                <div
                  className="font-mono text-[10px]"
                  style={{ color: up ? "#27C93F" : "#FF5F56" }}
                >
                  {up ? "▲" : "▼"} {Math.abs(r.change).toFixed(2)}%
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
};

export default TradingPanel;
