import React from "react";

export const Panel = ({
  title,
  subtitle,
  children,
  className = "",
  delay = 0,
  testId,
  accent = "cyan",
  icon: Icon,
}) => {
  const accentColor =
    accent === "magenta" ? "#FF007F" : accent === "amber" ? "#FFB000" : "#00F0FF";

  return (
    <div
      className={`jv-panel panel-in flex flex-col ${className}`}
      style={{ animationDelay: `${delay}ms` }}
      data-testid={testId}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 divider-cyan">
        <div className="flex items-center gap-1.5">
          <span className="mac-dot" style={{ background: "#FF5F56" }} />
          <span className="mac-dot" style={{ background: "#FFBD2E" }} />
          <span className="mac-dot" style={{ background: "#27C93F" }} />
        </div>
        <div className="flex items-center gap-2">
          {Icon && <Icon size={12} style={{ color: accentColor }} />}
          <span
            className="font-display text-[10px] tracking-[0.3em] uppercase"
            style={{ color: accentColor }}
          >
            {title}
          </span>
        </div>
        <span className="text-[9px] tracking-[0.2em] text-[#8BABC6] uppercase">
          {subtitle || "live"}
        </span>
      </div>
      {/* Body */}
      <div className="flex-1 p-3 overflow-hidden">{children}</div>
    </div>
  );
};

export default Panel;
