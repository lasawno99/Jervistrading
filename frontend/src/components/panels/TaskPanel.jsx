import React from "react";
import { Panel } from "../Panel";
import { Cpu } from "lucide-react";

const STATUS_COLOR = {
  queued: "#8BABC6",
  running: "#00F0FF",
  completed: "#27C93F",
  failed: "#FF5F56",
};

export const TaskPanel = ({ tasks, delay = 0 }) => {
  return (
    <Panel
      title="AGENT · TASKS"
      subtitle={`${tasks.length} active`}
      icon={Cpu}
      delay={delay}
      testId="panel-tasks"
    >
      <div className="space-y-2 jv-scroll overflow-y-auto pr-1" style={{ maxHeight: 320 }}>
        {tasks.length === 0 && (
          <div className="text-[11px] text-[#8BABC6] italic">
            // no spawned tasks. issue a command<span className="caret"> _</span>
          </div>
        )}
        {tasks.map((t) => (
          <div
            key={t.id}
            className="border border-[#00F0FF]/20 rounded-md p-2"
            data-testid={`task-${t.id}`}
          >
            <div className="flex items-center justify-between mb-1">
              <span
                className="font-display text-[10px] tracking-[0.3em] uppercase"
                style={{ color: STATUS_COLOR[t.status] || "#00F0FF" }}
              >
                ● {t.status}
              </span>
              <span className="text-[9px] text-[#8BABC6] uppercase tracking-wider">
                {t.panel}
              </span>
            </div>
            <div className="text-[11px] text-white leading-snug">{t.title}</div>
            {t.detail && (
              <div className="text-[10px] text-[#8BABC6] mt-1 leading-snug italic">
                ↳ {t.detail}
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
};

export default TaskPanel;
