// Shared UI primitives + API helper. Used by App.jsx and AgentsView.jsx.

export const getUser = () => {
  try { return JSON.parse(localStorage.getItem("ka_user")) || null; } catch { return null; }
};
export const setUser = (u) => {
  if (u) localStorage.setItem("ka_user", JSON.stringify(u));
  else localStorage.removeItem("ka_user");
};

const headers = () => {
  const h = { "Content-Type": "application/json" };
  const u = getUser();
  if (u?.id) h["X-User-Id"] = String(u.id);
  return h;
};

export const api = {
  post: (path, body) =>
    fetch(path, { method: "POST", headers: headers(), body: JSON.stringify(body) }).then(r => r.json()),
  put: (path, body) =>
    fetch(path, { method: "PUT", headers: headers(), body: JSON.stringify(body) }).then(r => r.json()),
  get: (path) => fetch(path, { headers: headers() }).then(r => r.json()),
  del: (path) => fetch(path, { method: "DELETE", headers: headers() }).then(r => r.json()),
};

export const fmt = {
  eur: (v) => v != null ? `${Number(v).toLocaleString("de-DE", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €` : "—",
  pct: (v) => `${(v * 100).toFixed(0)}%`,
  km: (v) => v != null ? `${Number(v).toLocaleString("de-DE")} km` : "—",
  time: (iso) => iso ? new Date(iso).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—",
};

export const Icon = ({ name, size = 16 }) => {
  const icons = {
    search: <><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></>,
    trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4h6v2" /></>,
    down: <><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></>,
    link: <><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></>,
    tag: <><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" /><line x1="7" y1="7" x2="7.01" y2="7" /></>,
    chart: <><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></>,
    x: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
    car: <><rect x="1" y="3" width="15" height="13" /><polygon points="16 8 20 8 23 11 23 16 16 16 16 8" /><circle cx="5.5" cy="18.5" r="2.5" /><circle cx="18.5" cy="18.5" r="2.5" /></>,
    brain: <><path d="M9.5 2a2.5 2.5 0 015 0c0 .95-.56 1.76-1.36 2.14A6 6 0 0118 10v1a6 6 0 01-6 6v3" /><path d="M9.5 2C8.12 2 7 3.12 7 4.5c0 .95.56 1.76 1.36 2.14A6 6 0 006 10v1a6 6 0 006 6" /></>,
    info: <><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></>,
    bot: <><rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4" /><line x1="8" y1="16" x2="8" y2="16" /><line x1="16" y1="16" x2="16" y2="16" /></>,
    play: <><polygon points="5 3 19 12 5 21 5 3" /></>,
    pause: <><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></>,
    edit: <><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></>,
    clock: <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>,
    key: <><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" /></>,
    refresh: <><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" /></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></>,
    note: <><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></>,
    chevronDown: <><polyline points="6 9 12 15 18 9" /></>,
    chevronUp: <><polyline points="18 15 12 9 6 15" /></>,
    plus: <><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>,
    alert: <><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
    check: <><polyline points="20 6 9 17 4 12" /></>,
    menu: <><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="18" x2="21" y2="18" /></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ display: "inline-block", verticalAlign: "middle", flexShrink: 0 }}>
      {icons[name]}
    </svg>
  );
};

export const Badge = ({ children, color = "default", title }) => {
  const colors = {
    default: { bg: "rgba(15,23,42,0.06)", text: "#64748B" },
    green: { bg: "#D1FAE5", text: "#047857" },
    red: { bg: "#FFE4E6", text: "#BE123C" },
    amber: { bg: "#FEF3C7", text: "#B45309" },
    blue: { bg: "#E0F2FE", text: "#0369A1" },
    purple: { bg: "#E0E7FF", text: "#4338CA" },
  };
  const c = colors[color] || colors.default;
  return (
    <span title={title} style={{
      background: c.bg, color: c.text, borderRadius: 999, padding: "2px 10px",
      fontSize: 11, fontWeight: 800, letterSpacing: "0.02em",
      whiteSpace: "nowrap",
    }}>
      {children}
    </span>
  );
};

// V2E stat-card tones: colored top border + matching icon chip
export const STAT_TONES = {
  indigo: { border: "#6366F1", chipBg: "#E0E7FF", chipText: "#4338CA" },
  cyan:   { border: "#22D3EE", chipBg: "#CFFAFE", chipText: "#0E7490" },
  green:  { border: "#10B981", chipBg: "#D1FAE5", chipText: "#047857" },
  amber:  { border: "#F59E0B", chipBg: "#FEF3C7", chipText: "#B45309" },
  rose:   { border: "#F43F5E", chipBg: "#FFE4E6", chipText: "#BE123C" },
  blue:   { border: "#3B82F6", chipBg: "#DBEAFE", chipText: "#1D4ED8" },
};

export const Stat = ({ label, value, sub, color, tone, icon }) => {
  const t = STAT_TONES[tone] || STAT_TONES.indigo;
  return (
    <div className="stat-card" style={{ padding: "14px 18px 16px", borderTopColor: t.border }}>
      {icon && (
        <div style={{
          width: 32, height: 32, borderRadius: 9, background: t.chipBg, color: t.chipText,
          display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 8,
        }}>
          <Icon name={icon} size={15} />
        </div>
      )}
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, marginTop: 2, color: color || "var(--text)" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
};

export const Spinner = ({ size = 20 }) => (
  <div role="status" aria-label="Lädt" style={{
    width: size, height: size, border: `2px solid var(--border2)`,
    borderTop: `2px solid var(--accent)`, borderRadius: "50%",
    animation: "spin 0.8s linear infinite", display: "inline-block"
  }} />
);

export const ProgressBar = ({ value }) => (
  <div style={{ background: "var(--border)", borderRadius: 4, height: 4, overflow: "hidden" }}>
    <div style={{
      height: "100%", width: `${value}%`, background: "var(--accent)",
      borderRadius: 4, transition: "width 0.4s ease"
    }} />
  </div>
);

export const InputField = ({ label, value, onChange, placeholder, type = "text", width = 100, id }) => {
  const inputId = id || `f-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div style={{ flex: `0 0 ${width}px` }}>
      <label htmlFor={inputId} className="field-label">{label}</label>
      <input id={inputId} className="input" type={type} value={value}
        onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  );
};
