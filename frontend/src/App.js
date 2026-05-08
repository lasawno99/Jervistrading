import React, { useCallback, useEffect, useRef, useState } from "react";
import "@/App.css";
import "@/index.css";
import axios from "axios";
import { motion } from "framer-motion";
import { Toaster, toast } from "sonner";
import JarvisOrb from "@/components/JarvisOrb";
import CommandPalette from "@/components/CommandPalette";
import BrokerHeroPanel, { MultiBrokerHero } from "@/components/panels/BrokerHeroPanel";
import TradingPanel from "@/components/panels/TradingPanel";
import TwitterPanel from "@/components/panels/TwitterPanel";
import CalendarPanel from "@/components/panels/CalendarPanel";
import NewsPanel from "@/components/panels/NewsPanel";
import BotPositionsPanel from "@/components/panels/BotPositionsPanel";
import BotSignalsPanel from "@/components/panels/BotSignalsPanel";
import BotControlPanel from "@/components/panels/BotControlPanel";
import RiskPanel from "@/components/panels/RiskPanel";
import ForexDeskPanel from "@/components/panels/ForexDeskPanel";
import JarvisInboxPanel from "@/components/panels/JarvisInboxPanel";
import { Activity, Cpu, Radio, Wifi } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

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
    r.onresult = (e) => onResult(e.results[0][0].transcript);
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recRef.current = r;
    setSupported(true);
  }, [onResult]);

  const start = () => {
    if (!recRef.current) return;
    try {
      recRef.current.start();
      setListening(true);
    } catch {}
  };
  const stop = () => {
    if (!recRef.current) return;
    try {
      recRef.current.stop();
    } catch {}
    setListening(false);
  };

  return { supported, listening, start, stop };
}

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    u.pitch = 0.85;
    u.volume = 0.9;
    window.speechSynthesis.speak(u);
  } catch {}
}

