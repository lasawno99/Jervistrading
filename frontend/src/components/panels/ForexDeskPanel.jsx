import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Banknote, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PAIRS = ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "AUD_USD", "USD_CAD", "NZD_USD", "EUR_GBP", "XAU_USD"];

export const ForexDeskPanel = ({ delay = 0 }) => {
  const [status, setStatus] = useState(null);
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [prices, setPrices] = useState({});
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  const loadStatus = async () => {
    try {
      const [s, a, p] = await Promise.all([
        axios.get(`${API}/forex/status`),
        axios.get(`${API}/forex/account`),
        axios.get(`${API}/forex/positions`),
      ]);
      setStatus(s.data);
      setAccount(a.data);
      setPositions(p.data.positions || []);
    } catch {}
  };

  const loadPrices = async () => {
    try {
      const top = ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"];
      const res = await Promise.all(top.map((p) => axios.get(`${API}/forex/price`, { params: { instrument: p } })));
      const map = {};
      top.forEach((p, i) => { map[p] = res[i].data; });
      setPrices(map);
    } catch {}
  };

  useEffect(() => {
    loadStatus();
    loadPrices();
    const t1 = setInterval(loadStatus, 8000);
    const t2 = setInterval(loadPrices, 5000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const send = async (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setBusy(true);
    try {
      const r = await axios.post(`${API}/forex/chat`, { message: text, session_id: sessionId });
      setSessionId(r.data.session_id);
      setMessages((m) => [...m, { role: "assistant", content: r.data.reply }]);
      loadStatus();
    } catch (err) {
      toast.error("forex chat failed", { description: err?.message });
    } finally {
      setBusy(false);
    }
  };

  const quickPrompt = (text) => {
    setInput(text);
  };

  const clearChat = async () => {
    if (sessionId) {
      try { await axios.delete(`${API}/forex/chat/${sessionId}`); } catch {}
    }
    setMessages([]);
    setSessionId(null);
  };

  const claudeOk = status?.anthropic_configured;
  const oandaOk = status?.oanda_configured;

  return (
    <Panel title="FOREX · DESK" subtitle={status?.env || "practice"} icon={Banknote} delay={delay} testId="panel-forex" accent="amber">
      <div className="space-y-3">
        {/* Status badges */}
        <div className="grid grid-cols-2 gap-2 text-center">
          <div className="border border-[#00F0FF]/15 rounded p-1.5">
            <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">claude</div>
            <div className="font-display text-[11px]" style={{ color: claudeOk ? "#27C93F" : "#FFB000" }}>
              {claudeOk ? "● online" : "○ no key"}
            </div>
          </div>
          <div className="border border-[#00F0FF]/15 rounded p-1.5">
            <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">oanda</div>
            <div className="font-display text-[11px]" style={{ color: oandaOk ? "#27C93F" : "#FFB000" }}>
              {oandaOk ? "● connected" : "○ mock"}
            </div>
          </div>
        </div>

        {/* Mini quotes strip */}
        <div className="grid grid-cols-2 gap-1 text-[10px]">
          {Object.entries(prices).map(([k, v]) => (
            <div key={k} className="flex justify-between border border-[#00F0FF]/10 rounded px-2 py-1" data-testid={`fx-${k}`}>
              <span className="text-[#8BABC6]">{k}</span>
              <span className="text-white font-mono">{v.bid?.toFixed(k === "XAU_USD" ? 2 : 4)}</span>
            </div>
          ))}
        </div>

        {/* Account snapshot */}
        {account && !account.error && (
          <div className="border-t border-[#00F0FF]/15 pt-2 grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">balance</div>
              <div className="font-display text-xs text-white">${Number(account.balance).toLocaleString()}</div>
            </div>
            <div>
              <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">unreal P/L</div>
              <div className="font-display text-xs" style={{ color: (account.unrealized_pl || 0) >= 0 ? "#27C93F" : "#FF5F56" }}>
                ${Number(account.unrealized_pl || 0).toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-[9px] tracking-[0.2em] uppercase text-[#8BABC6]">positions</div>
              <div className="font-display text-xs text-white">{account.open_position_count ?? positions.length}</div>
            </div>
          </div>
        )}

        {/* Open positions */}
        {positions.length > 0 && (
          <div className="border-t border-[#00F0FF]/15 pt-2 space-y-1">
            <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">open</div>
            {positions.map((p, i) => (
              <div key={i} className="flex justify-between text-[11px]" data-testid={`fx-pos-${p.instrument}`}>
                <span className="text-white">{p.instrument} <span className="text-[#8BABC6]">{p.net_units > 0 ? "long" : "short"} {Math.abs(p.net_units)}</span></span>
                <span style={{ color: p.unrealized_pl >= 0 ? "#27C93F" : "#FF5F56" }}>
                  ${p.unrealized_pl?.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Chat */}
        <div className="border-t border-[#00F0FF]/15 pt-2">
          <div className="flex items-center justify-between mb-1">
            <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6]">claude · forex agent</div>
            {messages.length > 0 && (
              <button onClick={clearChat} className="text-[#8BABC6] hover:text-white" title="clear" data-testid="forex-clear-btn">
                <Trash2 size={10} />
              </button>
            )}
          </div>

          <div ref={scrollRef} className="jv-scroll overflow-y-auto space-y-2 mb-2" style={{ maxHeight: 200 }}>
            {messages.length === 0 && (
              <div className="text-[10px] text-[#8BABC6] italic">
                ↳ try: "what's EUR/USD doing?", "buy 1000 EUR_USD with 30 pip stop"
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className="text-[11px] leading-snug" data-testid={`forex-msg-${i}`}>
                <span className={m.role === "user" ? "text-[#00F0FF]" : "text-[#FFB000]"}>
                  {m.role === "user" ? "you ▸" : "claude ▸"}
                </span>{" "}
                <span className="text-white whitespace-pre-wrap">{m.content}</span>
              </div>
            ))}
            {busy && <div className="text-[11px] text-[#FFB000] italic">claude ▸ thinking<span className="caret">_</span></div>}
          </div>

          <div className="flex flex-wrap gap-1 mb-2">
            {["EUR/USD price", "show account", "open positions"].map((t) => (
              <button
                key={t}
                onClick={() => quickPrompt(t)}
                className="text-[9px] px-2 py-0.5 rounded-full border border-[#00F0FF]/30 text-[#8BABC6] hover:text-white hover:border-[#00F0FF]/60"
                data-testid={`fx-quick-${t}`}
              >
                {t}
              </button>
            ))}
          </div>

          <form onSubmit={send} className="flex gap-1">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={claudeOk ? "ask claude…" : "ANTHROPIC_API_KEY needed"}
              disabled={!claudeOk || busy}
              className="flex-1 bg-transparent border border-[#00F0FF]/30 rounded px-2 py-1 text-[11px] text-white outline-none placeholder:text-[#8BABC6] disabled:opacity-50"
              data-testid="forex-input"
            />
            <button
              type="submit"
              disabled={!claudeOk || busy || !input.trim()}
              className="px-2 py-1 rounded text-[11px] disabled:opacity-40"
              style={{ background: "#FFB000", color: "#050B14" }}
              data-testid="forex-send-btn"
            >
              <Send size={11} />
            </button>
          </form>
        </div>

        {(!claudeOk || !oandaOk) && (
          <div className="text-[9px] text-[#FFB000] leading-snug border-t border-[#FFB000]/20 pt-2">
            ⚠ Configure {!claudeOk && <code className="text-white">ANTHROPIC_API_KEY</code>}
            {!claudeOk && !oandaOk && " + "}
            {!oandaOk && <><code className="text-white">OANDA_API_TOKEN</code>, <code className="text-white">OANDA_ACCOUNT_ID</code></>}
            {" "}in backend/.env, then restart backend.
          </div>
        )}
      </div>
    </Panel>
  );
};

export default ForexDeskPanel;
