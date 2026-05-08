import React from "react";
import { motion } from "framer-motion";

/**
 * Premium glassmorphic panel.
 * - Title row uses tracking-wide uppercase (small), no traffic-light dots.
 * - Subtle entrance via Framer Motion.
 */
export const Panel = ({
  title,
  subtitle,
  right,
  children,
  className = "",
  delay = 0,
  testId,
  icon: Icon,
  variant = "default", // "default" | "hero"
}) => {
  const base = variant === "hero" ? "jv-hero" : "jv-panel";
  return (
    <motion.section
      className={`${base} flex flex-col ${className}`}
      data-testid={testId}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1], delay: delay / 1000 }}
    >
      {(title || subtitle || right) && (
        <header className="flex items-center justify-between px-5 pt-4 pb-3">
          <div className="flex items-center gap-2">
            {Icon && <Icon size={13} className="text-white/40" />}
            <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/45">
              {title}
            </span>
            {subtitle && (
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-white/25">
                · {subtitle}
              </span>
            )}
          </div>
          {right}
        </header>
      )}
      <div className="flex-1 px-5 pb-5 pt-1 overflow-hidden">{children}</div>
    </motion.section>
  );
};

export default Panel;