function App() {
  const [orbState, setOrbState] = useState("idle");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [lastReply, setLastReply] = useState(
    "Standing by. Issue a command via voice, text, or Telegram."
  );
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [serviceInfo, setServiceInfo] = useState(null);
  const clock = useClock();

  const bumpRefresh = () => setRefreshKey((k) => k + 1);

  useEffect(() => {
    axios
      .get(`${API}/`)
      .then((r) => setServiceInfo(r.data))
      .catch(() => {});
  }, []);

  const handleCommand = useCallback(
    async (text) => {
      setBusy(true);
      setOrbState("thinking");
      try {
        const r = await axios.post(`${API}/jarvis/chat`, {
          message: text,
          session_id: sessionId || "dashboard-default",
        });
        setSessionId(r.data.session_id);
        setLastReply(r.data.reply);
        toast("JARVIS · responded", { description: r.data.reply.slice(0, 140) });
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
    (text) => {
      setOrbState("thinking");
      handleCommand(text);
    },
    [handleCommand]
  );

  const speech = useSpeechRecognition(onVoiceResult);

  const toggleVoice = () => {
    if (!speech.supported) {
      toast.error("Voice not supported in this browser");
      return;
    }
    if (speech.listening) {
      speech.stop();
      setOrbState("idle");
    } else {
      speech.start();
      setOrbState("listening");
    }
  };

  return (
    <div className="App grain relative min-h-screen overflow-hidden" data-testid="jarvis-app">
      {/* Background — radial spotlight, no image */}
      <div
        className="fixed inset-0 z-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(120% 80% at 50% -10%, rgba(123,97,255,0.10) 0%, rgba(0,229,255,0.04) 30%, transparent 60%)",
        }}
      />
      <div
        className="fixed inset-0 z-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(60% 40% at 50% 100%, rgba(0,229,255,0.05) 0%, transparent 60%)",
        }}
      />

      <Toaster
        theme="dark"
        position="top-center"
        toastOptions={{
          style: {
            background: "rgba(10,10,10,0.92)",
            border: "1px solid rgba(255,255,255,0.12)",
            color: "#fff",
            backdropFilter: "blur(16px)",
          },
        }}
      />

      {/* Top bar */}
      <header
        className="relative z-30 flex items-center justify-between px-6 md:px-10 py-4 border-b border-white/[0.06]"
        data-testid="hud-top"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg border border-white/10 flex items-center justify-center bg-white/[0.03]">
            <Activity size={13} className="text-white/80" />
          </div>
          <div>
            <div className="font-heading text-base tracking-tight text-white">
              Jarvis
            </div>
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/35">
              command center · paper desk · 24/7
            </div>
          </div>
        </div>

        <div className="hidden lg:flex items-center gap-7 font-mono text-[10px] tracking-[0.22em] uppercase text-white/45">
          <div className="flex items-center gap-2">
            <Wifi
              size={12}
              style={{ color: serviceInfo?.kimi_active ? "#00ff85" : "#ffb020" }}
            />
            <span>kimi {serviceInfo?.kimi_active ? "online" : "fallback"}</span>
          </div>
          <div className="flex items-center gap-2">
            <Radio
              size={12}
              style={{
                color: serviceInfo?.telegram_configured ? "#00ff85" : "#ff3b6e",
              }}
            />
            <span>tg {serviceInfo?.telegram_configured ? "linked" : "offline"}</span>
          </div>
          <div className="flex items-center gap-2">
            <Cpu size={12} className="text-white/60" />
            <span>cores · 32B</span>
          </div>
        </div>

        <div
          className="font-mono text-sm tracking-[0.18em] text-white/85 tabular"
          data-testid="hud-clock"
        >
          {clock.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </div>
      </header>

      {/* Main grid */}
      <main className="relative z-20 px-4 md:px-8 lg:px-10 pt-7 pb-44 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-12 gap-5 lg:gap-6">
          {/* Left rail */}
          <aside className="col-span-12 lg:col-span-3 flex flex-col gap-5">
            <BotPositionsPanel delay={120} refreshKey={refreshKey} />
            <BotControlPanel delay={220} onChange={bumpRefresh} />
            <RiskPanel delay={320} onChange={bumpRefresh} />
            <CalendarPanel delay={420} />
          </aside>

          {/* Center stage */}
          <section className="col-span-12 lg:col-span-6 flex flex-col gap-6">
            <MultiBrokerHero refreshKey={refreshKey} />

            <motion.div
              className="relative flex flex-col items-center pt-4"
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.65, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
            >
              <JarvisOrb state={orbState} size={240} />

              <div className="mt-14 max-w-xl text-center px-4">
                <div className="font-mono text-[10px] tracking-[0.34em] uppercase text-white/35 mb-2">
                  last response
                </div>
                <div
                  className="font-sans text-sm md:text-base text-white/90 leading-relaxed whitespace-pre-wrap"
                  data-testid="last-reply"
                >
                  {lastReply}
                  <span className="caret text-white/55"> ▌</span>
                </div>
              </div>
            </motion.div>

            <JarvisInboxPanel delay={250} refreshKey={refreshKey} />
            <BotSignalsPanel delay={350} onChange={bumpRefresh} />
          </section>

          {/* Right rail */}
          <aside className="col-span-12 lg:col-span-3 flex flex-col gap-5">
            <TradingPanel delay={120} />
            <ForexDeskPanel delay={220} />
            <TwitterPanel delay={320} />
            <NewsPanel delay={420} />
          </aside>
        </div>
      </main>

      {/* Floating command palette */}
      <div
        className="fixed bottom-0 left-0 right-0 z-40 px-4 pb-6 pt-12 pointer-events-none"
        style={{
          background:
            "linear-gradient(to top, rgba(5,5,5,0.95) 0%, rgba(5,5,5,0.6) 60%, transparent 100%)",
        }}
      >
        <div className="max-w-3xl mx-auto pointer-events-auto flex flex-col items-center gap-3">
          <div className="flex items-center gap-3 flex-wrap justify-center">
            <button
              onClick={() => setVoiceEnabled((v) => !v)}
              className="font-mono text-[10px] tracking-[0.28em] uppercase px-3 py-1 rounded-full border transition-colors"
              style={{
                color: voiceEnabled ? "#fff" : "rgba(255,255,255,0.45)",
                borderColor: voiceEnabled
                  ? "rgba(255,255,255,0.22)"
                  : "rgba(255,255,255,0.10)",
                background: voiceEnabled ? "rgba(255,255,255,0.05)" : "transparent",
              }}
              data-testid="tts-toggle-btn"
            >
              tts {voiceEnabled ? "on" : "off"}
            </button>
            <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-white/30">
              try: "what's my day", "buy 0.05 btc", "remind me at 4pm"
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
