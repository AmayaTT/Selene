const React = window.React;
const { useState, useEffect } = React;
const { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } = window.Recharts;

const C = {
  bg: "#F4F1EE", card: "#EDEAF3", cardAlt: "#EDE8E2",
  purple: "#B8A9C9", purpleDeep: "#9380AD",
  pink: "#D4BDB0", sage: "#B8C4B4", blue: "#A9BDC9",
  text: "#524A5F", textLight: "#9188A0", white: "#FAFAF8",
};

// 相对路径（同源部署：手机/公网访问 8010 都通）
const API = "";
async function apiGet(path) {
  try { const r = await fetch(API + path); return await r.json(); }
  catch (e) { console.warn("apiGet failed", e); return null; }
}
async function apiPost(path, body) {
  try {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.ok ? await r.json() : null;
  } catch (e) { console.warn("apiPost failed", e); return null; }
}

async function postPeriodAction(path, body) {
  try {
    const response = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const result = await response.json();
    return response.ok ? result : { success: false, detail: typeof result.detail === "string" ? result.detail : "日期或操作无效，请检查后重试" };
  } catch (_) {
    return { success: false, detail: "未能确认保存结果，输入已保留，请重试" };
  }
}

function localDateStr(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function cycleDayFromStart(periodStart, cycleLength = 28) {
  if (!periodStart) return 0;
  const start = new Date(`${periodStart}T00:00:00`);
  if (Number.isNaN(start.getTime())) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.floor((today - start) / 86400000);
  if (diff < 0) return 0;
  return diff + 1;
}

const PHASES = [
  { name: "月经期", days: [1, 5],   color: C.pink,   emoji: "🌑" },
  { name: "卵泡期", days: [6, 13],  color: C.sage,   emoji: "🌒" },
  { name: "排卵期", days: [14, 16], color: C.blue,   emoji: "🌕" },
  { name: "黄体期", days: [17, 28], color: C.purple, emoji: "🌖" },
];

function getPhase(day) {
  return PHASES.find((p) => day >= p.days[0] && day <= p.days[1]) || PHASES[3];
}

const UNKNOWN_PHASE = { name: "未知", color: C.purple, emoji: "🌙" };
const PHASE_KEYS = ["menstrual", "follicular", "ovulation", "luteal"];
function phaseFromTable(day, table) {
  return PHASES[PHASE_KEYS.indexOf(table[String(day)])] || UNKNOWN_PHASE;
}
const PhaseContext = React.createContext(() => UNKNOWN_PHASE);
const SourceContext = React.createContext({});

function moodEntries(moodLog) {
  return Object.entries(moodLog).filter(([, score]) => score > 0)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, mood]) => ({ date, mood }));
}

function phaseAverages(moodLog, dateInfo) {
  return PHASES.map((phase, index) => {
    const values = moodEntries(moodLog).filter(row => dateInfo[row.date]?.phase === PHASE_KEYS[index]);
    return { name: phase.name, color: phase.color,
      avg: values.length ? +(values.reduce((sum, row) => sum + row.mood, 0) / values.length).toFixed(1) : null };
  });
}

const SYMPTOMS_LIST = ["头疼", "偏头痛", "头晕", "腰酸", "腿酸", "水肿", "乳房胀痛", "小腹坠痛", "痛经", "腹痛", "腹胀", "恶心", "腹泻", "便秘", "食欲旺盛", "食欲不振", "疲惫", "乏力", "失眠", "嗜睡", "长痘", "畏寒", "情绪波动", "易怒", "焦虑", "心情低落", "状态良好"];

const MOOD_EMOJIS = [
  { score: 2, emoji: "😞", label: "很差" },
  { score: 4, emoji: "😕", label: "不好" },
  { score: 6, emoji: "😐", label: "还行" },
  { score: 8, emoji: "🙂", label: "不错" },
  { score: 10, emoji: "😊", label: "很好" },
];


function moodColor(score) {
  if (!score || score < 0) return "#E2DDE8";
  if (score <= 3) return "#D4BDB0";
  if (score <= 5) return "#C9BFD4";
  if (score <= 7) return "#B8C4B4";
  return "#A9BDC9";
}

// ═══════════════════════════════════════════
// 共用组件
// ═══════════════════════════════════════════

function SectionLabel({ children }) {
  return (
    <div style={{ fontSize: 11, color: C.textLight, marginBottom: 12, letterSpacing: "0.06em", textTransform: "uppercase" }}>
      {children}
    </div>
  );
}

function Card({ children, style }) {
  return (
    <div style={{ background: C.card, borderRadius: 20, padding: "16px 18px", ...style }}>
      {children}
    </div>
  );
}

// ═══════════════════════════════════════════
// 主页组件
// ═══════════════════════════════════════════

function PeriodStatus({ status }) {
  const current = status || { title: "待记录", detail: "记录经期开始日期后，可查看周期预测。", phase_label: "待记录" };
  return <Card>
    <SectionLabel>当前记录与预测</SectionLabel>
    <div style={{ color: C.text, fontSize: 17, fontWeight: 600 }}>{current.title}</div>
    <div style={{ color: C.textLight, fontSize: 13, lineHeight: 1.6, marginTop: 8 }}>{current.detail}</div>
    <div style={{ color: C.purpleDeep, fontSize: 13, marginTop: 8 }}>{current.phase_label}</div>
  </Card>;
}

