import React from "react";
import { Search, Bell, Menu } from "lucide-react";
import { motion } from "framer-motion";

export const TopHeader = ({ onMenu }) => (
  <motion.header
    className="flex items-center justify-between px-4 md:px-6 py-3.5"
    initial={{ opacity: 0, y: -8 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    data-testid="top-header"
  >
    <div className="flex items-center gap-3">
      <div
        className="w-9 h-9 rounded-xl flex items-center justify-center"
        style={{
          background:
            "conic-gradient(from 90deg, var(--accent-1), var(--accent-2), var(--accent-1))",
          padding: 2,
        }}
      >
        <div className="w-full h-full rounded-[10px] bg-[var(--bg)] flex items-center justify-center">
          <div
            className="w-3.5 h-3.5 rounded-full"
            style={{
              background:
                "radial-gradient(circle at 35% 30%, #fff 0%, var(--accent-1) 40%, var(--accent-2) 100%)",
            }}
          />
        </div>
      </div>
      <span className="text-[18px] font-semibold tracking-tight">Jarvis</span>
    </div>

    <div className="flex items-center gap-2">
      <button
        className="w-9 h-9 rounded-xl flex items-center justify-center text-white/65 hover:text-white hover:bg-white/5 transition"
        aria-label="Search"
        data-testid="header-search"
      >
        <Search size={17} />
      </button>
      <button
        className="relative w-9 h-9 rounded-xl flex items-center justify-center text-white/65 hover:text-white hover:bg-white/5 transition"
        aria-label="Notifications"
        data-testid="header-notifications"
      >
        <Bell size={17} />
        <span
          className="absolute top-1 right-1.5 w-4 h-4 rounded-full text-[10px] font-semibold flex items-center justify-center"
          style={{ background: "var(--accent-2)", color: "#fff" }}
        >
          3
        </span>
      </button>
      <button
        className="w-9 h-9 rounded-xl flex items-center justify-center text-white/65 hover:text-white hover:bg-white/5 transition"
        aria-label="Menu"
        onClick={onMenu}
        data-testid="header-menu"
      >
        <Menu size={17} />
      </button>
    </div>
  </motion.header>
);

export default TopHeader;
