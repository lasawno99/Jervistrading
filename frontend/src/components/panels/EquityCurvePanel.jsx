import React, { useEffect, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Activity } from "lucide-react";
import { LineChart, Line, ResponsiveContainer, YAxis, XAxis, Tooltip } from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const EquityCurvePanel = ({ delay = 0 }) => {
  const [data, setData] = useState([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await axios.get(`${API}/bot/equity-curve?limit=120`);
        setData(
          r.data.map((p, i) => ({
            i,
            equity: p.equity,
            label: new Date(p.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          }))
        );
      } catch {}
    };
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);

  const last = data[data.length - 1]?.equity ?? 0;
  const first = data[0]?.equity ?? last;
  const delta = last - first;
  const deltaPct = first ? (delta / first) * 100 : 0;
  const up = delta >= 0;

  return (
    <Panel title="EQUITY · CURVE" subtitle="30s tick" icon={Activity} delay={delay} testId="panel-equity-curve">
      <div className="space-y-2">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">last</div>
            <div className="font-display text-lg text-white">
              ${last.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">window</div>
            <div className="font-display text-xs" style={{ color: up ? "#27C93F" : "#FF5F56" }}>
              {up ? "▲" : "▼"} {deltaPct.toFixed(3)}%
            </div>
          </div>
        </div>
        <div style={{ width: "100%", height: 110 }}>
          {data.length > 1 ? (
            <ResponsiveContainer>
              <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="cyanLine" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#00F0FF" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#00F0FF" stopOpacity={1} />
                  </linearGradient>
                </defs>
                <YAxis hide domain={["dataMin", "dataMax"]} />
                <XAxis hide dataKey="i" />
                <Tooltip
                  cursor={{ stroke: "#00F0FF", strokeOpacity: 0.3 }}
                  contentStyle={{
                    background: "rgba(5,11,20,0.95)",
                    border: "1px solid rgba(0,240,255,0.4)",
                    borderRadius: 6,
                    fontSize: 10,
                    fontFamily: "IBM Plex Mono",
                    color: "#fff",
                  }}
                  formatter={(v) => [`$${v.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, "equity"]}
                  labelFormatter={(_, p) => p?.[0]?.payload?.label ?? ""}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="url(#cyanLine)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-[11px] italic text-[#8BABC6] flex items-center justify-center h-full">
              // collecting ticks_
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
};

export default EquityCurvePanel;
