import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Sparkles, MessageCircle, Bot, ChevronRight } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const AgentStatusCard = ({ delay = 0.3 }) => {
  const [info, setInfo] = useState(null);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/`).then((r) => alive && setInfo(r.data)).catch(() => {});
    return () => { alive = false; };
  }, []);

  const agents = [
    {
      name: "Kimi AI",
      role: "Chat fallback",
      Icon: Sparkles,
      iconColor: "#f59e0b",
      online: info?.kimi_active ?? true,
    },
    {
      name: "Telegram Bot",
      role: "Live alerts",
      Icon: MessageCircle,
      iconColor: "#6c8dff",
      online: info?.telegram_configured ?? true,
    },
    {
      name: "Auto Trader",
      role: "Risk Guard live",
      Icon: Bot,
      iconColor: "#9b7bff",
      online: true,
    },
  ];

  return (
    <motion.div
      className="card p-4"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="agent-status-card"
    >
      <div className="card-title mb-3">Agent Status</div>
      <div className="space-y-3">
        {agents.map((a) => (
          <div key={a.name} className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center"
              style={{ background: `${a.iconColor}22`, color: a.iconColor }}
            >
              <a.Icon size={16} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium leading-tight truncate">{a.name}</div>
              <div
                className="text-[11px] mt-0.5"
                style={{ color: a.online ? "var(--up)" : "var(--down)" }}
              >
                {a.online ? "Online" : "Offline"}
              </div>
            </div>
          </div>
        ))}
      </div>
      <button
        className="mt-4 w-full text-[13px] font-medium py-2 rounded-xl transition"
        style={{
          background: "rgba(155,123,255,0.12)",
          color: "var(--accent-2)",
        }}
        data-testid="view-all-agents"
      >
        View All Agents <ChevronRight size={13} className="inline -mt-0.5" />
      </button>
    </motion.div>
  );
};

export default AgentStatusCard;