function PeriodActions({ config, onChange }) {
  const [startDate, setStartDate] = useState(localDateStr());
  const [endDate, setEndDate] = useState(localDateStr());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const inFlight = React.useRef(false);
  const pending = React.useRef(null);
  async function submit(action) {
    if (inFlight.current) return;
    const value = action === "start" ? startDate : endDate;
    if (!value || value > localDateStr()) { setMessage("请选择今天或过去的实际日期"); return; }
    if (action === "end" && (!config.periodId || value < config.periodStart)) { setMessage("请先记录开始日期；结束日期不能早于开始日期"); return; }
    const payload = { action, date: value, period_id: action === "end" ? config.periodId : null };
    const signature = JSON.stringify(payload);
    if (pending.current?.signature !== signature) {
      pending.current = { signature, id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}` };
    }
    inFlight.current = true; setBusy(true); setMessage("正在保存…");
    try {
      const result = await postPeriodAction("/period/action", { ...payload, request_id: pending.current.id });
      if (!result.success) { setMessage(result.detail); return; }
      pending.current = null;
      await onChange(result);
      setMessage(result.undone ? "这次操作已撤销" : result.changed ? "已保存，可撤销上次记录" : "该日期已记录，无需重复保存");
    } finally { inFlight.current = false; setBusy(false); }
  }
  async function undo() {
    if (inFlight.current || !config.undoAction) return;
    inFlight.current = true; setBusy(true); setMessage("正在撤销…");
    try {
      const result = await postPeriodAction("/period/undo", { request_id: config.undoAction.request_id });
      if (!result.success) { setMessage(result.detail); return; }
      await onChange(result);
      setMessage("已撤销，恢复到操作前的记录");
    } finally { inFlight.current = false; setBusy(false); }
  }
  const inputStyle = { minWidth: 0, width: "100%", boxSizing: "border-box", padding: "9px", borderRadius: 10, border: "1px solid #D8D4E0", background: C.bg, color: C.text };
  const buttonStyle = { padding: "10px 12px", borderRadius: 10, border: "none", background: C.purpleDeep, color: C.white, cursor: "pointer" };
  return <Card>
    <SectionLabel>经期记录</SectionLabel>
    <div style={{ fontSize: 12, color: C.textLight, marginBottom: 12 }}>默认今天，也可以选择过去的日期补记。</div>
    <div style={{ display: "grid", gap: 12 }}>
      <label style={{ display: "grid", gap: 6, fontSize: 13, color: C.text }}>实际开始日期
        <input aria-label="实际开始日期" type="date" value={startDate} max={localDateStr()} disabled={busy} onChange={event => setStartDate(event.target.value)} style={inputStyle} />
      </label>
      <button disabled={busy} onClick={() => submit("start")} style={buttonStyle}>记录开始</button>
      <label style={{ display: "grid", gap: 6, fontSize: 13, color: C.text }}>实际结束日期
        <input aria-label="实际结束日期" type="date" value={endDate} min={config.periodStart || undefined} max={localDateStr()} disabled={busy || !config.periodId} onChange={event => setEndDate(event.target.value)} style={inputStyle} />
      </label>
      <button disabled={busy || !config.periodId} onClick={() => submit("end")} style={{ ...buttonStyle, background: config.periodId ? C.purpleDeep : C.textLight }}>记录结束</button>
      {config.periodStart && <div style={{ fontSize: 12, color: C.textLight }}>结束日期记在 {config.periodStart} 开始的这一轮。</div>}
      {config.undoAction && <button disabled={busy} onClick={undo} style={{ ...buttonStyle, background: C.cardAlt, color: C.text }}>撤销上次记录</button>}
      {message && <div role="status" aria-live="polite" style={{ fontSize: 13, color: C.text, lineHeight: 1.6 }}>{message}</div>}
    </div>
  </Card>;
}

function MoonRing({ day, total = 28, phaseLabel }) {
  const getPhase = React.useContext(PhaseContext);
  const r = 90, cx = 120, cy = 120;
  const circumference = 2 * Math.PI * r;
  const dash = circumference * Math.min(1, Math.max(0, day / total));
  const phase = getPhase(day);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, width: "100%" }}>
      <svg width="100%" viewBox="0 0 240 240" style={{ maxWidth: 260 }}>
        {Array.from({ length: total }, (_, i) => {
          const angle = ((i / total) * 360 - 90) * (Math.PI / 180);
          const inner = 105, outer = i % 7 === 0 ? 112 : 108;
          return (
            <line key={i}
              x1={cx + inner * Math.cos(angle)} y1={cy + inner * Math.sin(angle)}
              x2={cx + outer * Math.cos(angle)} y2={cy + outer * Math.sin(angle)}
              stroke={i + 1 <= day ? phase.color : "#D8D4E0"}
              strokeWidth={i % 7 === 0 ? 2 : 1} opacity={0.7} />
          );
        })}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#E2DDE8" strokeWidth={10} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={phase.color} strokeWidth={10}
          strokeLinecap="round" strokeDasharray={`${dash} ${circumference}`}
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: "stroke-dasharray 0.6s ease" }} />
        <circle cx={cx} cy={cy} r={52} fill={C.white} />
        <circle cx={cx} cy={cy} r={48} fill="#F0EBF5" />
        <text x={cx} y={cy - 8} textAnchor="middle" fontSize={28} dominantBaseline="middle">{phase.emoji}</text>
        <text x={cx} y={cy + 20} textAnchor="middle" fontSize={22} fontWeight="600" fill={C.text} style={{ fontFamily: "Georgia, serif" }}>{day > 0 ? `Day ${day}` : "待记录"}</text>
        <text x={cx} y={cy + 38} textAnchor="middle" fontSize={11} fill={C.textLight}>/ {total}</text>
      </svg>
      <div style={{ background: phase.color + "33", border: `1px solid ${phase.color}`, borderRadius: 20, padding: "5px 18px", color: C.text, fontSize: 13 }}>
        {phaseLabel || (day > 0 ? `预计${phase.name}` : "待记录")}
      </div>
    </div>
  );
}

function MoodLogger({ day, moodLog, onLog, logDate = localDateStr() }) {
  const getPhase = React.useContext(PhaseContext);
  const phase = getPhase(day);
  const logged = moodLog[logDate];
  const origin = React.useContext(SourceContext)[logDate]?.mood;
  const [editing, setEditing] = useState(false);
  useEffect(() => setEditing(false), [logDate, logged]);
  return (
    <Card>
      <SectionLabel>{logDate === localDateStr() ? "今天心情" : `${logDate} 心情`}</SectionLabel>
      {origin?.source === "memora" && <div style={{ fontSize: 11, color: C.textLight, marginBottom: 8 }}>来自 Memora · 自动估算，可手动修改</div>}
      {logged != null && !editing ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: C.text }}>
          <span style={{ fontSize: 24 }}>{logged === -1 ? "🌫️" : MOOD_EMOJIS.find(e => e.score === logged)?.emoji}</span>
          <span style={{ flex: 1 }}>{logged === -1 ? "今天没啥感觉" : <>记录了 <b style={{ color: phase.color }}>{logged}/10</b>，{MOOD_EMOJIS.find(e => e.score === logged)?.label}</>}</span>
          <button onClick={() => setEditing(true)} style={{ fontSize: 11, color: C.textLight, background: "none", border: "none", cursor: "pointer" }}>重选</button>
        </div>
      ) : (
        <div>
          <div style={{ display: "flex", justifyContent: "space-around", marginBottom: 12 }}>
            {MOOD_EMOJIS.map(({ score, emoji, label }) => (
              <button key={score} onClick={async () => { if (await onLog(logDate, score)) setEditing(false); }} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, background: "none", border: "none", cursor: "pointer", padding: "8px 4px", borderRadius: 12, flex: 1 }}>
                <span style={{ fontSize: 28 }}>{emoji}</span>
                <span style={{ fontSize: 10, color: C.textLight }}>{label}</span>
              </button>
            ))}
          </div>
          <button onClick={async () => { if (await onLog(logDate, -1)) setEditing(false); }} style={{ width: "100%", padding: "9px", borderRadius: 12, fontSize: 12, color: C.textLight, background: "transparent", border: `1px dashed #D8D4E0`, cursor: "pointer" }}>
            没啥感觉，跳过
          </button>
        </div>
      )}
    </Card>
  );
}

