import React, { useEffect, useRef, useState } from "react";
import { Mic, Send, Loader2, Sparkles } from "lucide-react";

export const CommandPalette = ({ onSend, busy, listening, onToggleVoice }) => {
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
    <form
      onSubmit={submit}
      className="flex items-center gap-2 px-2.5 py-2 w-full max-w-2xl bg-[#0a0a0a]/85 backdrop-blur-2xl border border-white/12 rounded-full shadow-[0_20px_40px_rgba(0,0,0,0.7)]"
      data-testid="command-palette"
    >
      <div className="flex items-center gap-1.5 pl-2 pr-1">
        <Sparkles size={14} className="text-white/55" />
        <span className="font-mono text-[10px] tracking-[0.28em] uppercase text-white/40 hidden sm:inline">
          ask jarvis
        </span>
      </div>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={listening ? "listening…" : "Type or speak — ⌘K"}
        className="flex-1 bg-transparent outline-none text-sm text-white placeholder:text-white/35 font-sans"
        data-testid="command-input"
        disabled={busy}
      />
      <button
        type="button"
        onClick={onToggleVoice}
        className="relative w-9 h-9 rounded-full flex items-center justify-center transition-all"
        style={{
          background: listening ? "rgba(255,59,110,0.16)" : "rgba(255,255,255,0.06)",
          border: `1px solid ${
            listening ? "rgba(255,59,110,0.6)" : "rgba(255,255,255,0.15)"
          }`,
          color: listening ? "var(--jv-down)" : "rgba(255,255,255,0.85)",
        }}
        data-testid="voice-toggle-btn"
        aria-label="Toggle voice"
      >
        <Mic size={14} />
        {listening && (
          <span
            className="absolute inset-0 rounded-full"
            style={{
              border: "1px solid rgba(255,59,110,0.7)",
              animation: "panel-in 1.2s ease-in-out infinite alternate",
            }}
          />
        )}
      </button>
      <button
        type="submit"
        disabled={busy || !value.trim()}
        className="w-9 h-9 rounded-full flex items-center justify-center transition-all disabled:opacity-40"
        style={{
          background: "#fff",
          color: "#000",
          boxShadow: "0 0 0 0 rgba(255,255,255,0.0)",
        }}
        data-testid="command-send-btn"
        aria-label="Send"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
      </button>
    </form>
  );
};

export default CommandPalette;
