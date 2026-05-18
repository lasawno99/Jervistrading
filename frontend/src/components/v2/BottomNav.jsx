import React from "react";
import { motion } from "framer-motion";
import { LayoutGrid, PieChart, Bot, Settings, Plus } from "lucide-react";

const TABS = [
  { id: "dashboard", label: "Dashboard", Icon: LayoutGrid },
  { id: "portfolio", label: "Portfolio", Icon: PieChart },
  { id: "create", label: "", Icon: Plus, primary: true },
  { id: "agents", label: "Agents", Icon: Bot },
  { id: "settings", label: "Settings", Icon: Settings },
];

export const BottomNav = ({ active, onChange, onCreate }) => (
  <motion.nav
    className="flex items-center justify-around px-3 py-2.5 rounded-2xl"
    style={{
      background: "rgba(20,20,28,0.82)",
      backdropFilter: "blur(28px) saturate(140%)",
      WebkitBackdropFilter: "blur(28px) saturate(140%)",
      border: "1px solid var(--border)",
      boxShadow: "0 18px 36px rgba(0,0,0,0.45)",
    }}
    initial={{ opacity: 0, y: 18 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
    data-testid="bottom-nav"
  >
    {TABS.map(({ id, label, Icon, primary }) => {
      const isActive = active === id;
      if (primary) {
        return (
          <button
            key={id}
            onClick={onCreate}
            className="w-12 h-12 rounded-full flex items-center justify-center text-white transition hover:scale-105"
            style={{
              background: "linear-gradient(135deg, var(--accent-1), var(--accent-2))",
              boxShadow: "0 8px 20px rgba(108,141,255,0.45)",
            }}
            data-testid={`nav-${id}`}
            aria-label="Quick action"
          >
            <Icon size={20} />
          </button>
        );
      }
      return (
        <button
          key={id}
          onClick={() => onChange?.(id)}
          className="flex flex-col items-center gap-0.5 px-2 py-1 transition"
          style={{ color: isActive ? "var(--accent-1)" : "var(--text-3)" }}
          data-testid={`nav-${id}`}
        >
          <Icon size={18} />
          <span className="text-[10px] font-medium">{label}</span>
        </button>
      );
    })}
  </motion.nav>
);

export default BottomNav;
