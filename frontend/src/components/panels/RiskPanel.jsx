import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { ShieldAlert, Power } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const RiskPanel = ({ delay = 0, onChange }) => {
  const [risk, setRisk] = useState(null);
  const [maxPos, setMaxPos] = useState("");
  const [maxLoss, setMaxLoss] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/bot/risk`);
      setRisk(r.data);
      setMaxPos(String(r.data.max_position_notional));
      setMaxLoss(String(r.data.max_daily_loss));
    } catch {}
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/bot/risk`, {
        max_position_notional: parseFloat(maxPos),
        max_daily_loss: parseFloat(maxLoss),
      });
      setRisk(r.data);
      toast.success("risk limits updated");
      onChange?.();
    } catch (e) {
      toast.error("update failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleKill = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/bot/risk`, { kill_switch: !risk?.kill_switch });
      setRisk(r.data);
      toast(r.data.kill_switch ? "🛑 KILL SWITCH ON" : "✅ trading resumed", {
        description: r.data.kill_switch ? "all new orders blocked" : "risk gate re-opened",
      });
      onChange?.();
    } finally {
      setBusy(false);
    }
  };

  if (!risk) return null;
  const killOn = !!risk.kill_switch;

  return (
    <Panel title="RISK · GATE" subtitle="active" icon={ShieldAlert} delay={delay} testId="panel-risk" accent="magenta">
      <div className="space-y-3">
        <div>
          <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6] mb-1">
            max position notional
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[#8BABC6] text-xs">$</span>
            <input
              type="number"
              value={maxPos}
              onChange={(e) => setMaxPos(e.target.value)}
              className="flex-1 bg-transparent border border-[#00F0FF]/30 rounded px-2 py-1 text-xs text-white outline-none"
              data-testid="max-pos-input"
            />
          </div>
        </div>
        <div>
          <div className="text-[9px] tracking-[0.3em] uppercase text-[#8BABC6] mb-1">
            max daily loss
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[#8BABC6] text-xs">$</span>
            <input
              type="number"
              value={maxLoss}
              onChange={(e) => setMaxLoss(e.target.value)}
              className="flex-1 bg-transparent border border-[#00F0FF]/30 rounded px-2 py-1 text-xs text-white outline-none"
              data-testid="max-loss-input"
            />
          </div>
        </div>
        <button
          onClick={save}
          disabled={busy}
          className="w-full py-1.5 rounded-md font-display text-[10px] tracking-[0.3em] uppercase disabled:opacity-40"
          style={{ background: "rgba(0,240,255,0.12)", color: "#00F0FF", border: "1px solid rgba(0,240,255,0.4)" }}
          data-testid="save-risk-btn"
        >
          save limits
        </button>

        <button
          onClick={toggleKill}
          disabled={busy}
          className="w-full py-2 rounded-md font-display text-[11px] tracking-[0.3em] uppercase disabled:opacity-40 flex items-center justify-center gap-2 transition-all"
          style={{
            background: killOn ? "#FF007F" : "transparent",
            color: killOn ? "#fff" : "#FF007F",
            border: "1px solid #FF007F",
            boxShadow: killOn ? "0 0 18px rgba(255,0,127,0.5)" : "none",
          }}
          data-testid="kill-switch-btn"
        >
          <Power size={12} /> {killOn ? "kill switch · ON" : "engage kill switch"}
        </button>
      </div>
    </Panel>
  );
};

export default RiskPanel;
