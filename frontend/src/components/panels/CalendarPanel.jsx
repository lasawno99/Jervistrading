import React, { useEffect, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { CalendarDays } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmt = (iso) => {
  const d = new Date(iso);
  return d.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
};

export const CalendarPanel = ({ delay = 0 }) => {
  const [items, setItems] = useState([]);

  useEffect(() => {
    axios.get(`${API}/feed/calendar`).then((r) => setItems(r.data)).catch(() => {});
  }, []);

  return (
    <Panel
      title="SCHEDULE"
      subtitle="upcoming"
      icon={CalendarDays}
      delay={delay}
      testId="panel-calendar"
    >
      <div className="space-y-3 jv-scroll overflow-y-auto pr-1" style={{ maxHeight: 320 }}>
        {items.map((it) => (
          <div
            key={it.id}
            className="border-l-2 pl-3 py-1"
            style={{ borderColor: "#00F0FF" }}
            data-testid={`event-${it.id}`}
          >
            <div className="font-display text-[11px] tracking-wider uppercase text-[#00F0FF]">
              {fmt(it.time)}
            </div>
            <div className="text-white text-xs mt-0.5">{it.title}</div>
            <div className="text-[10px] text-[#8BABC6] mt-1">
              {it.attendees.join(" · ")}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
};

export default CalendarPanel;
