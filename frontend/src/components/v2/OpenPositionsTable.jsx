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

const Pl = ({ value }) => {
  if (!Number.isFinite(value)) return <span className="text-white/40">—</span>;
  const up = value >= 0;
  return (
    <span className="tabular font-medium" style={{ color: up ? "var(--up)" : "var(--down)" }}>
      {up ? "+" : ""}
      {fmtMoney(value)}
    </span>
  );
};

const Pct = ({ value }) => {
  if (!Number.isFinite(value)) return <span className="text-white/40">—</span>;
  const up = value >= 0;
  return (
    <span className="tabular font-medium" style={{ color: up ? "var(--up)" : "var(--down)" }}>
      {up ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
};

export const OpenPositionsTable = ({ delay = 0.45 }) => {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/dashboard/open-positions`);
        if (alive) setRows(r.data.positions || []);
      } catch {}
    };
    load();
    const t = setInterval(load, 10000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  return (
    <motion.div
      className="card p-4 flex flex-col"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="open-positions-table"
    >
      <header className="flex items-center justify-between mb-3">
        <div className="card-title">Open Positions</div>
        <button className="text-[12px] font-medium" style={{ color: "var(--accent-1)" }}>
          View All
        </button>
      </header>
      {rows.length === 0 ? (
        <div className="text-[12px] text-white/40 py-6 text-center">No open positions</div>
      ) : (
        <div className="overflow-hidden">
          <div className="grid grid-cols-12 gap-2 text-[10px] tracking-[0.06em] uppercase text-white/35 px-1 pb-2 border-b border-white/5">
            <div className="col-span-4">Asset</div>
            <div className="col-span-2 text-right">Size</div>
            <div className="col-span-2 text-right">Entry</div>
            <div className="col-span-2 text-right">P/L</div>
            <div className="col-span-2 text-right">P/L %</div>
          </div>
          <div className="divide-y divide-white/5">
            {rows.slice(0, 6).map((r, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-center py-2.5 text-[13px]">
                <div className="col-span-4 flex items-center gap-2 min-w-0">
                  <span
                    className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-semibold flex-shrink-0"
                    style={{
                      background: `${brokerColor(r.broker)}24`,
                      color: brokerColor(r.broker),
                    }}
                  >
                    {(r.symbol || "?")[0]}
                  </span>
                  <span className="truncate font-medium">{r.symbol}</span>
                  <span className="text-[10px] text-white/35 uppercase">{r.broker}</span>
                </div>
                <div className="col-span-2 text-right tabular text-white/80">
                  {Number(r.qty).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                </div>
                <div className="col-span-2 text-right tabular text-white/80">
                  {fmtMoney(r.entry)}
                </div>
                <div className="col-span-2 text-right"><Pl value={r.pl} /></div>
                <div className="col-span-2 text-right"><Pct value={r.pl_pct} /></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

const brokerColor = (b) =>
  b === "alpaca" ? "#6c8dff" : b === "oanda" ? "#9b7bff" : "#f59e0b";

export default OpenPositionsTable;
