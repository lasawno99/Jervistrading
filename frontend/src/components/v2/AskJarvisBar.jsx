import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, AudioLines, Loader2 } from "lucide-react";

/**
 * Floating Ask Jarvis bar with orb + voice button.
 * Single rounded glass pill at the bottom of the workspace.
 */
export const AskJarvisBar = ({ onSend, busy, listening, onToggleVoice }) => {
  const [value, setValue] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const submit = (e) => {
    e?.preventDefault();
    const v = value.trim();
    if (!v || busy) return;
    onSend(v);
    setValue("");
  };

  return (
    <motion.form
      onSubmit={submit}
      className="flex items-center gap-3 w-full max-w-2xl mx-auto px-2 py-2 pr-2.5 rounded-full"
      style={{
        background: "rgba(20,20,28,0.78)",
        backdropFilter: "blur(28px) saturate(140%)",
        WebkitBackdropFilter: "blur(28px) saturate(140%)",
        border: "1px solid var(--border-hi)",
        boxShadow: "0 24px 48px rgba(0,0,0,0.55)",
      }}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      data-testid="ask-jarvis-bar"
    >
      {/* Orb */}
      <div
        className="relative w-11 h-11 rounded-full flex-shrink-0 flex items-center justify-center"
        style={{ background: "rgba(0,0,0,0.4)" }}
      >
        <div
          className="absolute inset-0 rounded-full orb-spin"
          style={{
            background:
              "conic-gradient(from 0deg, var(--accent-1), var(--accent-2), var(--accent-1))",
            padding: 1.5,
            WebkitMask:
              "radial-gradient(circle, transparent 56%, #000 57%)",
            mask: "radial-gradient(circle, transparent 56%, #000 57%)",
          }}
        />
        <div
          className="absolute inset-1.5 rounded-full"
          style={{
            background:
              "radial-gradient(circle at 30% 30%, rgba(255,255,255,0.6), var(--accent-1) 35%, var(--accent-2) 100%)",
            boxShadow: "0 0 22px rgba(108,141,255,0.55)",
          }}
        />
      </div>

      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={listening ? "Listening…" : "Ask Jarvis anything..."}
        className="flex-1 bg-transparent outline-none text-[14px] text-white placeholder:text-white/40"
        disabled={busy}
        data-testid="ask-jarvis-input"
      />

      <button
        type="button"
        onClick={onToggleVoice}
        className="w-9 h-9 rounded-full flex items-center justify-center text-white/65 hover:text-white transition flex-shrink-0"
        aria-label="Voice"
        data-testid="ask-jarvis-mic"
      >
        <Mic size={16} className={listening ? "listening" : ""} />
      </button>

      <button
        type="submit"
        disabled={busy || !value.trim()}
        className="w-11 h-11 rounded-full flex items-center justify-center transition disabled:opacity-50 flex-shrink-0"
        style={{
          background: "linear-gradient(135deg, var(--accent-1), var(--accent-2))",
          color: "#fff",
          boxShadow: "0 6px 16px rgba(108,141,255,0.35)",
        }}
        aria-label="Send"
        data-testid="ask-jarvis-send"
      >
        {busy ? <Loader2 size={16} className="animate-spin" /> : <AudioLines size={16} />}
      </button>
    </motion.form>
  );
};

export default AskJarvisBar;
