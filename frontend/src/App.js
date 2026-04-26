import React, { useCallback, useEffect, useRef, useState } from "react";
import "@/App.css";
import "@/index.css";
import axios from "axios";
import { Toaster, toast } from "sonner";
import JarvisOrb from "@/components/JarvisOrb";
import CommandPalette from "@/components/CommandPalette";
import TradingPanel from "@/components/panels/TradingPanel";
import TwitterPanel from "@/components/panels/TwitterPanel";
import CalendarPanel from "@/components/panels/CalendarPanel";
import NewsPanel from "@/components/panels/NewsPanel";
import BotPositionsPanel from "@/components/panels/BotPositionsPanel";
import BotSignalsPanel from "@/components/panels/BotSignalsPanel";
import BotControlPanel from "@/components/panels/BotControlPanel";
import { Activity, Cpu, Radio, Wifi } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const BG_IMAGE = "https://images.pexels.com/photos/14976666/pexels-photo-14976666.jpeg";

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function useSpeechRecognition(onResult) {
  const recRef = useRef(null);
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const r = new SR();
    r.continuous = false;
    r.interimResults = false;
    r.lang = "en-US";
    r.onresult = (e) => {
      const text = e.results[0][0].transcript;
      onResult(text);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recRef.current = r;
    setSupported(true);
  }, [onResult]);

  const start = () => {
    if (!recRef.current) return;
    try { recRef.current.start(); setListening(true); } catch {}
  };
  const stop = () => {
    if (!recRef.current) return;
    try { recRef.current.stop(); } catch {}
    setListening(false);
  };

  return { supported, listening, start, stop };
}

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05; u.pitch = 0.85; u.volume = 0.9;
    window.speechSynthesis.speak(u);
  } catch {}
}

