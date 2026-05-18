import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(Number.isFinite(v) ? v : 0);

const fmtTime = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
};

export const RecentTradesTable = ({ delay = 0.5 }) => {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/dashboard/recent-trades?limit=6`);
        if (alive) setRows(r.data.trades || []);
      } catch {}
    };
    load();
    const t = setInterval(load, 12000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  return (
    <motion.div
      className="card p-4 flex flex-col"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="recent-trades-table"
    >
      <header className="flex items-center justify-between mb-3">
        <div className="card-title">Recent Trades</div>
        <button className="text-[12px] font-medium" style={{ color: "var(--accent-1)" }}>
          View All
        </button>
      </header>
      {rows.length === 0 ? (
        <div className="text-[12px] text-white/40 py-6 text-center">No trades yet</div>
      ) : (
        <div className="divide-y divide-white/5">
          {rows.map((r, i) => {
            const side = (r.side || "").toUpperCase();
            const pl = r.pl ?? 0;
            const up = pl >= 0;
            return (
              <div key={i} className="grid grid-cols-12 gap-2 items-center py-2.5 text-[13px]">
                <div className="col-span-3 text-[11px] text-white/45 tabular">
                  {fmtTime(r.ts)}
                </div>
                <div className="col-span-4 flex items-center gap-2 min-w-0">
                  <span className="font-medium truncate">{r.symbol}</span>
                </div>
                <div className="col-span-2">
                  <span
                    className="text-[11px] font-semibold px-1.5 py-0.5 rounded"
                    style={{
                      background:
                        side === "BUY" ? "rgba(34,197,94,0.14)" : "rgba(239,68,68,0.14)",
                      color: side === "BUY" ? "var(--up)" : "var(--down)",
                    }}
                  >
                    {side} {Number(r.qty).toFixed(2)}
                  </span>
                </div>
                <div className="col-span-3 text-right tabular font-medium" style={{ color: up ? "var(--up)" : "var(--down)" }}>
                  {up ? "+" : ""}
                  {fmtMoney(pl)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
};

export default RecentTradesTable;
