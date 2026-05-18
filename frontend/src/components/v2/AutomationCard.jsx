import React, { useState } from "react";
import { motion } from "framer-motion";

export const AutomationCard = ({ delay = 0.35 }) => {
  const [on, setOn] = useState(true);

  return (
    <motion.div
      className="card p-4"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="automation-card"
    >
      <div className="card-title mb-3">Automation</div>

      <div className="flex items-center justify-between mb-4">
        <span className="text-[14px] font-medium">Auto-Trader</span>
        <button
          onClick={() => setOn((v) => !v)}
          className="relative w-12 h-7 rounded-full transition-colors"
          style={{
            background: on
              ? "linear-gradient(90deg, var(--accent-1), var(--accent-2))"
              : "rgba(255,255,255,0.10)",
          }}
          data-testid="auto-trader-toggle"
          aria-pressed={on}
        >
          <span
            className="absolute top-0.5 w-6 h-6 rounded-full bg-white transition-all"
            style={{
              left: on ? "calc(100% - 26px)" : "2px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.3)",
            }}
          />
        </button>
      </div>

      <div className="space-y-2.5">
        <Row label="Status" value={on ? "Running" : "Paused"} valueColor={on ? "var(--up)" : "var(--text-3)"} />
        <Row label="Last execution" value="2m ago" />
        <Row label="Cycles today" value="14" />
      </div>

      <button
        className="mt-4 w-full text-[13px] font-medium py-2 rounded-xl transition btn-primary"
        data-testid="view-automation-activity"
      >
        View Activity
      </button>
    </motion.div>
  );
};

const Row = ({ label, value, valueColor }) => (
  <div className="flex items-center justify-between text-[13px]">
    <span className="text-white/50">{label}</span>
    <span className="font-medium tabular" style={{ color: valueColor || "var(--text)" }}>
      {value}
    </span>
  </div>
);

export default AutomationCard;