function SymptomLogger({ day, symptomLog, onToggle, logDate = localDateStr() }) {
  const getPhase = React.useContext(PhaseContext);
  const phase = getPhase(day);
  const selected = symptomLog[logDate] || [];
  const origin = React.useContext(SourceContext)[logDate]?.symptoms;
  const isGood = selected.includes("状态良好");
  const [customOpen, setCustomOpen] = useState(false);
  const [customText, setCustomText] = useState("");
  function handleToggle(s) {
    if (s === "状态良好") { onToggle(logDate, "__good__"); }
    else { if (!isGood) onToggle(logDate, s); }
  }
  function openCustom() {
    setCustomText("");
    setCustomOpen(true);
  }
  function submitCustom() {
    const text = customText.trim();
    setCustomOpen(false);
    if (!text || selected.includes(text)) return;
    onToggle(logDate, text);
  }
  return (
    <Card>
      <SectionLabel>{logDate === localDateStr() ? "今日症状" : `${logDate} 症状`}</SectionLabel>
      {["memora", "mixed"].includes(origin?.source) && <div style={{ fontSize: 11, color: C.textLight, marginBottom: 8 }}>包含从 Memora 同步的症状</div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {SYMPTOMS_LIST.map((s) => {
          const active = selected.includes(s);
          const isGoodTag = s === "状态良好";
          const disabled = isGood && !isGoodTag;
          return (
            <button key={s} onClick={() => handleToggle(s)} style={{ padding: "6px 14px", borderRadius: 20, fontSize: 13, border: `1px solid ${active ? (isGoodTag ? C.sage : phase.color) : "#D8D4E0"}`, background: active ? (isGoodTag ? C.sage + "33" : phase.color + "33") : "transparent", color: disabled ? "#C8C4D0" : active ? C.text : C.textLight, cursor: disabled ? "not-allowed" : "pointer" }}>
              {isGoodTag ? "✨ " + s : s}
            </button>
          );
        })}
        {customOpen ? (
          <div style={{ display: "flex", gap: 8, alignItems: "center", width: "100%" }}>
            <input autoFocus value={customText} onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitCustom(); }} placeholder="输入自定义症状"
              style={{ flex: 1, padding: "6px 12px", borderRadius: 20, fontSize: 13, border: "1px dashed #D8D4E0", background: C.bg, color: C.text, outline: "none" }} />
            <button onClick={submitCustom} style={{ padding: "6px 12px", borderRadius: 20, fontSize: 13, border: "1px solid #D8D4E0", background: C.sage + "33", color: C.text, cursor: "pointer" }}>✓</button>
            <button onClick={() => { setCustomOpen(false); setCustomText(""); }} style={{ padding: "6px 12px", borderRadius: 20, fontSize: 13, border: "1px solid #D8D4E0", background: "transparent", color: C.textLight, cursor: "pointer" }}>✕</button>
          </div>
        ) : (
          <button onClick={openCustom} disabled={isGood} style={{ padding: "6px 14px", borderRadius: 20, fontSize: 13, border: "1px dashed #D8D4E0", background: "transparent", color: isGood ? "#C8C4D0" : C.textLight, cursor: isGood ? "not-allowed" : "pointer" }}>
            + 自定义
          </button>
        )}
      </div>
      {selected.length > 0 && !isGood && <div style={{ marginTop: 12, fontSize: 12, color: C.textLight }}>已记录 {selected.length} 项</div>}
    </Card>
  );
}

function MoodChartSmall({ currentDay, moodLog, periodStart }) {
  const getPhase = React.useContext(PhaseContext);
  const phase = getPhase(currentDay);
  const data = moodEntries(moodLog).filter(row => (!periodStart || row.date >= periodStart) && row.date <= localDateStr());
  return (
    <Card>
      <SectionLabel>本周期情绪走向</SectionLabel>
      <ResponsiveContainer width="100%" height={120}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
          <defs>
            <linearGradient id="moodGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={phase.color} stopOpacity={0.4} />
              <stop offset="95%" stopColor={phase.color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: C.textLight }} tickLine={false} axisLine={false} tickFormatter={v => v.slice(5)} />
          <YAxis domain={[1, 10]} tick={{ fontSize: 10, fill: C.textLight }} tickLine={false} axisLine={false} tickCount={3} />
          <Tooltip formatter={(v) => [v, "情绪"]} />
          <Area type="monotone" dataKey="mood" stroke={phase.color} strokeWidth={2} fill="url(#moodGrad)" dot={false} activeDot={{ r: 4, fill: phase.color, strokeWidth: 0 }} />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}

function NextPrediction({ cycleStart, cycleLength }) {
  const next = new Date(cycleStart); next.setDate(next.getDate() + cycleLength);
  const today = new Date();
  const diff = Math.round((next - today) / (1000 * 60 * 60 * 24));
  const ovulation = new Date(cycleStart); ovulation.setDate(ovulation.getDate() + cycleLength - 14);
  const fmt = (d) => `${d.getMonth() + 1}月${d.getDate()}日`;
  return (
    <div style={{ background: C.cardAlt, borderRadius: 20, padding: "16px 18px" }}>
      <SectionLabel>周期预测</SectionLabel>
      <div style={{ display: "flex", gap: 10 }}>
        <div style={{ flex: 1, background: C.pink + "33", borderRadius: 14, padding: "12px 14px" }}>
          <div style={{ fontSize: 10, color: C.textLight, marginBottom: 4 }}>预计下次经期</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>{fmt(next)}</div>
          <div style={{ fontSize: 11, color: C.pink, marginTop: 2 }}>{diff > 0 ? `还有 ${diff} 天` : diff === 0 ? "就是今天" : `已过 ${Math.abs(diff)} 天`}</div>
        </div>
        <div style={{ flex: 1, background: C.blue + "33", borderRadius: 14, padding: "12px 14px" }}>
          <div style={{ fontSize: 10, color: C.textLight, marginBottom: 4 }}>预计排卵</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>{fmt(ovulation)}</div>
          <div style={{ fontSize: 11, color: C.blue, marginTop: 2 }}>预计下次经期前 14 天</div>
        </div>
      </div>
    </div>
  );
}

