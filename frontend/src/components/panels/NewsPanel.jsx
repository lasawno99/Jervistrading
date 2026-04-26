import React, { useEffect, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Newspaper } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const NewsPanel = ({ delay = 0 }) => {
  const [items, setItems] = useState([]);

  useEffect(() => {
    axios.get(`${API}/feed/news`).then((r) => setItems(r.data)).catch(() => {});
  }, []);

  return (
    <Panel title="NEWS · BRIEF" subtitle="aggregated" icon={Newspaper} delay={delay} testId="panel-news">
      <div className="space-y-3 jv-scroll overflow-y-auto pr-1" style={{ maxHeight: 320 }}>
        {items.map((n) => (
          <div key={n.id} data-testid={`news-${n.id}`}>
            <div className="text-white text-xs leading-snug">{n.headline}</div>
            <div className="text-[10px] tracking-[0.2em] uppercase text-[#FFB000] mt-1">
              {n.source}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
};

export default NewsPanel;
