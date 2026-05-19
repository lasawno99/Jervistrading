import React, { useCallback, useEffect, useRef, useState } from "react";
import "@/App.css";
import "@/index.css";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { Toaster, toast } from "sonner";

import TopHeader from "@/components/v2/TopHeader";
import HeroMetricsRow from "@/components/v2/HeroMetricsRow";
import TodayProfitHero from "@/components/v2/TodayProfitHero";
import BrokerCarousel from "@/components/v2/BrokerCarousel";
import MarketPulseStrip from "@/components/v2/MarketPulseStrip";
import TradingPeersCluster from "@/components/v2/TradingPeersCluster";
import AgentStatusCard from "@/components/v2/AgentStatusCard";
import AutomationCard from "@/components/v2/AutomationCard";
import TopSignalsCard from "@/components/v2/TopSignalsCard";
import OpenPositionsTable from "@/components/v2/OpenPositionsTable";
import RecentTradesTable from "@/components/v2/RecentTradesTable";
import BotBrainPanel from "@/components/v2/BotBrainPanel";
import WinRateTrendCard from "@/components/v2/WinRateTrendCard";
import AskJarvisModal from "@/components/v2/AskJarvisModal";
import BottomNav from "@/components/v2/BottomNav";

import { MultiBrokerHero } from "@/components/panels/BrokerHeroPanel";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

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

export default function App() {
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [tab, setTab] = useState("dashboard");
  const [askOpen, setAskOpen] = useState(false);
  const [lastReply, setLastReply] = useState("");
  const [voiceEnabled] = useState(true);

  const handleCommand = useCallback(async (text) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/jarvis/chat`, {
        message: text,
        session_id: sessionId || "dashboard-default",
      });
      setSessionId(r.data.session_id);
      setLastReply(r.data.reply || "");
      toast("JARVIS", { description: r.data.reply });
      if (voiceEnabled) speak(r.data.reply);
    } catch (e) {
      toast.error("Command failed", { description: String(e?.message || e) });
    } finally {
      setBusy(false);
    }
  }, [sessionId, voiceEnabled]);

  const onVoiceResult = useCallback((text) => { handleCommand(text); }, [handleCommand]);
  const speech = useSpeechRecognition(onVoiceResult);

  const toggleVoice = () => {
    if (!speech.supported) { toast.error("Voice not supported"); return; }
    if (speech.listening) speech.stop(); else speech.start();
  };

  const onPeerSelect = (node) => {
    if (node.kind === "asset") {
      toast(node.label || node.id, {
        description: `${node.name || node.id} · ${node.status || "watching"}`,
      });
    } else {
      toast(node.name || node.id, { description: node.role || "Agent online" });
    }
  };

  return (
    <div className="relative min-h-screen bg-grain" data-testid="jarvis-app-v2">
      {/* Background gradients */}
      <div
        className="fixed inset-0 z-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(120% 80% at 80% -10%, rgba(108,141,255,0.10) 0%, transparent 50%), radial-gradient(80% 60% at 10% 110%, rgba(155,123,255,0.08) 0%, transparent 55%)",
        }}
      />

      <Toaster
        theme="dark"
        position="top-center"
        toastOptions={{
          style: {
            background: "rgba(20,20,28,0.92)",
            border: "1px solid var(--border-hi)",
            color: "#fff",
            backdropFilter: "blur(16px)",
          },
        }}
      />

      <div className="relative z-10 max-w-[1400px] mx-auto pb-24">
        <TopHeader />

        <AnimatePresence mode="wait">
          <motion.main
            key={tab}
            className="px-4 md:px-6 pt-1"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            data-testid={`tab-${tab}`}
          >
            {tab === "dashboard" && (
              <div className="space-y-3">
                <TodayProfitHero />
                <MarketPulseStrip />
                <TradingPeersCluster onSelect={onPeerSelect} />
                <BrokerCarousel />
              </div>
            )}

            {tab === "portfolio" && (
              <div className="space-y-5 pt-2">
                <div>
                  <h2 className="text-[22px] font-semibold tracking-tight">Portfolio</h2>
                  <p className="text-[13px] text-white/45 mt-1">
                    Live across all connected brokers — OANDA forex, Alpaca stocks &amp; crypto, JARVIS Sim Desk.
                  </p>
                </div>
                <HeroMetricsRow />
                <MultiBrokerHero />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <OpenPositionsTable />
                  <RecentTradesTable />
                </div>
              </div>
            )}

            {tab === "agents" && (
              <div className="space-y-5 pt-2">
                <div>
                  <h2 className="text-[22px] font-semibold tracking-tight">Agents</h2>
                  <p className="text-[13px] text-white/45 mt-1">
                    Watch each pipeline layer think in real time.
                  </p>
                </div>
                <WinRateTrendCard delay={0.05} />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  <AgentStatusCard delay={0.1} />
                  <AutomationCard delay={0.15} />
                  <TopSignalsCard delay={0.2} />
                </div>
                <BotBrainPanel delay={0.25} />
              </div>
            )}

            {tab === "settings" && (
              <div className="space-y-5 pt-2">
                <h2 className="text-[22px] font-semibold tracking-tight">Settings</h2>
                <div className="card p-6">
                  <p className="text-[13px] text-white/50">
                    Configuration UI coming soon. Variables are managed via Railway and the backend <code>.env</code>.
                  </p>
                </div>
              </div>
            )}
          </motion.main>
        </AnimatePresence>
      </div>

      {/* Bottom Nav (no persistent ask-bar — that's now triggered by the "+" button) */}
      <div
        className="fixed bottom-0 left-0 right-0 z-40 pointer-events-none"
        style={{
          background:
            "linear-gradient(to top, rgba(11,11,16,0.96) 0%, rgba(11,11,16,0.55) 60%, transparent 100%)",
          paddingTop: 24,
        }}
      >
        <div
          className="max-w-xl mx-auto px-4 pt-2 pointer-events-auto"
          style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
        >
          <BottomNav
            active={tab}
            onChange={setTab}
            onCreate={() => setAskOpen(true)}
          />
        </div>
      </div>

      <AskJarvisModal
        open={askOpen}
        onClose={() => setAskOpen(false)}
        onSend={handleCommand}
        busy={busy}
        listening={speech.listening}
        onToggleVoice={toggleVoice}
        lastReply={lastReply}
      />
    </div>
  );
}
