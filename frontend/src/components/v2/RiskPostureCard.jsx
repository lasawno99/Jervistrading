import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Shield, TrendingDown, TrendingUp, Check, X, AlertTriangle } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtUsd = (v) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(
    Number.isFinite(v) ? v : 0
  );

const CapabilityChip = ({ enabled, label, sub }) => (
  <div
    className="flex items-center gap-2 px-2.5 py-2 rounded-xl"
    style={{
      background: enabled ? "rgba(34,197,94,0.08)" : "rgba(255,255,255,0.03)",
      border: `1px solid ${enabled ? "rgba(34,197,94,0.24)" : "rgba(255,255,255,0.07)"}`,
    }}
  >
    <span
      className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
      style={{
        background: enabled ? "rgba(34,197,94,0.20)" : "rgba(255,255,255,0.06)",
        color: enabled ? "var(--up)" : "var(--text-3)",
      }}
    >
      {enabled ? <Check size={11} strokeWidth={3} /> : <X size={11} strokeWidth={3} />}
    </span>
    <div className="min-w-0">
      <div className="text-[11px] font-semibold leading-tight">{label}</div>
      <div className="text-[10px] text-white/45 leading-tight truncate">{sub}</div>
    </div>
  </div>
);

const ProtectionRow = ({ label, value, sub, severity = "ok" }) => {
  const c = {
    ok: { dot: "var(--up)", bg: "rgba(34,197,94,0.10)" },
    warn: { dot: "var(--warn)", bg: "rgba(245,158,11,0.10)" },
    danger: { dot: "var(--down)", bg: "rgba(239,68,68,0.10)" },
  }[severity];
  return (
    <div
      className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg"
      style={{ background: c.bg, border: "1px solid rgba(255,255,255,0.04)" }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: c.dot }} />
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-white/85 leading-tight">{label}</div>
          {sub && <div className="text-[10px] text-white/45 leading-tight">{sub}</div>}
        </div>
      </div>
      <div className="text-[12px] tabular font-semibold flex-shrink-0" style={{ color: c.dot }}>
        {value}
      </div>
    </div>
  );
};

