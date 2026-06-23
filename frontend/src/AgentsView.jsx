import { useState, useEffect, useCallback, useRef } from "react";
import { api, fmt, Icon, Badge, Spinner } from "./ui.jsx";

const INTERVALS = [10, 15, 20, 30, 60, 120, 240];
const MODEL_SUGGESTIONS = [
  "deepseek/deepseek-chat-v3.1",
  "deepseek/deepseek-v3.2-exp",
  "google/gemini-2.5-flash-lite",
  "qwen/qwen3-235b-a22b",
  "minimax/minimax-m2",
  "openai/gpt-oss-120b",
];

const EMPTY_FORM = {
  name: "", query: "", category: "all", plz: "", radius: 0,
  price_min: "", price_max: "", year_from: "", year_to: "", km_max: "", ps_min: "",
  max_pages: 3, interval_minutes: 20, exclude: "", custom_prompt: "", active: true,
  max_age_days: 60,
};

const VERDICT_BADGE = {
  top_deal: { color: "green", label: "TOP DEAL" },
  ok: { color: "blue", label: "OK" },
  reject: { color: "red", label: "ABGELEHNT" },
};

const fieldNum = (v) => Number(v) || 0;

// ── Settings panel ─────────────────────────────────────────────────────────────
const SettingsPanel = ({ settings, onSaved }) => {
  const [key, setKey] = useState("");
  const [model, setModel] = useState(settings?.openrouter_model || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { setModel(settings?.openrouter_model || ""); }, [settings?.openrouter_model]);

  const save = async () => {
    setSaving(true);
    try {
      const body = { openrouter_model: model.trim() };
      if (key.trim()) body.openrouter_api_key = key.trim();
      await api.put("/api/settings", body);
      setKey("");
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ color: "var(--accent)" }}><Icon name="key" size={15} /></span>
        <span style={{ fontSize: 13, fontWeight: 700 }}>LLM-Einstellungen (OpenRouter)</span>
        {settings?.openrouter_key_set
          ? <Badge color="green" title={settings.openrouter_key_preview}>Key gesetzt</Badge>
          : <Badge color="red">Kein Key</Badge>}
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div style={{ flex: "1 1 260px" }}>
          <label htmlFor="or-key" className="field-label">
            API-Key {settings?.openrouter_key_set && <span style={{ color: "var(--muted)" }}>({settings.openrouter_key_preview} — leer lassen zum Behalten)</span>}
          </label>
          <input id="or-key" className="input" type="password" value={key}
            onChange={e => setKey(e.target.value)} placeholder="sk-or-v1-…" autoComplete="off" />
        </div>
        <div style={{ flex: "1 1 240px" }}>
          <label htmlFor="or-model" className="field-label">Modell</label>
          <input id="or-model" className="input" list="model-suggestions" value={model}
            onChange={e => setModel(e.target.value)} placeholder={settings?.default_model} />
          <datalist id="model-suggestions">
            {MODEL_SUGGESTIONS.map(m => <option key={m} value={m} />)}
          </datalist>
        </div>
        <button className="btn btn-primary" onClick={save} disabled={saving} style={{ height: 38 }}>
          {saving ? <Spinner size={14} /> : saved ? <Icon name="check" size={14} /> : null}
          {saved ? "Gespeichert" : "Speichern"}
        </button>
      </div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.6 }}>
        Empfehlung: günstiges, starkes Modell — z.B. <code className="mono">deepseek/deepseek-chat-v3.1</code>.
        Der Key wird lokal in der SQLite-DB gespeichert und nur an openrouter.ai gesendet.
      </div>
    </div>
  );
};

