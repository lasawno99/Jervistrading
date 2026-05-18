import React, { useCallback, useEffect, useRef, useState } from "react";
import "@/App.css";
import "@/index.css";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { Toaster, toast } from "sonner";

import TopHeader from "@/components/v2/TopHeader";
import HeroMetricsRow from "@/components/v2/HeroMetricsRow";
import ChartCard from "@/components/v2/ChartCard";
import TradingPeersCluster from "@/components/v2/TradingPeersCluster";
import AgentStatusCard from "@/components/v2/AgentStatusCard";
import AutomationCard from "@/components/v2/AutomationCard";
import TopSignalsCard from "@/components/v2/TopSignalsCard";
import OpenPositionsTable from "@/components/v2/OpenPositionsTable";
import RecentTradesTable from "@/components/v2/RecentTradesTable";
import AskJarvisBar from "@/components/v2/AskJarvisBar";
import BottomNav from "@/components/v2/BottomNav";

// Keep the existing 3-broker stack accessible behind the Portfolio tab
import { MultiBrokerHero } from "@/components/panels/BrokerHeroPanel";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ASSET_DEFAULTS = {
  BTC: { name: "Bitcoin", anchor: 80000 },
  ETH: { name: "Ethereum", anchor: 3800 },
  NVDA: { name: "NVIDIA", anchor: 215 },
  TSLA: { name: "Tesla", anchor: 248 },
  OIL: { name: "WTI Crude", anchor: 116 },
  KIMI: { name: "Kimi Agent", anchor: 100 },
  CLDE: { name: "Claude Agent", anchor: 100 },
  KRNS: { name: "Kronos Predictor", anchor: 100 },
};

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
  const [chartFocus, setChartFocus] = useState({ symbol: "BTC", ...ASSET_DEFAULTS.BTC });
  const [voiceEnabled] = useState(true);

  const handleCommand = useCallback(async (text) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/jarvis/chat`, {
        message: text,
        session_id: sessionId || "dashboard-default",
      });
      setSessionId(r.data.session_id);
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
    const def = ASSET_DEFAULTS[node.id] || { name: node.name || node.id, anchor: 100 };
    if (node.kind === "asset") {
      setChartFocus({ symbol: node.id, name: def.name, anchor: def.anchor });
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

      <div className="relative z-10 max-w-[1400px] mx-auto pb-44 lg:pb-32">
        <TopHeader />

        <AnimatePresence mode="wait">
          <motion.main
            key={tab}
            className="px-4 md:px-6 pt-2 space-y-5"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            {tab === "dashboard" && (
              <>
                <HeroMetricsRow />

                {/* Main workspace: chart (left) + peers cluster (right) */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                  <div className="lg:col-span-7 xl:col-span-8">
                    <ChartCard
                      symbol={chartFocus.symbol}
                      name={chartFocus.name}
                      anchor={chartFocus.anchor}
                    />
                  </div>
                  <div className="lg:col-span-5 xl:col-span-4">
                    <TradingPeersCluster onSelect={onPeerSelect} />
                  </div>
                </div>

                {/* Three small cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  <AgentStatusCard />
                  <AutomationCard />
                  <TopSignalsCard />
                </div>

                {/* Tables */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <OpenPositionsTable />
                  <RecentTradesTable />
                </div>
              </>
            )}

            {tab === "portfolio" && (
              <div className="space-y-5 pt-2">
                <div>
                  <h2 className="text-[22px] font-semibold tracking-tight">Portfolio</h2>
                  <p className="text-[13px] text-white/45 mt-1">
                    Live across all connected brokers — OANDA forex, Alpaca stocks &amp; crypto, and the JARVIS Sim Desk.
                  </p>
                </div>
                <MultiBrokerHero />
              </div>
            )}

            {tab === "agents" && (
              <div className="space-y-5 pt-2">
                <div>
                  <h2 className="text-[22px] font-semibold tracking-tight">Agents</h2>
                  <p className="text-[13px] text-white/45 mt-1">
                    Connected services keeping the system running.
                  </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  <AgentStatusCard delay={0.05} />
                  <AutomationCard delay={0.1} />
                  <TopSignalsCard delay={0.15} />
                </div>
              </div>
            )}

            {tab === "settings" && (
              <div className="space-y-5 pt-2">
                <h2 className="text-[22px] font-semibold tracking-tight">Settings</h2>
                <div className="card p-6">
                  <p className="text-[13px] text-white/50">
                    Configuration UI coming soon. Variables are managed via Railway and the backend `.env`.
                  </p>
                </div>
              </div>
            )}
          </motion.main>
        </AnimatePresence>
      </div>

      {/* Floating Ask Jarvis bar + Bottom Nav */}
      <div
        className="fixed bottom-0 left-0 right-0 z-40 pointer-events-none"
        style={{
          background:
            "linear-gradient(to top, rgba(11,11,16,0.95) 0%, rgba(11,11,16,0.55) 55%, transparent 100%)",
          paddingTop: 32,
        }}
      >
        <div className="max-w-3xl mx-auto px-4 pb-2 pointer-events-auto">
          <AskJarvisBar
            onSend={handleCommand}
            busy={busy}
            listening={speech.listening}
            onToggleVoice={toggleVoice}
          />
        </div>
        <div className="max-w-xl mx-auto px-4 pb-4 pt-2 pointer-events-auto">
          <BottomNav
            active={tab}
            onChange={setTab}
            onCreate={() => toast("Quick action", { description: "Quick-add coming soon" })}
          />
        </div>
      </div>
    </div>
  );
}