const SUGGESTIONS = {
  月经期: ["多喝红糖姜茶，暖一暖", "减少剧烈运动，散步就好", "身体在更新，允许自己慢下来"],
  卵泡期: ["能量慢慢回升，适合开始新计划", "多补充蛋白质和铁", "心情会越来越好的"],
  排卵期: ["今天状态最好，做重要的事", "适合社交和表达", "身体在发光，好好感受"],
  黄体期: ["情绪波动正常，不要责怪自己", "多吃镁和B6（香蕉、坚果）", "需要更多安静和陪伴"],
};

function TodayCard({ day }) {
  const getPhase = React.useContext(PhaseContext);
  const phase = getPhase(day);
  const tips = SUGGESTIONS[phase.name] || ["请先记录经期日期。"];
  return (
    <div style={{ background: phase.color + "22", border: `1px solid ${phase.color}55`, borderRadius: 20, padding: "16px 18px" }}>
      <SectionLabel>今日</SectionLabel>
      {tips.map((tip, i) => (
        <div key={i} style={{ display: "flex", gap: 8, marginBottom: i < tips.length - 1 ? 10 : 0, fontSize: 14, color: C.text, lineHeight: 1.5 }}>
          <span style={{ color: phase.color, flexShrink: 0 }}>·</span>{tip}
        </div>
      ))}
    </div>
  );
}

