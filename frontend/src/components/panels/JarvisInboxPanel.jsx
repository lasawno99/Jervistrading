import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Inbox, Check, Calendar as CalIcon, ListTodo, Bell } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const JarvisInboxPanel = ({ delay = 0, refreshKey = 0 }) => {
  const [tab, setTab] = useState("inbox");
  const [notifications, setNotifications] = useState([]);
  const [todos, setTodos] = useState([]);
  const [schedules, setSchedules] = useState([]);

  const load = useCallback(async () => {
    try {
      const [n, t, s] = await Promise.all([
        axios.get(`${API}/jarvis/notifications?limit=15`),
        axios.get(`${API}/jarvis/todos`),
        axios.get(`${API}/jarvis/schedules`),
      ]);
      setNotifications(n.data.notifications || []);
      setTodos(t.data.todos || []);
      setSchedules(s.data.schedules || []);
    } catch {}
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load, refreshKey]);

  const completeTodo = async (id) => {
    await axios.post(`${API}/jarvis/todos/${id}/complete`);
    load();
  };

  const cancelSchedule = async (id) => {
    await axios.delete(`${API}/jarvis/schedules/${id}`);
    load();
  };

  const tabs = [
    { id: "inbox", label: "inbox", icon: Bell, count: notifications.filter((n) => !n.read).length },
    { id: "todos", label: "todos", icon: ListTodo, count: todos.length },
    { id: "schedules", label: "schedules", icon: CalIcon, count: schedules.length },
  ];

  return (
    <Panel title="JARVIS · INBOX" subtitle="live" icon={Inbox} delay={delay} testId="panel-jarvis-inbox">
      <div className="flex gap-1 mb-2">
        {tabs.map(({ id, label, count, icon: I }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex-1 px-2 py-1 rounded-md text-[10px] tracking-[0.2em] uppercase font-display flex items-center justify-center gap-1.5 transition-all"
            style={{
              color: tab === id ? "#050B14" : "#8BABC6",
              background: tab === id ? "#00F0FF" : "transparent",
              border: "1px solid rgba(0,240,255,0.3)",
            }}
            data-testid={`inbox-tab-${id}`}
          >
            <I size={10} />
            {label}
            {count > 0 && <span className="ml-0.5 text-[9px]">·{count}</span>}
          </button>
        ))}
      </div>

      <div className="jv-scroll overflow-y-auto pr-1" style={{ maxHeight: 280 }}>
        {tab === "inbox" && (
          notifications.length === 0
            ? <div className="text-[11px] italic text-[#8BABC6]">// no notifications yet_</div>
            : notifications.map((n) => (
                <div key={n.id} className="border border-[#00F0FF]/15 rounded p-2 mb-2" data-testid={`notif-${n.id}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-display text-[10px] tracking-[0.2em] uppercase text-[#FFB000]">{n.title}</span>
                    <span className="text-[9px] text-[#8BABC6]">
                      {new Date(n.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <div className="text-[11px] text-white whitespace-pre-wrap leading-snug">{n.content}</div>
                </div>
              ))
        )}

        {tab === "todos" && (
          todos.length === 0
            ? <div className="text-[11px] italic text-[#8BABC6]">// no open todos_</div>
            : todos.map((t) => (
                <div key={t.id} className="flex items-start gap-2 py-1.5 border-b border-[#00F0FF]/10 last:border-0" data-testid={`todo-${t.id}`}>
                  <button
                    onClick={() => completeTodo(t.id)}
                    className="mt-0.5 w-4 h-4 rounded border border-[#00F0FF]/40 flex items-center justify-center hover:bg-[#00F0FF]/10"
                    data-testid={`todo-done-${t.id}`}
                    aria-label="mark done"
                  >
                    <Check size={10} className="opacity-0 hover:opacity-100" style={{ color: "#27C93F" }} />
                  </button>
                  <span className="text-[11px] text-white flex-1 leading-snug">{t.text}</span>
                </div>
              ))
        )}

        {tab === "schedules" && (
          schedules.length === 0
            ? <div className="text-[11px] italic text-[#8BABC6]">// no active schedules_</div>
            : schedules.map((s) => (
                <div key={s.id} className="border border-[#00F0FF]/15 rounded p-2 mb-2" data-testid={`sched-${s.id}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-display text-[10px] tracking-[0.2em] uppercase text-[#00F0FF]">{s.title}</span>
                    <button
                      onClick={() => cancelSchedule(s.id)}
                      className="text-[9px] tracking-wider text-[#FF5F56] hover:text-[#FF007F]"
                      data-testid={`sched-cancel-${s.id}`}
                    >
                      ✕ cancel
                    </button>
                  </div>
                  <div className="text-[10px] text-[#8BABC6] mb-1">
                    {s.cron ? <>cron <code className="text-white">{s.cron}</code></> : <>at <code className="text-white">{s.at}</code></>}
                  </div>
                  <div className="text-[10px] text-white/80 leading-snug italic">↳ {s.prompt}</div>
                  {s.next_run && (
                    <div className="text-[9px] text-[#8BABC6] mt-1">
                      next: {new Date(s.next_run).toLocaleString()}
                    </div>
                  )}
                </div>
              ))
        )}
      </div>
    </Panel>
  );
};

export default JarvisInboxPanel;