function App() {
  const [orbState, setOrbState] = useState("idle");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [lastReply, setLastReply] = useState("Standing by. Issue a command or fire up auto-trader.");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [serviceInfo, setServiceInfo] = useState(null);
  const clock = useClock();

  const bumpRefresh = () => setRefreshKey((k) => k + 1);

  useEffect(() => {
    axios.get(`${API}/`).then((r) => setServiceInfo(r.data)).catch(() => {});
  }, []);

  const handleCommand = useCallback(
    async (text) => {
      setBusy(true);
      setOrbState("thinking");
      try {
        const r = await axios.post(`${API}/chat`, { message: text, session_id: sessionId });
        setSessionId(r.data.session_id);
        setLastReply(r.data.reply);
        toast(`${r.data.intent.toUpperCase()} · task spawned`, { description: r.data.reply });
        if (voiceEnabled) speak(r.data.reply);
        bumpRefresh();
      } catch (e) {
        toast.error("Command failed", { description: String(e?.message || e) });
      } finally {
        setBusy(false);
        setOrbState("idle");
      }
    },
    [sessionId, voiceEnabled]
  );

  const onVoiceResult = useCallback(
    (text) => { setOrbState("thinking"); handleCommand(text); },
    [handleCommand]
  );

  const speech = useSpeechRecognition(onVoiceResult);

  const toggleVoice = () => {
    if (!speech.supported) { toast.error("Voice not supported in this browser"); return; }
    if (speech.listening) { speech.stop(); setOrbState("idle"); }
    else { speech.start(); setOrbState("listening"); }
  };

  return (
    <div className="App grain scan-lines relative min-h-screen overflow-hidden" data-testid="jarvis-app">
      <div
        className="fixed inset-0 z-0"
        style={{
          backgroundImage: `url(${BG_IMAGE})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          filter: "saturate(0.6) brightness(0.55) hue-rotate(180deg)",
        }}
      />
      <div className="fixed inset-0 z-0"
        style={{ background: "radial-gradient(ellipse at center, rgba(5,11,20,0.55) 0%, rgba(5,11,20,0.92) 65%, #050B14 100%)" }} />
      <div className="fixed inset-0 z-0 pointer-events-none"
        style={{ background: "radial-gradient(ellipse at center, transparent 30%, rgba(5,11,20,0.6) 80%, #050B14 100%)" }} />

      <Toaster
        theme="dark"
        position="top-center"
        toastOptions={{
          style: {
            background: "rgba(10,17,40,0.85)",
            border: "1px solid rgba(0,240,255,0.4)",
            color: "#fff",
            backdropFilter: "blur(12px)",
          },
        }}
      />

      <header className="relative z-30 flex items-center justify-between px-6 py-3 border-b border-[#00F0FF]/20" data-testid="hud-top">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-md border border-[#00F0FF]/50 flex items-center justify-center"
               style={{ background: "rgba(0,240,255,0.08)" }}>
            <Activity size={14} style={{ color: "#00F0FF" }} />
          </div>
          <div>
            <div className="font-display text-sm tracking-[0.4em] uppercase text-white glow-cyan">
              JARVIS // TRADE-CTR
            </div>
            <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">
              kimi k2.5 · paper desk · 24/7
            </div>
          </div>
        </div>

        <div className="hidden lg:flex items-center gap-6 text-[10px] tracking-[0.3em] uppercase text-[#8BABC6]">
          <div className="flex items-center gap-2">
            <Wifi size={12} style={{ color: serviceInfo?.kimi_active ? "#27C93F" : "#FFB000" }} />
            <span>kimi {serviceInfo?.kimi_active ? "online" : "fallback"}</span>
          </div>
          <div className="flex items-center gap-2">
            <Radio size={12} style={{ color: serviceInfo?.telegram_configured ? "#27C93F" : "#FF5F56" }} />
            <span>tg {serviceInfo?.telegram_configured ? "linked" : "offline"}</span>
          </div>
          <div className="flex items-center gap-2">
            <Cpu size={12} style={{ color: "#00F0FF" }} />
            <span>cores · 32B active</span>
          </div>
        </div>

        <div className="font-display text-sm tracking-[0.3em] text-[#00F0FF] glow-cyan" data-testid="hud-clock">
          {clock.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </div>
      </header>

      <main className="relative z-20 px-4 md:px-6 pt-6 pb-44">
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-12 lg:col-span-3 space-y-4">
            <BotPositionsPanel delay={0} refreshKey={refreshKey} />
            <TradingPanel delay={120} />
            <CalendarPanel delay={200} />
          </div>

          <div className="col-span-12 lg:col-span-6 flex flex-col items-center">
            <div className="relative w-full flex flex-col items-center mt-2 lg:mt-6">
              <JarvisOrb state={orbState} />
              <div className="mt-20 max-w-xl text-center px-4 panel-in" style={{ animationDelay: "200ms" }}>
                <div className="text-[10px] tracking-[0.4em] uppercase text-[#8BABC6] mb-2">// last response</div>
                <div className="font-mono text-sm md:text-base text-white leading-relaxed" data-testid="last-reply">
                  {lastReply}<span className="caret text-[#00F0FF]"> ▌</span>
                </div>
              </div>
            </div>
            <div className="mt-8 w-full">
              <BotSignalsPanel delay={300} onChange={bumpRefresh} />
            </div>
          </div>

          <div className="col-span-12 lg:col-span-3 space-y-4">
            <BotControlPanel delay={60} onChange={bumpRefresh} />
            <TwitterPanel delay={180} />
            <NewsPanel delay={260} />
          </div>
        </div>
      </main>

      <div className="fixed bottom-0 left-0 right-0 z-40 px-4 pb-6 pt-12 pointer-events-none"
           style={{ background: "linear-gradient(to top, rgba(5,11,20,0.95) 0%, rgba(5,11,20,0.6) 60%, transparent 100%)" }}>
        <div className="max-w-3xl mx-auto pointer-events-auto flex flex-col items-center gap-3">
          <div className="flex items-center gap-3 flex-wrap justify-center">
            <button
              onClick={() => setVoiceEnabled((v) => !v)}
              className="text-[10px] tracking-[0.3em] uppercase px-3 py-1 rounded-full border transition-colors"
              style={{
                color: voiceEnabled ? "#00F0FF" : "#8BABC6",
                borderColor: voiceEnabled ? "rgba(0,240,255,0.5)" : "rgba(139,171,198,0.3)",
                background: voiceEnabled ? "rgba(0,240,255,0.08)" : "transparent",
              }}
              data-testid="tts-toggle-btn"
            >
              tts {voiceEnabled ? "on" : "off"}
            </button>
            <span className="text-[10px] tracking-[0.3em] uppercase text-[#8BABC6]">
              try: "buy 0.1 btc", "what's tsla doing", "schedule sync friday"
            </span>
          </div>
          <CommandPalette
            onSend={handleCommand}
            busy={busy}
            listening={speech.listening}
            onToggleVoice={toggleVoice}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
