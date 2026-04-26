import React, { useEffect, useState } from "react";
import axios from "axios";
import { Panel } from "../Panel";
import { Hash } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const TwitterPanel = ({ delay = 0 }) => {
  const [tweets, setTweets] = useState([]);

  useEffect(() => {
    axios.get(`${API}/feed/twitter`).then((r) => setTweets(r.data)).catch(() => {});
  }, []);

  return (
    <Panel title="X · FEED" subtitle="streaming" icon={Hash} delay={delay} testId="panel-twitter">
      <div className="space-y-3 jv-scroll overflow-y-auto pr-1" style={{ maxHeight: 320 }}>
        {tweets.map((t) => (
          <div key={t.id} className="text-xs leading-relaxed" data-testid={`tweet-${t.handle}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-display text-[#00F0FF]">{t.name}</span>
              <span className="text-[10px] text-[#8BABC6]">{t.handle}</span>
            </div>
            <div className="text-white/90 text-[12px]">{t.content}</div>
            <div className="text-[10px] text-[#8BABC6] mt-1">♥ {t.likes.toLocaleString()}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
};

export default TwitterPanel;