export const RiskPostureCard = ({ delay = 0.1 }) => {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/risk/posture`, { timeout: 10000 });
        if (alive) setData(r.data);
      } catch {}
    };
    load();
    const t = setInterval(load, 60000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!data) {
    return (
      <section className="card p-5" data-testid="risk-posture-card">
        <div className="text-[12px] text-white/35">Loading risk posture…</div>
      </section>
    );
  }

  const dc = data.downside_capability;
  const prot = data.protections;
  const exp = data.current_exposure;
  const gaps = data.improvement_gaps || [];

  const budgetUsedPct = prot.daily_loss_halt.budget_used_pct;
  const budgetSeverity = budgetUsedPct >= 80 ? "danger" : budgetUsedPct >= 50 ? "warn" : "ok";

  return (
    <motion.section
      className="card p-5"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      data-testid="risk-posture-card"
    >
      <header className="flex items-center gap-2.5 mb-4">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: "rgba(108,141,255,0.18)", color: "var(--accent-1)" }}
        >
          <Shield size={15} />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold tracking-tight leading-none">Risk Posture</h3>
          <div className="text-[11px] text-white/40 mt-0.5">
            Can we make money going down? Is risk managed? — Live audit.
          </div>
        </div>
      </header>

      {/* Downside capability */}
      <div className="mb-4">
        <div className="text-[10px] tracking-[0.12em] uppercase text-white/40 mb-2 flex items-center gap-1.5">
          <TrendingDown size={11} /> Downside Earning Capability
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" data-testid="downside-capability">
          <CapabilityChip enabled={dc.forex_short.enabled} label="Forex SHORT" sub={dc.forex_short.via} />
          <CapabilityChip enabled={dc.stocks_short.enabled} label="Stocks SHORT" sub={dc.stocks_short.via} />
          <CapabilityChip enabled={dc.crypto_short.enabled} label="Crypto SHORT" sub={dc.crypto_short.reason || "Long-only"} />
        </div>
        <div className="mt-2 text-[10px] text-white/45 flex flex-wrap gap-x-3 gap-y-1">
          <span>Kronos predicts down moves: <strong style={{ color: dc.kronos_predicts_downside ? "var(--up)" : "var(--down)" }}>{dc.kronos_predicts_downside ? "YES" : "NO"}</strong></span>
          <span>Tauric votes SHORT: <strong style={{ color: dc.tauric_supports_short ? "var(--up)" : "var(--down)" }}>{dc.tauric_supports_short ? "YES" : "NO"}</strong></span>
        </div>
      </div>

      {/* Active protections */}
      <div className="mb-4">
        <div className="text-[10px] tracking-[0.12em] uppercase text-white/40 mb-2 flex items-center gap-1.5">
          <Shield size={11} /> Active Protections
        </div>
        <div className="space-y-1.5" data-testid="active-protections">
          <ProtectionRow
            label="Risk-Off Gate"
            sub={prot.risk_off_gate.reason}
            value={prot.risk_off_gate.active ? "ACTIVE" : "STANDBY"}
            severity={prot.risk_off_gate.active ? "warn" : "ok"}
          />
          <ProtectionRow
            label="Profit Lock"
            sub={`Every +${prot.profit_lock.threshold_pct}% NAV → swept to ledger`}
            value={fmtUsd(prot.profit_lock.total_locked)}
            severity="ok"
          />
          <ProtectionRow
            label="Daily Loss Budget"
            sub={`${budgetUsedPct.toFixed(1)}% used · ${fmtUsd(prot.daily_loss_halt.budget_remaining_usd)} remaining`}
            value={`${prot.daily_loss_halt.limit_pct}%`}
            severity={budgetSeverity}
          />
          <ProtectionRow
            label="Confidence Floor"
            sub="Tauric ≥7/10 + Kronos ≥medium"
            value="STRICT"
            severity="ok"
          />
          <ProtectionRow
            label="Min Risk:Reward"
            sub="Take-profit always ≥2× stop-loss"
            value="2.0–3.0×"
            severity="ok"
          />
        </div>
      </div>

      {/* Current exposure */}
      <div className="mb-4">
        <div className="text-[10px] tracking-[0.12em] uppercase text-white/40 mb-2">Current Exposure</div>
        <div className="grid grid-cols-3 gap-2" data-testid="current-exposure">
          <div className="px-2 py-2 rounded-lg" style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)" }}>
            <div className="text-[10px] text-white/45 flex items-center gap-1"><TrendingUp size={10} /> LONG</div>
            <div className="text-[16px] font-semibold tabular" style={{ color: "var(--up)" }}>{exp.open_long_positions}</div>
            <div className="text-[10px] text-white/45 tabular">{fmtUsd(exp.long_notional)}</div>
          </div>
          <div className="px-2 py-2 rounded-lg" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)" }}>
            <div className="text-[10px] text-white/45 flex items-center gap-1"><TrendingDown size={10} /> SHORT</div>
            <div className="text-[16px] font-semibold tabular" style={{ color: "var(--down)" }}>{exp.open_short_positions}</div>
            <div className="text-[10px] text-white/45 tabular">{fmtUsd(exp.short_notional)}</div>
          </div>
          <div className="px-2 py-2 rounded-lg" style={{ background: "rgba(108,141,255,0.08)", border: "1px solid rgba(108,141,255,0.2)" }}>
            <div className="text-[10px] text-white/45">Bias</div>
            <div className="text-[13px] font-semibold mt-0.5 uppercase tracking-wide" style={{ color: "var(--accent-1)" }}>
              {exp.directional_bias.replace("-", " ")}
            </div>
          </div>
        </div>
      </div>

      {/* Improvement gaps */}
      {gaps.length > 0 && (
        <div>
          <div className="text-[10px] tracking-[0.12em] uppercase text-white/40 mb-2 flex items-center gap-1.5">
            <AlertTriangle size={11} /> Improvement Opportunities ({gaps.length})
          </div>
          <div className="space-y-1.5" data-testid="improvement-gaps">
            {gaps.map((g) => (
              <details key={g.id} className="group">
                <summary
                  className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg cursor-pointer"
                  style={{
                    background: "rgba(245,158,11,0.06)",
                    border: "1px solid rgba(245,158,11,0.18)",
                  }}
                >
                  <span className="text-[12px] font-medium text-white/90">{g.label}</span>
                  <span
                    className="text-[9px] tracking-[0.1em] uppercase px-1.5 py-0.5 rounded font-semibold"
                    style={{
                      background: g.impact === "high" ? "rgba(239,68,68,0.18)" : "rgba(245,158,11,0.18)",
                      color: g.impact === "high" ? "var(--down)" : "var(--warn)",
                    }}
                  >
                    {g.impact} impact
                  </span>
                </summary>
                <div className="px-3 py-2 text-[11px] text-white/65 leading-relaxed">
                  <div className="mb-1"><span className="text-white/45">Now:</span> {g.current}</div>
                  <div><span className="text-white/45">Proposed:</span> {g.proposed}</div>
                </div>
              </details>
            ))}
          </div>
        </div>
      )}
    </motion.section>
  );
};

export default RiskPostureCard;
