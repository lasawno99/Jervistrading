import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Wallet } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(v) ? v : 0);

const fmtPct = (v) =>
  Number.isFinite(v) ? `${v >= 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(2)}%` : "—";

const Animated = ({ value, formatter = fmtMoney, className = "" }) => {
  const mv = useMotionValue(0);
  const display = useTransform(mv, (v) => formatter(v));
  useEffect(() => {
    const c = animate(mv, Number.isFinite(value) ? value : 0, {
      duration: 0.9,
      ease: [0.22, 1, 0.36, 1],
    });
    return c.stop;
  }, [value, mv]);
  return <motion.span className={`tabular ${className}`}>{display}</motion.span>;
};

const Sparkline = ({ data, up }) => {
  const color = up ? "var(--up)" : "var(--down)";
  return (
    <div className="h-10 w-full -mb-1">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`spark-${up ? "u" : "d"}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.4} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="y"
            stroke={color}
            strokeWidth={1.6}
            fill={`url(#spark-${up ? "u" : "d"})`}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

const Ring = ({ pct, color = "var(--accent-2)" }) => {
  const safe = Math.max(0, Math.min(100, pct ?? 0));
  const circumference = 2 * Math.PI * 18;
  const offset = circumference * (1 - safe / 100);
  return (
    <svg width="48" height="48" className="-mt-1" viewBox="0 0 48 48">
      <circle cx="24" cy="24" r="18" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
      <circle
        cx="24"
        cy="24"
        r="18"
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 24 24)"
        style={{ transition: "stroke-dashoffset 800ms cubic-bezier(0.22, 1, 0.36, 1)" }}
      />
    </svg>
  );
};

const Bar = ({ pct, color = "var(--accent-1)" }) => {
  const safe = Math.max(0, Math.min(100, pct ?? 0));
  return (
    <div className="h-1.5 w-full rounded-full bg-white/8 overflow-hidden">
      <div
        className="h-full rounded-full"
        style={{
          width: `${safe}%`,
          background: `linear-gradient(90deg, ${color}, var(--accent-2))`,
          transition: "width 800ms cubic-bezier(0.22, 1, 0.36, 1)",
        }}
      />
    </div>
  );
};

const Kpi = ({ title, value, sub, accent, children, testId, delay }) => (
  <motion.div
    className="card p-4 flex flex-col gap-2 min-w-0"
    initial={{ opacity: 0, y: 14 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay }}
    data-testid={testId}
  >
    <div className="card-title">{title}</div>
    <div className="text-[22px] md:text-[26px] font-semibold tracking-tight leading-none truncate">
      {value}
    </div>
    {sub && <div className="text-[12px]" style={{ color: accent }}>{sub}</div>}
    {children}
  </motion.div>
);

export const HeroMetricsRow = () => {
  const [hero, setHero] = useState(null);
  const [spark, setSpark] = useState([]);
  const [sparkPL, setSparkPL] = useState([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [h, s, sp] = await Promise.all([
          axios.get(`${API}/dashboard/hero`),
          axios.get(`${API}/dashboard/sparkline?metric=equity`),
          axios.get(`${API}/dashboard/sparkline?metric=pl`),
        ]);
        if (!alive) return;
        setHero(h.data);
        setSpark(s.data.points || []);
        setSparkPL(sp.data.points || []);
      } catch {}
    };
    load();
    const t = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const equity = hero?.total_equity ?? 0;
  const dayPl = hero?.day_pl ?? 0;
  const cash = hero?.total_cash ?? 0;
  const exposure = hero?.exposure_pct ?? 0;
  const winRate = hero?.win_rate;
  const dayUp = dayPl >= 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3" data-testid="hero-metrics">
      <Kpi
        title="Total Equity"
        value={<Animated value={equity} />}
        sub={fmtPct(hero?.total_equity_pct)}
        accent={(hero?.total_equity_pct ?? 0) >= 0 ? "var(--up)" : "var(--down)"}
        testId="kpi-equity"
        delay={0.05}
      >
        <Sparkline data={spark} up={true} />
      </Kpi>

      <Kpi
        title="Day's P/L"
        value={<Animated value={dayPl} formatter={(v) => (v >= 0 ? "+" : "") + fmtMoney(v)} />}
        sub={fmtPct(hero?.day_pl_pct)}
        accent={dayUp ? "var(--up)" : "var(--down)"}
        testId="kpi-day-pl"
        delay={0.1}
      >
        <Sparkline data={sparkPL.length ? sparkPL : spark} up={dayUp} />
      </Kpi>

      <Kpi
        title="Total Cash"
        value={<Animated value={cash} />}
        testId="kpi-cash"
        delay={0.15}
      >
        <div className="flex items-center gap-2 mt-1 text-white/45">
          <Wallet size={14} />
          <span className="text-[11px]">{hero?.open_positions ?? 0} open</span>
        </div>
      </Kpi>

      <Kpi
        title="Exposure"
        value={`${(exposure ?? 0).toFixed(1)}%`}
        testId="kpi-exposure"
        delay={0.2}
      >
        <div className="mt-2"><Bar pct={exposure} /></div>
      </Kpi>

      <Kpi
        title="Win Rate"
        value={winRate == null ? "—" : `${winRate.toFixed(1)}%`}
        sub={winRate == null ? "no closed trades yet" : null}
        accent="var(--text-3)"
        testId="kpi-win-rate"
        delay={0.25}
      >
        {winRate != null && (
          <div className="flex justify-end -mt-2">
            <Ring pct={winRate} color="var(--accent-2)" />
          </div>
        )}
      </Kpi>
    </div>
  );
};

export default HeroMetricsRow;
