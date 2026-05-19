import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, AudioLines, Loader2, X } from "lucide-react";

/**
 * Full-screen "Ask Jarvis" modal, triggered from the Bottom Nav center "+" button.
 * Replaces the persistent floating bar so the Dashboard stays single-screen.
 */
export const AskJarvisModal = ({ open, onClose, onSend, busy, listening, onToggleVoice, lastReply }) => {
  const [value, setValue] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(t);
    }
  }, [open]);

  useEffect(() => {
    const handler = (e) => {
      if (open && e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const submit = (e) => {
    e?.preventDefault();
    const v = value.trim();
    if (!v || busy) return;
    onSend(v);
    setValue("");
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex flex-col"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          style={{
            background: "rgba(8,8,12,0.78)",
            backdropFilter: "blur(28px) saturate(140%)",
            WebkitBackdropFilter: "blur(28px) saturate(140%)",
          }}
          data-testid="ask-jarvis-modal"
        >
          {/* Close */}
          <div className="absolute top-4 right-4 z-10">
            <button
              onClick={onClose}
              className="w-10 h-10 rounded-full flex items-center justify-center text-white/70 hover:text-white transition"
              style={{ background: "rgba(255,255,255,0.06)", border: "1px solid var(--border-hi)" }}
              data-testid="ask-jarvis-close"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>

          {/* Center orb + answer */}
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <motion.div
              className="relative w-32 h-32 rounded-full flex items-center justify-center"
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            >
              <div
                className="absolute inset-0 rounded-full orb-spin"
                style={{
                  background: "conic-gradient(from 0deg, var(--accent-1), var(--accent-2), var(--accent-1))",
                  WebkitMask: "radial-gradient(circle, transparent 56%, #000 57%)",
                  mask: "radial-gradient(circle, transparent 56%, #000 57%)",
                }}
              />
              <div
                className={`absolute inset-3 rounded-full ${listening ? "listening" : ""}`}
                style={{
                  background:
                    "radial-gradient(circle at 30% 30%, rgba(255,255,255,0.85), var(--accent-1) 38%, var(--accent-2) 100%)",
                  boxShadow: "0 0 64px rgba(108,141,255,0.6)",
                }}
              />
            </motion.div>

            <div className="mt-6 text-[12px] uppercase tracking-[0.18em] text-white/45">
              {busy ? "Thinking…" : listening ? "Listening…" : "JARVIS"}
            </div>

            {lastReply && !busy && (
              <motion.div
                key={lastReply}
                className="mt-5 max-w-xl text-center text-[15px] text-white/80 leading-relaxed"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                data-testid="ask-jarvis-reply"
              >
                {lastReply}
              </motion.div>
            )}
          </div>

          {/* Input pill */}
          <div className="px-4 pb-8" style={{ paddingBottom: "max(2rem, env(safe-area-inset-bottom))" }}>
            <motion.form
              onSubmit={submit}
              className="flex items-center gap-2 w-full max-w-2xl mx-auto px-3 py-2.5 rounded-full"
              style={{
                background: "rgba(20,20,28,0.88)",
                border: "1px solid var(--border-hi)",
                boxShadow: "0 24px 48px rgba(0,0,0,0.55)",
              }}
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            >
              <input
                ref={inputRef}
                type="text"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={listening ? "Listening…" : "Ask Jarvis anything…"}
                className="flex-1 bg-transparent outline-none text-[15px] text-white placeholder:text-white/40 px-2"
                disabled={busy}
                data-testid="ask-jarvis-input"
              />

              <button
                type="button"
                onClick={onToggleVoice}
                className="w-10 h-10 rounded-full flex items-center justify-center text-white/70 hover:text-white transition flex-shrink-0"
                aria-label="Voice"
                data-testid="ask-jarvis-mic"
              >
                <Mic size={17} className={listening ? "listening" : ""} />
              </button>

              <button
                type="submit"
                disabled={busy || !value.trim()}
                className="w-11 h-11 rounded-full flex items-center justify-center transition disabled:opacity-50 flex-shrink-0"
                style={{
                  background: "linear-gradient(135deg, var(--accent-1), var(--accent-2))",
                  color: "#fff",
                  boxShadow: "0 6px 16px rgba(108,141,255,0.45)",
                }}
                aria-label="Send"
                data-testid="ask-jarvis-send"
              >
                {busy ? <Loader2 size={16} className="animate-spin" /> : <AudioLines size={16} />}
              </button>
            </motion.form>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default AskJarvisModal;