// ── Product form (create / edit) ───────────────────────────────────────────────
const ProductForm = ({ initial, onSubmit, onCancel }) => {
  const [f, setF] = useState(initial || EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF(prev => ({ ...prev, [k]: e?.target ? e.target.value : e }));
  const isEdit = !!initial?.id;
  const isCars = f.category === "cars";

  const submit = async () => {
    if (!f.name.trim() || !f.query.trim()) return;
    setBusy(true);
    try {
      await onSubmit({
        ...f,
        radius: fieldNum(f.radius), price_min: fieldNum(f.price_min), price_max: fieldNum(f.price_max),
        year_from: fieldNum(f.year_from), year_to: fieldNum(f.year_to),
        km_max: fieldNum(f.km_max), ps_min: fieldNum(f.ps_min),
        max_pages: fieldNum(f.max_pages) || 3, interval_minutes: fieldNum(f.interval_minutes) || 20,
        max_age_days: fieldNum(f.max_age_days),
      });
    } finally {
      setBusy(false);
    }
  };

  // Plain function (not a component): inline JSX keeps input identity stable,
  // so typing never loses focus.
  const F = ({ label, k, type = "text", placeholder, flex = "0 0 110px" }) => (
    <div key={k} style={{ flex }}>
      <label htmlFor={`pf-${k}`} className="field-label">{label}</label>
      <input id={`pf-${k}`} className="input" type={type} value={f[k]}
        onChange={set(k)} placeholder={placeholder} />
    </div>
  );

  return (
    <div className="card" style={{ padding: "16px 20px", marginBottom: 16, borderColor: "rgba(99,102,241,0.5)" }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>
        {isEdit ? `Agent bearbeiten: ${initial.name}` : "Neuen Produkt-Agenten anlegen"}
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        {F({ label: "Produktname *", k: "name", placeholder: "z.B. PlayStation 5", flex: "1 1 180px" })}
        {F({ label: "Suchbegriff *", k: "query", placeholder: "z.B. PlayStation 5", flex: "1 1 180px" })}
        <div style={{ flex: "0 0 140px" }}>
          <label htmlFor="pf-category" className="field-label">Kategorie</label>
          <select id="pf-category" className="input" value={f.category} onChange={set("category")}>
            <option value="all">Alle Kategorien</option>
            <option value="cars">Autos (PKW)</option>
          </select>
        </div>
        {F({ label: "PLZ", k: "plz", placeholder: "z.B. 65428" })}
        <div style={{ flex: "0 0 110px" }}>
          <label htmlFor="pf-radius" className="field-label">Umkreis</label>
          <select id="pf-radius" className="input" value={f.radius} onChange={set("radius")}>
            <option value={0}>Ganz DE</option>
            {[10, 20, 50, 100, 200].map(r => <option key={r} value={r}>{r} km</option>)}
          </select>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        {F({ label: "Min. Preis €", k: "price_min", type: "number", placeholder: "200" })}
        {F({ label: "Max. Preis €", k: "price_max", type: "number", placeholder: "300" })}
        {isCars && <>
          {F({ label: "Baujahr von", k: "year_from", type: "number", placeholder: "2014" })}
          {F({ label: "Baujahr bis", k: "year_to", type: "number", placeholder: "2020" })}
          {F({ label: "Max. KM", k: "km_max", type: "number", placeholder: "150000" })}
          {F({ label: "Min. PS", k: "ps_min", type: "number", placeholder: "150" })}
        </>}
        <div style={{ flex: "0 0 130px" }}>
          <label htmlFor="pf-interval" className="field-label">Intervall</label>
          <select id="pf-interval" className="input" value={f.interval_minutes} onChange={set("interval_minutes")}>
            {INTERVALS.map(m => <option key={m} value={m}>alle {m >= 60 ? `${m / 60} Std.` : `${m} Min.`}</option>)}
          </select>
        </div>
        <div style={{ flex: "0 0 150px" }}>
          <label htmlFor="pf-age" className="field-label">Inserat max. Alter</label>
          <select id="pf-age" className="input" value={f.max_age_days} onChange={set("max_age_days")}>
            {[7, 14, 30, 60, 90, 180].map(d => <option key={d} value={d}>{d} Tage</option>)}
            <option value={0}>egal</option>
          </select>
        </div>
        <div style={{ flex: "0 0 110px" }}>
          <label htmlFor="pf-pages" className="field-label">Seiten/Runde</label>
          <select id="pf-pages" className="input" value={f.max_pages} onChange={set("max_pages")}>
            {[1, 2, 3, 5, 8, 10].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        {F({ label: "Ausschlusswörter (Komma)", k: "exclude", placeholder: "defekt,controller,spiel", flex: "1 1 220px" })}
      </div>

      <div style={{ marginBottom: 12 }}>
        <label htmlFor="pf-prompt" className="field-label">
          Zusatz-Prompt für das LLM <span style={{ color: "var(--muted)" }}>(optional — z.B. „Unfallwagen aussortieren", „nur mit OVP und 2 Controllern")</span>
        </label>
        <textarea id="pf-prompt" className="input" rows={2} value={f.custom_prompt}
          onChange={set("custom_prompt")} style={{ resize: "vertical", minHeight: 56 }}
          placeholder="Worauf soll der Agent besonders achten?" />
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" onClick={submit}
          disabled={busy || !f.name.trim() || !f.query.trim()}>
          {busy ? <Spinner size={14} /> : <Icon name="check" size={14} />}
          {isEdit ? "Speichern" : "Agent starten"}
        </button>
        <button className="btn" onClick={onCancel}>Abbrechen</button>
      </div>
    </div>
  );
};

// ── Deal card ──────────────────────────────────────────────────────────────────
const DealCard = ({ d }) => {
  const vb = VERDICT_BADGE[d.verdict] || VERDICT_BADGE.ok;
  return (
    <a href={d.url} target="_blank" rel="noreferrer" className="deal-card"
      style={{
        display: "block", background: "var(--surface2)", borderRadius: 8,
        padding: "10px 12px", color: "var(--text)", textDecoration: "none",
        border: `1px solid ${d.verdict === "top_deal" ? "rgba(5,150,105,0.4)" : "var(--border)"}`,
      }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "baseline", marginBottom: 4 }}>
        <span style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.title}</span>
        <span style={{ fontFamily: "var(--mono)", fontWeight: 700, color: "var(--green)", whiteSpace: "nowrap" }}>{fmt.eur(d.price)}</span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 5, alignItems: "center" }}>
        <Badge color={vb.color}>{vb.label}</Badge>
        {d.score != null && <Badge color="amber" title="Deal-Score des Agenten">Score {d.score}</Badge>}
        {d.fake_risk != null && d.fake_risk > 40 &&
          <Badge color="red" title="Fake-/Scam-Risiko laut Agent">Fake-Risiko {d.fake_risk}%</Badge>}
        {d.date_posted && (
          <span style={{ fontSize: 11, color: "var(--muted)", display: "inline-flex", alignItems: "center", gap: 3 }}
            title="Veroeffentlicht am">
            <Icon name="clock" size={11} /> {d.date_posted}
          </span>
        )}
        {d.location && <span style={{ fontSize: 11, color: "var(--muted)" }}>{d.location}</span>}
        {d.km != null && <span style={{ fontSize: 11, color: "var(--muted)" }}>{fmt.km(d.km)}</span>}
        {d.year != null && <span style={{ fontSize: 11, color: "var(--muted)" }}>{d.year}</span>}
      </div>
      {d.reason && <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{d.reason}</div>}
    </a>
  );
};