function PhaseBar({ currentDay }) {
  const getPhase = React.useContext(PhaseContext);
  return (
    <div>
      <div style={{ display: "flex", gap: 4 }}>
        {PHASES.map((p) => {
          const len = p.days[1] - p.days[0] + 1;
          const active = getPhase(currentDay).name === p.name;
          return <div key={p.name} style={{ flex: len, height: 4, borderRadius: 2, background: active ? p.color : p.color + "44", transition: "background 0.3s" }} />;
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5 }}>
        {PHASES.map((p) => <div key={p.name} style={{ fontSize: 10, color: C.textLight }}>{p.name}</div>)}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════
// 记录页 — 月历
// ═══════════════════════════════════════════

function LogPage({ currentDay, moodLog, symptomLog, periodStart, dateInfo, onLog, onToggle }) {
  const getPhase = React.useContext(PhaseContext);
  const [selected, setSelected] = useState(null);
  const today = new Date();
  const [viewMonth, setViewMonth] = useState(localDateStr().slice(0, 7));
  const [year, monthNumber] = viewMonth.split("-").map(Number);
  const month = monthNumber - 1;
  const dateKey = d => `${viewMonth}-${String(d).padStart(2, "0")}`;
  function changeMonth(offset) {
    setViewMonth(localDateStr(new Date(year, month + offset, 1)).slice(0, 7));
    setSelected(null);
  }
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const WEEKS = ["日", "一", "二", "三", "四", "五", "六"];

  // 从已保存的经期开始日期计算，不自动进入下一轮。
  const cycleDay = (d) => dateInfo[dateKey(d)]?.day ?? (periodStart && dateKey(d) >= periodStart ? Math.round((new Date(year, month, d) - new Date(`${periodStart}T00:00:00`)) / 86400000) + 1 : 0);
  const calendarPhase = d => dateInfo[dateKey(d)]
    ? phaseFromTable(1, { 1: dateInfo[dateKey(d)].phase }) : getPhase(cycleDay(d));

  const detail = selected ? {
    mood: moodLog[dateKey(selected)],
    symptoms: symptomLog[dateKey(selected)] || [],
    phase: calendarPhase(selected),
  } : null;

  return (
    <div style={{ padding: "44px 16px 0" }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: C.text, fontFamily: "Georgia, serif", marginBottom: 4 }}>
        <button aria-label="上个月" onClick={() => changeMonth(-1)}>‹</button>{" "}
        {year}年{month + 1}月
        {" "}<button aria-label="下个月" onClick={() => changeMonth(1)} disabled={viewMonth >= localDateStr().slice(0, 7)}>›</button>
      </div>
      <div style={{ fontSize: 12, color: C.textLight, marginBottom: 20 }}>点击日期查看当天记录</div>

      {/* 星期头 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", marginBottom: 8 }}>
        {WEEKS.map(w => <div key={w} style={{ textAlign: "center", fontSize: 11, color: C.textLight, padding: "4px 0" }}>{w}</div>)}
      </div>

      {/* 日历格子 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
        {Array.from({ length: firstDay }).map((_, i) => <div key={`e${i}`} />)}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const d = i + 1;
          const cd = cycleDay(d);
          const mood = moodLog[dateKey(d)];
          const phase = calendarPhase(d);
          const isToday = dateKey(d) === localDateStr();
          const isSel = selected === d;
          const bg = mood && mood > 0 ? moodColor(mood) : phase.color + "22";
          return (
            <button key={d} onClick={() => setSelected(isSel ? null : d)} style={{
              aspectRatio: "1", borderRadius: 10, border: isSel ? `2px solid ${phase.color}` : isToday ? `2px solid ${C.purpleDeep}` : "2px solid transparent",
              background: bg, cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 1,
            }}>
              <span style={{ fontSize: 13, color: C.text, fontWeight: isToday ? 700 : 400 }}>{d}</span>
              {(symptomLog[dateKey(d)] || []).length > 0 && <span style={{ width: 4, height: 4, borderRadius: "50%", background: phase.color, display: "block" }} />}
            </button>
          );
        })}
      </div>

      {/* 图例 */}
      <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
        {[["😞", "很差"], ["😐", "还行"], ["😊", "很好"]].map(([e, l]) => (
          <div key={l} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: C.textLight }}>
            <span>{e}</span><span>{l}</span>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: C.textLight }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: C.purple, display: "inline-block" }} />有症状记录
        </div>
      </div>

      {/* 当天详情 */}
      {selected && detail && (
        <div style={{ marginTop: 20, background: detail.phase.color + "22", border: `1px solid ${detail.phase.color}55`, borderRadius: 20, padding: "16px 18px" }}>
          <div style={{ fontWeight: 600, color: C.text, marginBottom: 10 }}>{month + 1}月{selected}日 · {detail.phase.name} Day {cycleDay(selected)}</div>
          <div style={{ fontSize: 13, color: C.textLight, marginBottom: 6 }}>
            心情：{detail.mood == null ? "未记录" : detail.mood === -1 ? "无感觉" : `${MOOD_EMOJIS.find(e => e.score === detail.mood)?.emoji} ${MOOD_EMOJIS.find(e => e.score === detail.mood)?.label}`}
          </div>
          <div style={{ fontSize: 13, color: C.textLight }}>
            症状：{detail.symptoms.length === 0 ? "未记录" : detail.symptoms.join("、")}
          </div>
          {dateKey(selected) <= localDateStr() && (
            <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
              <MoodLogger key={`mood-${dateKey(selected)}`} day={cycleDay(selected)} logDate={dateKey(selected)} moodLog={moodLog} onLog={onLog} />
              <SymptomLogger key={`symptom-${dateKey(selected)}`} day={cycleDay(selected)} logDate={dateKey(selected)} symptomLog={symptomLog} onToggle={onToggle} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// 统计页
// ═══════════════════════════════════════════

function StatsPage({ moodLog, symptomLog, currentDay, dateInfo }) {
  const getPhase = React.useContext(PhaseContext);
  const phase = getPhase(currentDay);

  // 情绪均值
  const moodValues = Object.values(moodLog).filter(v => v > 0);
  const avgMood = moodValues.length ? (moodValues.reduce((a, b) => a + b, 0) / moodValues.length).toFixed(1) : "—";

  // 各阶段情绪均值
  const phaseAvg = phaseAverages(moodLog, dateInfo);

  // 症状频率
  const symptomCount = {};
  Object.values(symptomLog).forEach(arr => {
    (arr || []).forEach(s => { if (s !== "状态良好") symptomCount[s] = (symptomCount[s] || 0) + 1; });
  });
  const symptomData = Object.entries(symptomCount).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([name, count]) => ({ name, count }));

  return (
    <div style={{ padding: "44px 16px 0" }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: C.text, fontFamily: "Georgia, serif", marginBottom: 20 }}>数据统计</div>

      {/* 概览卡 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
        <div style={{ background: C.card, borderRadius: 18, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, color: C.textLight, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>平均情绪</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: C.purpleDeep, fontFamily: "Georgia, serif" }}>{avgMood}</div>
          <div style={{ fontSize: 11, color: C.textLight }}>/ 10 分</div>
        </div>
        <div style={{ background: C.card, borderRadius: 18, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, color: C.textLight, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>记录天数</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: C.purpleDeep, fontFamily: "Georgia, serif" }}>{new Set([...Object.keys(moodLog), ...Object.keys(symptomLog)]).size}</div>
          <div style={{ fontSize: 11, color: C.textLight }}>累计记录日期</div>
        </div>
      </div>

      {/* 各阶段情绪 */}
      <Card style={{ marginBottom: 14 }}>
        <SectionLabel>各阶段情绪均值</SectionLabel>
        <div style={{ display: "flex", gap: 8 }}>
          {phaseAvg.map(p => (
            <div key={p.name} style={{ flex: 1, textAlign: "center" }}>
              <div style={{ height: 60, display: "flex", alignItems: "flex-end", justifyContent: "center", marginBottom: 6 }}>
                <div style={{ width: "60%", background: PHASES.find(ph => ph.name.startsWith(p.name))?.color, borderRadius: 6, height: `${(p.avg / 10) * 60}px`, transition: "height 0.4s ease" }} />
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{p.avg ?? "—"}</div>
              <div style={{ fontSize: 10, color: C.textLight, marginTop: 2 }}>{p.name}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 症状频率 */}
      <Card>
        <SectionLabel>症状频率</SectionLabel>
        {symptomData.length === 0 ? (
          <div style={{ fontSize: 13, color: C.textLight, textAlign: "center", padding: "20px 0" }}>还没有症状记录</div>
        ) : (
          symptomData.map(({ name, count }) => (
            <div key={name} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.text, marginBottom: 4 }}>
                <span>{name}</span><span style={{ color: C.textLight }}>{count}次</span>
              </div>
              <div style={{ height: 6, background: "#E2DDE8", borderRadius: 3, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${Math.min(100, count * 20)}%`, background: phase.color, borderRadius: 3, transition: "width 0.4s ease" }} />
              </div>
            </div>
          ))
        )}
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════
// 我的页
// ═══════════════════════════════════════════

function MePage({ cycleLength, setCycleLength, periodStart, setPeriodStart, periodEnd, setPeriodEnd, onSaveConfig,
  remindEnabled, setRemindEnabled, serverchanKey, setServerchanKey, remindTimes, setRemindTimes, coupleMode, setCoupleMode, onSaveReminder, onTestReminder, reminderMsg }) {
  // 计算经期天数
  const periodDays = periodStart && periodEnd
    ? Math.max(1, Math.round((new Date(periodEnd) - new Date(periodStart)) / (1000 * 60 * 60 * 24)) + 1)
    : null;

  return (
    <div style={{ padding: "44px 16px 0" }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: C.text, fontFamily: "Georgia, serif", marginBottom: 20 }}>我的</div>

      {/* 周期设置 */}
      <Card style={{ marginBottom: 14 }}>
        <SectionLabel>周期设置</SectionLabel>
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: C.text, marginBottom: 8 }}>
            <span>周期长度</span>
            <b style={{ color: C.purpleDeep }}>{cycleLength} 天</b>
          </div>
          <input type="range" min={21} max={35} value={cycleLength}
            onChange={e => setCycleLength(Number(e.target.value))}
            style={{ width: "100%", accentColor: C.purpleDeep }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textLight, marginTop: 4 }}>
            <span>21天</span><span>35天</span>
          </div>
        </div>

        <div style={{ borderTop: "1px solid #E2DDE8", paddingTop: 14, display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, color: C.text, marginBottom: 8 }}>上次月经开始</div>
            <input type="date" value={periodStart} max={localDateStr()} onChange={e => setPeriodStart(e.target.value)}
              style={{ width: "100%", padding: "8px 12px", borderRadius: 12, border: "1px solid #D8D4E0", background: C.bg, color: C.text, fontSize: 13, boxSizing: "border-box" }} />
          </div>
          <div>
            <div style={{ fontSize: 13, color: C.text, marginBottom: 8 }}>上次月经结束</div>
            <input type="date" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)}
              min={periodStart || undefined} max={localDateStr()}
              style={{ width: "100%", padding: "8px 12px", borderRadius: 12, border: "1px solid #D8D4E0", background: C.bg, color: C.text, fontSize: 13, boxSizing: "border-box" }} />
          </div>
          {periodDays && (
            <div style={{ background: C.pink + "33", borderRadius: 12, padding: "8px 14px", fontSize: 12, color: C.text }}>
              本次填写经期 <b style={{ color: C.pink }}>{periodDays} 天</b>，保存后生效
            </div>
          )}
          <button onClick={onSaveConfig}
            style={{ width: "100%", padding: "11px", borderRadius: 12, fontSize: 13, fontWeight: 600, color: C.white, background: C.purpleDeep, border: "none", cursor: "pointer", marginTop: 6 }}>
            保存周期设置
          </button>
        </div>
      </Card>

      {/* 主动提醒配置（对接 /reminder_config） */}
      <Card style={{ marginBottom: 14 }}>
        <SectionLabel>主动提醒</SectionLabel>

        {/* 总开关 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div>
            <div style={{ fontSize: 13, color: C.text }}>开启微信提醒</div>
            <div style={{ fontSize: 11, color: C.textLight, marginTop: 2 }}>经期关怀推送到微信</div>
          </div>
          <div onClick={() => setRemindEnabled(!remindEnabled)}
            style={{ width: 44, height: 24, borderRadius: 12, background: remindEnabled ? C.purpleDeep : "#D8D4E0", position: "relative", cursor: "pointer", transition: "background 0.3s", flexShrink: 0 }}>
            <div style={{ position: "absolute", top: 3, left: remindEnabled ? 24 : 3, width: 18, height: 18, borderRadius: "50%", background: C.white, transition: "left 0.3s", boxShadow: "0 1px 3px rgba(0,0,0,0.2)" }} />
          </div>
        </div>

        <div style={{ borderTop: "1px solid #E2DDE8", paddingTop: 14, display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, color: C.text, marginBottom: 8 }}>提醒时间（逗号分隔，24小时制）</div>
            <input type="text" value={remindTimes} onChange={e => setRemindTimes(e.target.value)} placeholder="08:30,21:00"
              style={{ width: "100%", padding: "8px 12px", borderRadius: 12, border: "1px solid #D8D4E0", background: C.bg, color: C.text, fontSize: 13, boxSizing: "border-box" }} />
          </div>
          <div>
            <div style={{ fontSize: 13, color: C.text, marginBottom: 8 }}>Server酱 SendKey</div>
            <input type="text" value={serverchanKey} onChange={e => setServerchanKey(e.target.value)} placeholder="从 sct.ftqq.com 获取"
              style={{ width: "100%", padding: "8px 12px", borderRadius: 12, border: "1px solid #D8D4E0", background: C.bg, color: C.text, fontSize: 13, boxSizing: "border-box" }} />
          </div>
          <div>
            <div style={{ fontSize: 13, color: C.text, marginBottom: 8 }}>提醒语气</div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => setCoupleMode(true)}
                style={{ flex: 1, padding: "9px", borderRadius: 12, fontSize: 13, border: `1px solid ${coupleMode ? C.purpleDeep : "#D8D4E0"}`, background: coupleMode ? C.purpleDeep + "22" : "transparent", color: C.text, cursor: "pointer", fontWeight: coupleMode ? 600 : 400 }}>
                伴侣版 💕
              </button>
              <button onClick={() => setCoupleMode(false)}
                style={{ flex: 1, padding: "9px", borderRadius: 12, fontSize: 13, border: `1px solid ${!coupleMode ? C.sage : "#D8D4E0"}`, background: !coupleMode ? C.sage + "22" : "transparent", color: C.text, cursor: "pointer", fontWeight: !coupleMode ? 600 : 400 }}>
                中性版 🌙
              </button>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onTestReminder}
              style={{ flex: 1, padding: "11px", borderRadius: 12, fontSize: 13, fontWeight: 600, color: C.purpleDeep, background: "transparent", border: `1px solid ${C.purpleDeep}`, cursor: "pointer" }}>
              测试推送
            </button>
            <button onClick={onSaveReminder}
              style={{ flex: 1, padding: "11px", borderRadius: 12, fontSize: 13, fontWeight: 600, color: C.white, background: C.purpleDeep, border: "none", cursor: "pointer" }}>
              保存提醒设置
            </button>
          </div>
          {reminderMsg && <div style={{ fontSize: 12, color: C.textLight, textAlign: "center" }}>{reminderMsg}</div>}
        </div>
      </Card>

      {/* 关于 */}
      <Card>
        <SectionLabel>关于 Selene</SectionLabel>
        <div style={{ fontSize: 13, color: C.textLight, lineHeight: 1.7 }}>
          Selene 是一款温柔的女性健康伙伴，与你的经期同步，记录情绪、理解身体。<br /><br />
          名字来自希腊月亮女神 Σελήνη。
        </div>
        <div style={{ marginTop: 14, fontSize: 12, color: C.textLight + "88", textAlign: "center" }}>
          v0.1 · 与你同步的月亮 🌙
        </div>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════
// 底部导航
// ═══════════════════════════════════════════

const NAV = [
  { key: "home",  label: "主页",  icon: "🌙" },
  { key: "log",   label: "记录",  icon: "📅" },
  { key: "stats", label: "统计",  icon: "📊" },
  { key: "me",    label: "我的",  icon: "👤" },
];

function BottomNav({ active, onChange }) {
  return (
    <div style={{
      position: "fixed", bottom: 0, left: 0, right: 0,
      background: C.white, borderTop: "1px solid #E8E4EE",
      display: "flex", justifyContent: "space-around",
      padding: "10px 0 12px", zIndex: 100,
    }}>
      {NAV.map(({ key, label, icon }) => {
        const isActive = active === key;
        return (
          <button key={key} onClick={() => onChange(key)} style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
            background: "none", border: "none", cursor: "pointer", padding: "4px 16px", borderRadius: 12,
            opacity: isActive ? 1 : 0.4,
          }}>
            <span style={{ fontSize: 20 }}>{icon}</span>
            <span style={{ fontSize: 10, color: isActive ? C.purpleDeep : C.textLight, fontWeight: isActive ? 600 : 400 }}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════
// 主入口
// ═══════════════════════════════════════════

function Selene() {
  const [day, setDay] = useState(0);
  const [savedCycle, setSavedCycle] = useState({ phaseByDay: {}, periodStart: "", cycleLength: 28 });
  const getPhase = d => phaseFromTable(d, savedCycle.phaseByDay || {});
  const [moodLog, setMoodLog] = useState({});
  const [symptomLog, setSymptomLog] = useState({});
  const [dateInfo, setDateInfo] = useState({});
  const [logSources, setLogSources] = useState({});
  const symptomRef = React.useRef({});
  const saveQueue = React.useRef(Promise.resolve());
  const [tab, setTab] = useState("home");
  const [cycleLength, setCycleLength] = useState(28);
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [saveMsg, setSaveMsg] = useState(null);
  // 提醒配置
  const [remindEnabled, setRemindEnabled] = useState(true);
  const [serverchanKey, setServerchanKey] = useState("");
  const [remindTimes, setRemindTimes] = useState("08:30");
  const [coupleMode, setCoupleMode] = useState(true);
  const [reminderMsg, setReminderMsg] = useState(null);
  const [careCtx, setCareCtx] = useState(null);
  const careRequest = React.useRef(0);

  const cycleStart = new Date(`${savedCycle.periodStart}T00:00:00`);
  const phase = getPhase(day);

  function queueSave(action) {
    const pending = saveQueue.current.then(action).catch(() => false);
    saveQueue.current = pending;
    return pending;
  }
  function saveFailed() {
    setSaveMsg("保存失败，原记录已保留，请重试");
    setTimeout(() => setSaveMsg(null), 3000);
    return false;
  }
  function logMood(logDate, score) {
    return queueSave(async () => {
      const result = await apiPost("/log_mood", { day: 0, date: logDate, score });
      if (!result?.success) return saveFailed();
      setMoodLog(prev => ({ ...prev, [result.date]: result.score }));
      setLogSources(prev => ({ ...prev, [result.date]: { ...prev[result.date], mood: { source: "manual" } } }));
      setDateInfo(prev => ({ ...prev, [result.date]: { day: result.day, phase: result.phase } }));
      const request = ++careRequest.current;
      if (score >= 1 && score <= 4) {
        apiPost("/care_low_mood", { day: result.day, date: result.date, score, phase: result.phase })
          .then(care => {
            if (request === careRequest.current && !care?.skipped) {
              setCareCtx(care || { memora_ok: false, related: [] });
            }
          });
      }
      return true;
    });
  }
  function toggleSymptom(logDate, symptom) {
    return queueSave(async () => {
      const current = symptomRef.current[logDate] || [];
      const next = symptom === "__good__"
        ? (current.includes("状态良好") ? [] : ["状态良好"])
        : (current.includes(symptom) ? current.filter(x => x !== symptom) : [...current.filter(x => x !== "状态良好"), symptom]);
      const result = await apiPost("/log_symptoms", { day: 0, date: logDate, symptoms: next });
      if (!result?.success) return saveFailed();
      symptomRef.current = { ...symptomRef.current, [result.date]: result.symptoms };
      setSymptomLog(symptomRef.current);
      setLogSources(prev => ({ ...prev, [result.date]: { ...prev[result.date], symptoms: { source: "manual" } } }));
      setDateInfo(prev => ({ ...prev, [result.date]: { day: result.day, phase: result.phase } }));
      return true;
    });
  }

  useEffect(() => {
    (async () => {
      const logs = await apiGet("/get_logs");
      if (logs) {
        if (logs.moodLog) setMoodLog(logs.moodLog);
        if (logs.symptomLog) { symptomRef.current = logs.symptomLog; setSymptomLog(logs.symptomLog); }
        if (logs.dateInfo) setDateInfo(logs.dateInfo);
        if (logs.logSources) setLogSources(logs.logSources);
      }
      const cfg = await apiGet("/get_config");
      if (cfg) {
        applySavedCycle(cfg);
      }
      const rem = await apiGet("/reminder_config");
      if (rem) {
        if (rem.enabled != null) setRemindEnabled(rem.enabled);
        if (rem.serverchan_key != null) setServerchanKey(rem.serverchan_key);
        if (rem.times) setRemindTimes(rem.times);
        if (rem.couple_mode != null) setCoupleMode(rem.couple_mode);
      }
    })();
  }, []);

  useEffect(() => {
    if (tab !== "home") return;
    let active = true;
    const request = careRequest.current;
    apiGet("/care/emotion_history?days=30").then(result => {
      if (active && request === careRequest.current) setCareCtx(result || { memora_ok: false, related: [] });
    });
    return () => { active = false; };
  }, [tab]);

  function applySavedCycle(result) {
    setSavedCycle(result);
    setCycleLength(result.cycleLength);
    setPeriodStart(result.periodStart || "");
    setPeriodEnd(result.periodEnd || "");
    setDay(cycleDayFromStart(result.periodStart, result.cycleLength));
  }

  async function periodChanged(result) {
    applySavedCycle(result);
    const logs = await apiGet("/get_logs");
    if (logs?.dateInfo) setDateInfo(logs.dateInfo);
  }

  async function saveConfig() {
    const result = await postPeriodAction("/save_config", { cycleLength, periodStart, periodEnd });
    if (result.success) await periodChanged(result);
    setSaveMsg(result.success ? "\u5468\u671f\u8bbe\u7f6e\u5df2\u4fdd\u5b58" : result.detail);
    setTimeout(() => setSaveMsg(null), 3000);
  }

  async function saveReminder() {
    const r = await apiPost("/reminder_config", { enabled: remindEnabled, serverchan_key: serverchanKey, times: remindTimes, couple_mode: coupleMode });
    setReminderMsg(r ? "提醒设置已保存 ✓" : "保存失败，请重试");
    setTimeout(() => setReminderMsg(null), 3000);
  }

  async function testReminder() {
    setReminderMsg("正在测试推送…");
    const r = await apiPost("/reminder_test", {});
    setReminderMsg(r && r.success ? "推送已发出，去微信看看 📲" : (r ? "已触发但没推送：可能没配SendKey，或此刻无需提醒" : "测试失败，请重试"));
    setTimeout(() => setReminderMsg(null), 4000);
  }

  // 各阶段天空背景配色（绿蓝换成温柔色）
  const PHASE_SKY = {
    月经期: { from: "#2A1A2E", to: "#3D2438", stars: "#F0D0D8", accent: C.pink },
    卵泡期: { from: "#1E1A2E", to: "#2C2442", stars: "#E0D4F4", accent: "#C4B8E0" },
    排卵期: { from: "#1E2030", to: "#2A2C44", stars: "#F0E8D8", accent: "#C8C0B0" },
    黄体期: { from: "#221A30", to: "#332548", stars: "#E4D0F0", accent: C.purple },
  };
  const sky = PHASE_SKY[phase.name] || PHASE_SKY["黄体期"];

  // 星星：非均匀分布，大小不一
  const STARS = Array.from({ length: 45 }, (_, i) => ({
    x: (i * 83 + i * i * 17 + i * 3) % 100,
    y: (i * 61 + i * i * 11 + i * 7) % 70,
    r: [0.5, 0.8, 1, 1, 1.2, 1.5, 2][i % 7],
    delay: (i * 0.6 + (i % 5) * 0.4) % 5,
    dur: 1.5 + (i % 4) * 0.8,
  }));

  // 流星：5颗，位置散乱，各自周期（period=整个循环秒数，慢慢等），angle=倾斜角
  const METEORS = [
    { left: "68%", top: "6%",  angle: 32, period: 31, initDelay: 0  },
    { left: "12%", top: "22%", angle: 28, period: 43, initDelay: 7  },
    { left: "45%", top: "3%",  angle: 38, period: 27, initDelay: 18 },
    { left: "4%",  top: "14%", angle: 35, period: 52, initDelay: 3  },
    { left: "80%", top: "30%", angle: 30, period: 38, initDelay: 24 },
  ];

  return (
    <PhaseContext.Provider value={getPhase}>
    <SourceContext.Provider value={logSources}>
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: "system-ui, -apple-system, sans-serif" }}>
      <div style={{ paddingBottom: 80, overflowX: "hidden" }}>

        {tab === "home" && (
          <>
            {/* 星空顶部区域 */}
            <div style={{
              background: `linear-gradient(180deg, ${sky.from} 0%, ${sky.to} 60%, ${C.bg} 100%)`,
              paddingBottom: 32,
              position: "relative",
              overflow: "hidden",
              transition: "background 0.8s ease",
            }}>
              {/* 星星 SVG */}
              <svg style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
                <defs>
                  <style>{`
                    @keyframes twinkle {
                      0%, 100% { opacity: 0.15; }
                      50% { opacity: 0.85; }
                    }
                    ${METEORS.map((m, i) => `
                    @keyframes meteor${i} {
                      0%   { opacity: 0; transform: rotate(${m.angle}deg) translateX(0px); }
                      3%   { opacity: 0.9; }
                      12%  { opacity: 0; transform: rotate(${m.angle}deg) translateX(110px); }
                      100% { opacity: 0; transform: rotate(${m.angle}deg) translateX(110px); }
                    }`).join("")}
                  `}</style>
                </defs>
                {STARS.map((s, i) => (
                  <circle key={i} cx={`${s.x}%`} cy={`${s.y}%`} r={s.r}
                    fill={sky.stars}
                    style={{ animation: `twinkle ${s.dur}s ease-in-out infinite`, animationDelay: `${s.delay}s` }} />
                ))}
              </svg>

              {/* 流星：div实现渐变尾巴，各自慢周期 */}
              {METEORS.map((m, i) => (
                <div key={i} style={{
                  position: "absolute",
                  left: m.left, top: m.top,
                  width: 70, height: 1.5,
                  borderRadius: 1,
                  background: `linear-gradient(90deg, transparent 0%, ${sky.stars} 100%)`,
                  transformOrigin: "left center",
                  pointerEvents: "none",
                  animation: `meteor${i} ${m.period}s linear infinite`,
                  animationDelay: `${m.initDelay}s`,
                  opacity: 0,
                }} />
              ))}

              {/* 顶部标题 */}
              <div style={{ padding: "44px 16px 14px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", position: "relative" }}>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#F5F0FA", fontFamily: "Georgia, serif", letterSpacing: "-0.01em" }}>Selene</div>
                  <div style={{ fontSize: 11, color: sky.stars + "99", marginTop: 2 }}>与你同步的月亮</div>
                </div>
                <div style={{ background: "rgba(255,255,255,0.12)", borderRadius: 12, padding: "6px 13px", fontSize: 12, color: sky.stars }}>{day > 0 ? `第 ${day} 天` : "待记录"}</div>
              </div>

              {/* 阶段条 */}
              <div style={{ padding: "0 16px 16px", position: "relative" }}>
                <PhaseBar currentDay={day} />
              </div>

              {/* 月相环 */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "0 32px 14px", position: "relative" }}>
                <MoonRing day={day} total={savedCycle.cycleLength} phaseLabel={savedCycle.status?.phase_label} />
              </div>


            </div>

            {/* 内容卡片区 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "16px 16px 0" }}>
              <PeriodStatus status={savedCycle.status} />
              <PeriodActions config={savedCycle} onChange={periodChanged} />
              <MoodLogger day={day} moodLog={moodLog} onLog={logMood} />
              {careCtx && (
                <Card>
                  <SectionLabel>最近的心情</SectionLabel>
                  {!careCtx.memora_ok ? (
                    <div style={{ color: C.textLight, fontSize: 13 }}>记忆库暂时未连接，不影响在 Selene 记录心情。</div>
                  ) : (careCtx.related || []).length === 0 ? (
                    <div style={{ color: C.textLight, fontSize: 13 }}>暂时没有相关记忆。</div>
                  ) : (careCtx.related || []).slice(0, 3).map((memory, index) => (
                    <div key={index} style={{ color: C.text, fontSize: 13, lineHeight: 1.6, marginBottom: 8 }}>
                      <span style={{ color: C.textLight }}>{memory.time_ago} </span>{memory.content}
                    </div>
                  ))}
                </Card>
              )}
              <SymptomLogger day={day} symptomLog={symptomLog} onToggle={toggleSymptom} />
              <MoodChartSmall currentDay={day} moodLog={moodLog} periodStart={savedCycle.periodStart} />
              {savedCycle.periodStart && <NextPrediction cycleStart={cycleStart} cycleLength={savedCycle.cycleLength} />}
              <TodayCard day={day} />
            </div>
          </>
        )}

        {tab === "log" && (
          <LogPage currentDay={day} moodLog={moodLog} symptomLog={symptomLog} periodStart={savedCycle.periodStart} dateInfo={dateInfo} onLog={logMood} onToggle={toggleSymptom} />
        )}

        {tab === "stats" && (
          <StatsPage moodLog={moodLog} symptomLog={symptomLog} currentDay={day} dateInfo={dateInfo} />
        )}

        {tab === "me" && (
          <MePage cycleLength={cycleLength} setCycleLength={setCycleLength}
            periodStart={periodStart} setPeriodStart={setPeriodStart}
            periodEnd={periodEnd} setPeriodEnd={setPeriodEnd}
            onSaveConfig={saveConfig}
            remindEnabled={remindEnabled} setRemindEnabled={setRemindEnabled}
            serverchanKey={serverchanKey} setServerchanKey={setServerchanKey}
            remindTimes={remindTimes} setRemindTimes={setRemindTimes}
            coupleMode={coupleMode} setCoupleMode={setCoupleMode}
            onSaveReminder={saveReminder} onTestReminder={testReminder}
            reminderMsg={reminderMsg} />
        )}
      </div>

      <BottomNav active={tab} onChange={setTab} />
      {saveMsg && (
        <div style={{ position: "fixed", bottom: 90, left: "50%", transform: "translateX(-50%)", background: C.purpleDeep, color: C.white, padding: "10px 22px", borderRadius: 24, fontSize: 13, fontWeight: 600, boxShadow: "0 4px 16px rgba(0,0,0,0.2)", zIndex: 200 }}>
          {saveMsg}
        </div>
      )}
    </div>
    </SourceContext.Provider>
    </PhaseContext.Provider>
  );
}

(function(){var root=ReactDOM.createRoot(document.getElementById("root"));root.render(React.createElement(Selene));})();
