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
      className="jv-panel flex items-center gap-3 px-4 py-3 w-full max-w-3xl"
      style={{ borderRadius: 999, borderColor: "rgba(0,240,255,0.5)" }}
      data-testid="command-palette"
    >
      <Sparkles size={16} style={{ color: "#00F0FF" }} />
      <span className="font-display text-[10px] tracking-[0.4em] uppercase text-[#00F0FF] hidden sm:inline">
        CMD
      </span>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={listening ? "// listening..." : "Speak or type a command — ⌘K"}
        className="flex-1 bg-transparent outline-none text-sm text-white placeholder:text-[#8BABC6] font-mono"
        data-testid="command-input"
        disabled={busy}
      />
      <button
        type="button"
        onClick={onToggleVoice}
        className="relative w-9 h-9 rounded-full flex items-center justify-center transition-all"
        style={{
          background: listening ? "rgba(255,0,127,0.18)" : "rgba(0,240,255,0.12)",
          border: `1px solid ${listening ? "#FF007F" : "rgba(0,240,255,0.5)"}`,
          color: listening ? "#FF007F" : "#00F0FF",
        }}
        data-testid="voice-toggle-btn"
        aria-label="Toggle voice"
      >
        <Mic size={14} />
        {listening && (
          <span
            className="absolute inset-0 rounded-full"
            style={{
              border: "1px solid #FF007F",
              animation: "orb-pulse-fast 1.2s ease-in-out infinite",
            }}
          />
        )}
      </button>
      <button
        type="submit"
        disabled={busy || !value.trim()}
        className="w-9 h-9 rounded-full flex items-center justify-center transition-all disabled:opacity-40"
        style={{
          background: "#00F0FF",
          color: "#050B14",
          boxShadow: "0 0 18px rgba(0,240,255,0.6)",
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