// ── Run row ────────────────────────────────────────────────────────────────────
const RunRow = ({ run }) => {
  const [open, setOpen] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const market = run.market_json ? JSON.parse(run.market_json) : null;
  const deals = run.deals_json ? JSON.parse(run.deals_json) : [];
  const isErr = run.status === "error";
  const isRunning = run.status === "running";

  return (
    <div style={{ background: "var(--surface2)", borderRadius: 8, border: "1px solid var(--border)" }}>
      <button onClick={() => setOpen(o => !o)} aria-expanded={open}
        style={{
          display: "flex", alignItems: "center", gap: 10, width: "100%", flexWrap: "wrap",
          background: "transparent", border: "none", color: "var(--text)",
          padding: "10px 12px", textAlign: "left", fontSize: 12,
        }}>
        <span style={{ color: "var(--muted)", fontFamily: "var(--mono)", whiteSpace: "nowrap" }}>{fmt.time(run.started_at)}</span>
        {isRunning ? <Spinner size={12} /> :
          isErr ? <Badge color="red">Fehler</Badge> :
          <Badge color={run.deal_count > 0 ? "green" : "default"}>{run.deal_count} gute Inserate</Badge>}
        <span style={{ color: "var(--muted)" }}>
          {run.raw_count} gescraped · {run.new_count} neu · {run.reviewed_count} reviewt
        </span>
        {run.query_used && <span style={{ fontFamily: "var(--mono)", color: "var(--blue)", fontSize: 11 }}>„{run.query_used}"</span>}
        <span style={{ flex: 1 }} />
        <Icon name={open ? "chevronUp" : "chevronDown"} size={14} />
      </button>

      {open && (
        <div style={{ padding: "0 12px 12px", borderTop: "1px solid var(--border)" }}>
          {isErr && (
            <div role="alert" style={{
              marginTop: 10, padding: "8px 12px", borderRadius: 6, fontSize: 12,
              background: "rgba(194,54,47,0.06)", border: "1px solid rgba(194,54,47,0.25)", color: "var(--red)",
            }}>
              <Icon name="alert" size={13} /> {run.error}
            </div>
          )}
          {market && (
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", margin: "10px 0", fontSize: 12, fontFamily: "var(--mono)", color: "var(--muted)" }}>
              <span>Median <strong style={{ color: "var(--text)" }}>{fmt.eur(market.median_price)}</strong></span>
              <span>Ø <strong style={{ color: "var(--text)" }}>{fmt.eur(market.avg_price)}</strong></span>
              <span>Spanne {fmt.eur(market.min_price)}–{fmt.eur(market.max_price)}</span>
              <span>{market.count} Inserate</span>
              {run.search_id && (
                <a href={`/api/export/${run.search_id}`} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>
                  CSV der Runde
                </a>
              )}
            </div>
          )}
          {deals.length > 0 ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 8 }}>
              {deals.map((d, i) => <DealCard key={i} d={d} />)}
            </div>
          ) : !isErr && !isRunning && (
            <div style={{ fontSize: 12, color: "var(--muted)", fontStyle: "italic", marginTop: 8 }}>
              Keine guten Inserate in dieser Runde.
            </div>
          )}
          {run.log && (
            <div style={{ marginTop: 10 }}>
              <button className="btn btn-ghost" onClick={() => setShowLog(s => !s)} style={{ fontSize: 11, padding: "3px 8px" }}>
                {showLog ? "Log ausblenden" : "Agenten-Log anzeigen"}
              </button>
              {showLog && (
                <pre style={{
                  marginTop: 6, fontSize: 11, color: "var(--muted)",
                  whiteSpace: "pre-wrap", background: "var(--surface2)", borderRadius: 8, padding: "8px 10px",
                  maxHeight: 240, overflowY: "auto",
                }}>{run.log}</pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Product card ───────────────────────────────────────────────────────────────
const ProductCard = ({ p, onEdit, onChanged }) => {
  const [tab, setTab] = useState(null); // null | runs | top | notes
  const [runs, setRuns] = useState([]);
  const [top, setTop] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const loadTab = useCallback(async (t) => {
    if (t === "runs") setRuns((await api.get(`/api/watch/products/${p.id}/runs`)).runs || []);
    if (t === "top") setTop((await api.get(`/api/watch/products/${p.id}/top`)).top || []);
  }, [p.id]);

  useEffect(() => { if (tab) loadTab(tab); }, [tab, loadTab, p.last_run_at, p.is_running]);

  const action = async (fn) => {
    setBusy(true); setErr("");
    try {
      const res = await fn();
      if (res?.detail) setErr(res.detail);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const intervalLabel = p.interval_minutes >= 60 ? `${p.interval_minutes / 60} Std.` : `${p.interval_minutes} Min.`;
  const nextRun = p.active && p.next_run_at ? new Date(p.next_run_at) : null;
  const nextIn = nextRun ? Math.max(0, Math.round((nextRun - Date.now()) / 60000)) : null;
  const refined = p.current_query && p.current_query !== p.query;
  let aliases = [];
  try { aliases = JSON.parse(p.query_aliases || "[]"); } catch { aliases = []; }
  aliases = Array.isArray(aliases) ? aliases : [];

  const criteria = [
    (p.price_min || p.price_max) && `${p.price_min || 0}–${p.price_max || "∞"} €`,
    p.plz && `PLZ ${p.plz}${p.radius ? ` +${p.radius}km` : ""}`,
    p.category === "cars" && "Autos",
    p.year_from && `ab ${p.year_from}`,
    p.km_max && `≤${Number(p.km_max).toLocaleString("de-DE")} km`,
    p.max_age_days > 0 && `max. ${p.max_age_days} Tage alt`,
  ].filter(Boolean);

  return (
    <div className="card" style={{
      padding: "14px 16px",
      borderColor: p.is_running ? "var(--accent)" : p.active ? "var(--border)" : "var(--border)",
      opacity: p.active ? 1 : 0.65,
    }}>
      {/* Head */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, flexWrap: "wrap" }}>
        <span style={{ color: p.is_running ? "var(--accent)" : "var(--muted)", marginTop: 2 }}>
          <Icon name="bot" size={18} />
        </span>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ fontSize: 15, fontWeight: 700, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {p.name}
            {p.is_running && <Badge color="amber">SUCHT GERADE…</Badge>}
            {!p.active && <Badge>PAUSIERT</Badge>}
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <span className="mono">„{refined ? p.current_query : p.query}"</span>
            {refined && (
              <Badge color="purple" title={`Vom Agenten verfeinert — Original: „${p.query}"`}>
                verfeinert
              </Badge>
            )}
            {aliases.map((a, i) => (
              <span key={`a${i}`} className="mono" style={{ color: "var(--accent)" }}
                title="Synonym vom Agenten — wird zusätzlich durchsucht">+ „{a}"</span>
            ))}
            {criteria.map((c, i) => <Badge key={i}>{c}</Badge>)}
            <Badge color="blue" title="Suchintervall">alle {intervalLabel}</Badge>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button className="btn" onClick={() => action(() => api.post(`/api/watch/products/${p.id}/run-now`))}
            disabled={busy || p.is_running} title="Sofort eine Suchrunde starten">
            <Icon name="play" size={13} /> Jetzt suchen
          </button>
          <button className="btn" onClick={() => action(() => api.post(`/api/watch/products/${p.id}/toggle`))}
            disabled={busy} title={p.active ? "Agent pausieren" : "Agent aktivieren"}>
            <Icon name={p.active ? "pause" : "play"} size={13} /> {p.active ? "Pause" : "Aktivieren"}
          </button>
          <button className="btn" onClick={() => onEdit(p)} disabled={busy} aria-label={`${p.name} bearbeiten`}>
            <Icon name="edit" size={13} />
          </button>
          <button className="btn btn-danger" disabled={busy} aria-label={`${p.name} löschen`}
            onClick={() => { if (confirm(`Agent „${p.name}" und alle Runden löschen?`)) action(() => api.del(`/api/watch/products/${p.id}`)); }}>
            <Icon name="trash" size={13} />
          </button>
        </div>
      </div>

      {err && (
        <div role="alert" style={{
          marginTop: 8, padding: "6px 10px", borderRadius: 6, fontSize: 12,
          background: "rgba(194,54,47,0.06)", border: "1px solid rgba(194,54,47,0.25)", color: "var(--red)",
        }}>
          <Icon name="alert" size={12} /> {err}
        </div>
      )}

      {/* Status line */}
      <div style={{ display: "flex", gap: 14, marginTop: 10, fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)", flexWrap: "wrap" }}>
        <span><Icon name="clock" size={11} /> Letzte Runde: {fmt.time(p.last_run_at)}</span>
        {p.active && nextIn != null && !p.is_running &&
          <span>Nächste: {nextIn === 0 ? "gleich" : `in ~${nextIn} Min.`}</span>}
        {p.custom_prompt && <span title={p.custom_prompt}><Icon name="note" size={11} /> eigener Prompt aktiv</span>}
      </div>

      {/* Sub-tabs */}
      <div style={{ display: "flex", gap: 4, marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
        {[["runs", "Suchrunden"], ["top", "Top-Liste"], ["notes", "Agenten-Notizen"]].map(([id, label]) => (
          <button key={id} onClick={() => setTab(tab === id ? null : id)}
            className="btn btn-ghost"
            style={{
              fontSize: 12, padding: "4px 10px",
              color: tab === id ? "var(--accent)" : "var(--muted)",
              borderBottom: tab === id ? "2px solid var(--accent)" : "2px solid transparent",
              borderRadius: 0,
            }}>
            {label}
          </button>
        ))}
      </div>

      {tab === "runs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 10 }}>
          {runs.length === 0 && <div style={{ fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>Noch keine Runden gelaufen.</div>}
          {runs.map(r => <RunRow key={r.id} run={r} />)}
        </div>
      )}

      {tab === "top" && (
        <div style={{ marginTop: 10 }}>
          {top.length === 0
            ? <div style={{ fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>Noch keine guten Inserate gefunden.</div>
            : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 8 }}>
                {top.map((d, i) => <DealCard key={i} d={{ ...d, fake_risk: null }} />)}
              </div>}
        </div>
      )}

      {tab === "notes" && (
        <div style={{ marginTop: 10 }}>
          {refined && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, fontSize: 12 }}>
              <span style={{ color: "var(--muted)" }}>
                Aktiver Suchbegriff: <span className="mono" style={{ color: "var(--blue)" }}>„{p.current_query}"</span>
                {" "}(Original: „{p.query}")
              </span>
              <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }}
                onClick={() => action(() => api.post(`/api/watch/products/${p.id}/reset-query`))}>
                <Icon name="refresh" size={11} /> zurücksetzen
              </button>
            </div>
          )}
          {p.notes
            ? <pre style={{
                fontSize: 12, color: "var(--text)", whiteSpace: "pre-wrap", lineHeight: 1.7,
                background: "var(--surface2)", borderRadius: 10, padding: "12px 14px", margin: 0,
                fontFamily: "var(--sans)",
              }}>{p.notes}</pre>
            : <div style={{ fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>
                Der Agent hat noch keine Kriterien-Notizen erstellt — sie entstehen nach der ersten Runde.
              </div>}
        </div>
      )}
    </div>
  );
};

// ── Main view ──────────────────────────────────────────────────────────────────
export default function AgentsView() {
  const [settings, setSettings] = useState(null);
  const [products, setProducts] = useState([]);
  const [editing, setEditing] = useState(null);   // null | {} (new) | product
  const [loaded, setLoaded] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    const [s, p] = await Promise.all([api.get("/api/settings"), api.get("/api/watch/products")]);
    setSettings(s);
    setProducts(p.products || []);
    setLoaded(true);
  }, []);

  useEffect(() => {
    load();
    pollRef.current = setInterval(load, 5000);
    return () => clearInterval(pollRef.current);
  }, [load]);

  const saveProduct = async (data) => {
    if (editing?.id) {
      await api.put(`/api/watch/products/${editing.id}`, data);
    } else {
      await api.post("/api/watch/products", data);
    }
    setEditing(null);
    await load();
  };

  const startEdit = (p) => setEditing({
    ...EMPTY_FORM, ...p,
    price_min: p.price_min || "", price_max: p.price_max || "",
    year_from: p.year_from || "", year_to: p.year_to || "",
    km_max: p.km_max || "", ps_min: p.ps_min || "",
    max_age_days: p.max_age_days ?? 60,
    active: !!p.active,
  });

  return (
    <div>
      <div className="hero-dark" style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        gap: 16, padding: "20px 26px", marginBottom: 16, flexWrap: "wrap",
      }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, display: "flex", alignItems: "center", gap: 10 }}>
            <Icon name="bot" size={20} />
            Produkt-Agenten
          </div>
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.78)", marginTop: 4, maxWidth: 680, lineHeight: 1.6 }}>
            Jeder Agent sucht in seinem Intervall selbständig nach deinem Produkt — auch mit vom LLM
            vorgeschlagenen Synonymen — prüft jedes neue Inserat (richtige Ware? Fake? guter Preis?),
            fasst alle Treffer zusammen und pflegt eigene Kriterien-Notizen.
          </div>
        </div>
        {!editing && (
          <button className="btn-hero" onClick={() => setEditing({ ...EMPTY_FORM })}>
            <Icon name="plus" size={14} /> Neuer Agent
          </button>
        )}
      </div>

      <SettingsPanel settings={settings} onSaved={load} />

      {settings && !settings.openrouter_key_set && (
        <div role="alert" style={{
          marginBottom: 16, padding: "10px 14px", borderRadius: 10, fontSize: 12,
          background: "rgba(217,119,6,0.07)", border: "1px solid rgba(217,119,6,0.3)", color: "#B45309",
        }}>
          <Icon name="alert" size={13} /> Ohne OpenRouter-Key können Agenten nicht reviewen. Key oben eintragen —
          erstellen unter <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">openrouter.ai/keys</a>.
        </div>
      )}

      {editing && <ProductForm initial={editing.id ? editing : null} onSubmit={saveProduct} onCancel={() => setEditing(null)} />}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {products.map(p => (
          <ProductCard key={p.id} p={p} onEdit={startEdit} onChanged={load} />
        ))}
      </div>

      {loaded && products.length === 0 && !editing && (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center", gap: 12,
          padding: "60px 20px", color: "var(--muted)", textAlign: "center",
        }}>
          <Icon name="bot" size={40} />
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>Noch keine Agenten</div>
          <div style={{ fontSize: 13, maxWidth: 420, lineHeight: 1.7 }}>
            Lege einen Agenten an — z.B. „PlayStation 5, 200–300 €, PLZ 65428 +50 km, alle 20 Minuten".
            Der Agent meldet dir nur geprüfte, gute Inserate mit Begründung.
          </div>
          <button className="btn btn-primary" onClick={() => setEditing({ ...EMPTY_FORM })}>
            <Icon name="plus" size={14} /> Ersten Agenten anlegen
          </button>
        </div>
      )}
    </div>
  );
}
