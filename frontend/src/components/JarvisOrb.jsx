import React from "react";

export const JarvisOrb = ({ state = "idle" }) => {
  const animClass =
    state === "listening"
      ? "orb-listening"
      : state === "thinking"
      ? "orb-thinking"
      : "orb-idle";

  const coreColor =
    state === "listening" ? "#FF007F" : state === "thinking" ? "#FFB000" : "#00F0FF";

  return (
    <div
      className="relative flex items-center justify-center"
      data-testid="jarvis-orb"
    >
      {/* Outer rotating dashed ring */}
      <svg
        className="absolute orb-ring-3"
        width="380"
        height="380"
        viewBox="0 0 380 380"
        style={{ filter: "drop-shadow(0 0 8px rgba(0,240,255,0.4))" }}
      >
        <circle
          cx="190"
          cy="190"
          r="180"
          fill="none"
          stroke={coreColor}
          strokeOpacity="0.25"
          strokeWidth="1"
          strokeDasharray="2 8"
        />
      </svg>

      <svg
        className="absolute orb-ring-2"
        width="300"
        height="300"
        viewBox="0 0 300 300"
      >
        <circle
          cx="150"
          cy="150"
          r="142"
          fill="none"
          stroke={coreColor}
          strokeOpacity="0.45"
          strokeWidth="1"
          strokeDasharray="20 6 4 6"
        />
        {/* tick marks */}
        {Array.from({ length: 36 }).map((_, i) => (
          <line
            key={i}
            x1="150"
            y1="6"
            x2="150"
            y2={i % 6 === 0 ? "20" : "12"}
            stroke={coreColor}
            strokeOpacity={i % 6 === 0 ? "0.7" : "0.3"}
            strokeWidth="1"
            transform={`rotate(${i * 10} 150 150)`}
          />
        ))}
      </svg>

      <svg
        className="absolute orb-ring-1"
        width="240"
        height="240"
        viewBox="0 0 240 240"
      >
        <circle
          cx="120"
          cy="120"
          r="112"
          fill="none"
          stroke={coreColor}
          strokeOpacity="0.6"
          strokeWidth="1.5"
          strokeDasharray="60 8 4 8"
        />
      </svg>

      {/* Glow halo */}
      <div
        className={`absolute rounded-full ${animClass}`}
        style={{
          width: 200,
          height: 200,
          background: `radial-gradient(circle at 50% 50%, ${coreColor}66 0%, ${coreColor}22 35%, transparent 70%)`,
        }}
      />

      {/* Core sphere */}
      <div
        className={`relative rounded-full ${animClass}`}
        style={{
          width: 130,
          height: 130,
          background: `radial-gradient(circle at 35% 30%, #ffffff 0%, ${coreColor} 35%, #061B33 80%, #02060d 100%)`,
          boxShadow: `0 0 60px ${coreColor}, inset 0 0 30px ${coreColor}88, inset 0 0 80px #02060d`,
        }}
      >
        {/* Inner highlight */}
        <div
          className="absolute rounded-full"
          style={{
            top: "18%",
            left: "22%",
            width: "30%",
            height: "20%",
            background:
              "radial-gradient(ellipse at center, rgba(255,255,255,0.55), transparent 70%)",
            filter: "blur(4px)",
          }}
        />
        {/* Core dot */}
        <div
          className="absolute rounded-full"
          style={{
            top: "50%",
            left: "50%",
            transform: "translate(-50%,-50%)",
            width: 12,
            height: 12,
            background: "#02060d",
            boxShadow: `0 0 24px ${coreColor}, inset 0 0 6px #000`,
          }}
        />
      </div>

      {/* State label */}
      <div
        className="absolute -bottom-14 font-display text-xs tracking-[0.4em] uppercase"
        style={{ color: coreColor, textShadow: `0 0 10px ${coreColor}` }}
        data-testid="orb-state-label"
      >
        {state === "listening"
          ? "// LISTENING"
          : state === "thinking"
          ? "// PROCESSING"
          : "// JARVIS · ONLINE"}
      </div>
    </div>
  );
};

export default JarvisOrb;
