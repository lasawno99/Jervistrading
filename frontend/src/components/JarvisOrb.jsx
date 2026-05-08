import React from "react";
import { motion } from "framer-motion";

/**
 * CSS-only premium JARVIS orb.
 * - Layered: outer aura halo · spinning conic ring · glassy core · inner highlight · core dot
 * - States: idle / listening / thinking — change pace + accent color
 * - No SVG, no images. All built from gradients + box-shadow.
 */
const STATE_COLOR = {
  idle: { aura: "0, 229, 255", ring: "123, 97, 255", label: "JARVIS · ONLINE" },
  listening: { aura: "255, 59, 110", ring: "255, 176, 32", label: "LISTENING" },
  thinking: { aura: "255, 176, 32", ring: "0, 229, 255", label: "PROCESSING" },
};

export const JarvisOrb = ({ state = "idle", size = 220 }) => {
  const c = STATE_COLOR[state] || STATE_COLOR.idle;
  const stateClass =
    state === "listening" ? "orb-listening" : state === "thinking" ? "orb-thinking" : "";

  return (
    <div
      className={`relative flex items-center justify-center ${stateClass}`}
      style={{ width: size, height: size }}
      data-testid="jarvis-orb"
    >
      {/* Outer aura — soft glow */}
      <motion.div
        className="absolute inset-0 rounded-full pointer-events-none"
        style={{
          background: `radial-gradient(closest-side, rgba(${c.aura},0.25) 0%, rgba(${c.aura},0.10) 45%, transparent 75%)`,
          filter: "blur(8px)",
        }}
        animate={{ scale: [1, 1.06, 1], opacity: [0.7, 1, 0.7] }}
        transition={{ duration: state === "listening" ? 1.4 : 4.5, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Spinning conic ring — outermost ring of light */}
      <div
        className="absolute orb-conic rounded-full"
        style={{
          width: size * 0.92,
          height: size * 0.92,
          padding: 1,
          background: `conic-gradient(from 0deg, rgba(${c.ring},0) 0deg, rgba(${c.ring},0.55) 90deg, rgba(${c.aura},0.4) 180deg, rgba(${c.ring},0) 360deg)`,
          WebkitMask: "radial-gradient(transparent 62%, #000 63%)",
          mask: "radial-gradient(transparent 62%, #000 63%)",
        }}
      />

      {/* Counter-spin inner ring (very thin) */}
      <div
        className="absolute orb-conic-rev rounded-full"
        style={{
          width: size * 0.74,
          height: size * 0.74,
          padding: 1,
          background: `conic-gradient(from 180deg, rgba(${c.aura},0) 0deg, rgba(${c.aura},0.45) 60deg, rgba(${c.ring},0.25) 220deg, rgba(${c.aura},0) 360deg)`,
          WebkitMask: "radial-gradient(transparent 67%, #000 68%)",
          mask: "radial-gradient(transparent 67%, #000 68%)",
        }}
      />

      {/* Glass core */}
      <div
        className="relative orb-breathe rounded-full"
        style={{
          width: size * 0.62,
          height: size * 0.62,
          background: `
            radial-gradient(circle at 32% 28%, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.05) 25%, transparent 40%),
            radial-gradient(circle at 50% 50%, rgba(${c.aura},0.6) 0%, rgba(${c.aura},0.18) 35%, rgba(10,10,12,0.95) 75%)
          `,
          boxShadow: `
            0 0 60px rgba(${c.aura},0.5),
            0 0 120px rgba(${c.ring},0.25),
            inset 0 0 40px rgba(${c.aura},0.35),
            inset 0 -30px 60px rgba(0,0,0,0.7)
          `,
          backdropFilter: "blur(8px)",
        }}
      >
        {/* Highlight */}
        <div
          className="absolute rounded-full"
          style={{
            top: "16%",
            left: "20%",
            width: "32%",
            height: "20%",
            background:
              "radial-gradient(ellipse at center, rgba(255,255,255,0.55), transparent 70%)",
            filter: "blur(5px)",
          }}
        />
        {/* Inner core dot */}
        <div
          className="absolute rounded-full"
          style={{
            top: "50%",
            left: "50%",
            transform: "translate(-50%,-50%)",
            width: 10,
            height: 10,
            background: "#0a0a0a",
            boxShadow: `0 0 22px rgba(${c.aura},1), inset 0 0 6px #000`,
          }}
        />
      </div>

      {/* State label */}
      <div
        className="absolute font-mono text-[9px] tracking-[0.42em] uppercase text-white/55"
        style={{ bottom: -28 }}
        data-testid="orb-state-label"
      >
        {c.label}
      </div>
    </div>
  );
};

export default JarvisOrb;
