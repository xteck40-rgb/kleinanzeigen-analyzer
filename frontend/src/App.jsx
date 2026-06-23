import { useState, useEffect, useCallback, useRef } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { api, fmt, Icon, Badge, Stat, Spinner, ProgressBar, InputField, getUser, setUser as storeUser } from "./ui.jsx";
import AgentsView from "./AgentsView.jsx";

// ── Login (name only — no password) ───────────────────────────────────────────
const LoginView = ({ onLogin }) => {
  const [name, setName] = useState("");
  const [known, setKnown] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get("/api/users").then(d => setKnown(d.users || [])).catch(() => {});
  }, []);

  const submit = async (n) => {
    const value = (n || name).trim();
    if (!value) return;
    setBusy(true); setErr("");
    try {
      const res = await api.post("/api/login", { name: value });
      if (res?.id) onLogin(res);
      else setErr(res?.detail || "Anmeldung fehlgeschlagen");
    } catch {
      setErr("Backend nicht erreichbar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", padding: 20,
    }}>
      <div className="hero-dark" style={{ width: 420, maxWidth: "100%", padding: "34px 32px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <div style={{
            width: 42, height: 42, borderRadius: 12,
            background: "linear-gradient(135deg, #6366F1, #22D3EE)",
            display: "flex", alignItems: "center", justifyContent: "center", color: "#111633",
          }}>
            <Icon name="tag" size={20} />
          </div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Kleinanzeigen Analyzer</div>
        </div>
        <div style={{ fontSize: 13, color: "rgba(255,255,255,0.75)", marginBottom: 22, lineHeight: 1.6 }}>
          Wähle deinen Namen — jeder sieht nur seine eigenen Suchen, Verläufe und Agenten.
        </div>

        <label htmlFor="login-name" style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.75)", display: "block", marginBottom: 6 }}>
          Dein Name
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <input id="login-name" className="input" value={name} autoFocus
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !busy && submit()}
            placeholder="z.B. Justin" maxLength={40}
            style={{ background: "rgba(255,255,255,0.95)" }} />
          <button className="btn-hero" onClick={() => submit()} disabled={busy || !name.trim()}>
            {busy ? <Spinner size={14} /> : "Los"}
          </button>
        </div>
        {err && (
          <div role="alert" style={{ marginTop: 10, fontSize: 12, color: "#FDA4AF" }}>
            <Icon name="alert" size={12} /> {err}
          </div>
        )}

        {known.length > 0 && (
          <div style={{ marginTop: 22 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.55)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
              Bekannte Nutzer
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {known.map(u => (
                <button key={u.id} onClick={() => submit(u.name)} disabled={busy}
                  style={{
                    background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.2)",
                    color: "#fff", borderRadius: 999, padding: "6px 16px", fontSize: 13, fontWeight: 600,
                  }}>
                  {u.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ── MLR Panel ──────────────────────────────────────────────────────────────────
const MLRPanel = ({ mlr }) => {
  if (!mlr) return null;
  const maxImpact = Math.max(...mlr.coefficients.map(c => c.impact));

  return (
    <div style={{
      background: "var(--surface)", border: "1px solid rgba(29,78,216,0.25)",
      borderRadius: 12, padding: "20px 24px", marginBottom: 20
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "var(--blue)" }}><Icon name="brain" size={16} /></span>
            MLR Preisanalyse
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
            Basierend auf {mlr.n_samples} Inseraten mit vollständigen Daten
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>Modellgüte (R²)</div>
          <div style={{
            fontFamily: "var(--mono)", fontWeight: 700, fontSize: 22,
            color: mlr.r2 > 0.6 ? "var(--green)" : mlr.r2 > 0.35 ? "var(--accent)" : "var(--red)"
          }}>
            {mlr.r2_pct}%
          </div>
        </div>
      </div>

      <div style={{
        fontSize: 12, color: "var(--muted)", marginBottom: 16, padding: "10px 14px",
        background: "rgba(29,78,216,0.06)", borderRadius: 8, lineHeight: 1.7
      }}>
        {mlr.interpretation}
      </div>

      <div style={{
        fontSize: 11, color: "var(--muted)", textTransform: "uppercase",
        letterSpacing: "0.08em", marginBottom: 10
      }}>Einfluss auf den Preis</div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {mlr.coefficients.map((c, i) => (
          <div key={i}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
              <span style={{ fontSize: 12 }}>{c.feature}</span>
              <span style={{
                fontSize: 12, fontFamily: "var(--mono)",
                color: c.direction === "positiv" ? "var(--green)" : "var(--red)"
              }}>
                {c.direction === "positiv" ? "+" : "−"}{fmt.eur(Math.abs(c.per_unit_value))} {c.per_unit_label}
              </span>
            </div>
            <div style={{ background: "var(--border)", borderRadius: 4, height: 6, overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${(c.impact / maxImpact) * 100}%`,
                background: c.direction === "positiv" ? "var(--green)" : "var(--red)",
                borderRadius: 4, transition: "width 0.6s ease",
              }} />
            </div>
          </div>
        ))}
      </div>

      <div style={{
        marginTop: 16, fontSize: 11, color: "var(--muted)", padding: "8px 12px",
        background: "rgba(34,31,26,0.03)", borderRadius: 6
      }}>
        <Icon name="info" size={12} /> R² = {mlr.r2_pct}% bedeutet: das Modell erklärt {mlr.r2_pct}% der Preisunterschiede
        anhand der verfügbaren Merkmale. {mlr.r2 < 0.4 && "Mehr Daten (mehr Seiten scrapen) verbessern die Genauigkeit."}
      </div>
    </div>
  );
};

// ── Resale Calculator ──────────────────────────────────────────────────────────
const ResaleCalc = ({ analysis, excludedCount }) => {
  const [margin, setMargin] = useState(20);
  const [repairCost, setRepairCost] = useState(0);
  if (!analysis?.median_price) return null;

  const sellPrice = analysis.median_price;
  const maxBuy = sellPrice / (1 + margin / 100) - repairCost;
  const profit = sellPrice - maxBuy - repairCost;

  return (
    <div style={{
      background: "var(--surface)", border: "1px solid rgba(29,78,216,0.2)",
      borderRadius: 12, padding: "18px 22px", marginBottom: 20
    }}>
      <div style={{
        fontSize: 13, fontWeight: 700, marginBottom: 14, display: "flex",
        alignItems: "center", gap: 8, justifyContent: "space-between"
      }}>
        <span>Weiterverkaufs-Kalkulator</span>
        {excludedCount > 0 && (
          <span style={{ fontSize: 11, color: "var(--red)", fontWeight: 400 }}>
            {excludedCount} ausgeblendet
          </span>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Ziel-Gewinnmarge</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {[10, 15, 20, 30, 50].map(p => (
              <button key={p} onClick={() => setMargin(p)} style={{
                background: margin === p ? "rgba(29,78,216,0.2)" : "var(--surface2)",
                border: `1px solid ${margin === p ? "var(--blue)" : "var(--border2)"}`,
                color: margin === p ? "var(--blue)" : "var(--muted)",
                borderRadius: 5, padding: "4px 10px", fontSize: 12, fontWeight: 600,
              }}>{p}%</button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
            Reparaturkosten (€)
          </div>
          <input type="number" value={repairCost} min={0}
            onChange={e => setRepairCost(Number(e.target.value))}
            style={{
              background: "var(--surface2)", border: "1px solid var(--border2)",
              borderRadius: 6, padding: "6px 10px", color: "var(--text)", fontSize: 13,
              width: 120, outline: "none"
            }}
          />
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {[
          { label: "Realist. Verkaufspreis (Median)", value: fmt.eur(sellPrice), color: "var(--text)" },
          { label: `Max. Einkaufspreis (bei ${margin}% Marge)`, value: fmt.eur(Math.max(0, maxBuy)), color: "var(--green)" },
          { label: "Gewinn pro Fahrzeug", value: fmt.eur(Math.max(0, profit)), color: "var(--accent)" },
          { label: "Deals verfügbar", value: analysis.deals?.length || 0, color: "var(--blue)", unit: "" },
        ].map(({ label, value, color, unit }) => (
          <div key={label} style={{
            flex: "1 1 150px", background: "var(--surface2)",
            border: "1px solid var(--border)", borderRadius: 8, padding: "12px 16px"
          }}>
            <div style={{
              fontSize: 10, color: "var(--muted)", textTransform: "uppercase",
              letterSpacing: "0.08em", marginBottom: 4
            }}>{label}</div>
            <div style={{ fontFamily: "var(--mono)", fontWeight: 700, fontSize: 20, color }}>{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Price Chart ────────────────────────────────────────────────────────────────
const PriceChart = ({ distribution }) => {
  if (!distribution?.length) return null;
  const max = Math.max(...distribution.map(d => d.count));
  return (
    <div>
      <div style={{
        fontSize: 12, color: "var(--muted)", marginBottom: 12,
        textTransform: "uppercase", letterSpacing: "0.08em"
      }}>Preisverteilung</div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={distribution} margin={{ top: 4, right: 4, left: -20, bottom: 4 }}>
          <defs>
            <linearGradient id="barHot" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366F1" />
              <stop offset="100%" stopColor="#22D3EE" />
            </linearGradient>
          </defs>
          <XAxis dataKey="range" tick={{ fontSize: 10, fill: "#64748B" }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fontSize: 10, fill: "#64748B" }} tickLine={false} axisLine={false} />
          <Tooltip contentStyle={{
            background: "var(--surface2)", border: "1px solid var(--border2)",
            borderRadius: 6, fontSize: 12
          }} formatter={(v) => [v, "Inserate"]} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]}>
            {distribution.map((entry, i) => (
              <Cell key={i} fill={entry.count === max ? "url(#barHot)" : "#C7D2FE"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

// ── Results Table ──────────────────────────────────────────────────────────────
const ResultsTable = ({ listings, avgPrice, isCarMode, excludeTerms = [] }) => {
  const [sort, setSort] = useState({ key: "price_value", dir: "asc" });
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const sorted = [...listings]
    .filter(l => {
      if (excludeTerms.length > 0) {
        const text = `${l.title || ""} ${l.description || ""}`.toLowerCase();
        if (excludeTerms.some(t => text.includes(t))) return false;
      }
      return !filter || l.title?.toLowerCase().includes(filter.toLowerCase()) ||
        l.location?.toLowerCase().includes(filter.toLowerCase());
    })
    .sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });

  const pages = Math.ceil(sorted.length / PAGE_SIZE);
  const visible = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const Col = ({ label, k }) => (
    <th onClick={() => setSort(s => ({ key: k, dir: s.key === k && s.dir === "asc" ? "desc" : "asc" }))}
      style={{
        padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600,
        textTransform: "uppercase", letterSpacing: "0.08em", cursor: "pointer", whiteSpace: "nowrap",
        borderBottom: "1px solid var(--border2)", userSelect: "none",
        color: sort.key === k ? "var(--accent)" : "var(--muted)"
      }}>
      {label} {sort.key === k ? (sort.dir === "asc" ? "↑" : "↓") : ""}
    </th>
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 12, alignItems: "center" }}>
        <input placeholder="Filter nach Titel oder Ort..." value={filter}
          onChange={e => { setFilter(e.target.value); setPage(0); }}
          style={{
            flex: 1, background: "var(--surface2)", border: "1px solid var(--border2)",
            borderRadius: 6, padding: "7px 12px", color: "var(--text)", fontSize: 13, outline: "none"
          }} />
        <span style={{ color: "var(--muted)", fontSize: 12, whiteSpace: "nowrap" }}>{sorted.length} Ergebnisse</span>
      </div>

      <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid var(--border)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead style={{ background: "var(--surface2)" }}>
            <tr>
              <Col label="Titel" k="title" />
              <Col label="Preis" k="price_value" />
              {isCarMode && <>
                <Col label="KM" k="km" />
                <Col label="Jahr" k="year" />
                <Col label="PS" k="power_hp" />
                <Col label="Kraftstoff" k="fuel" />
                <Col label="Getriebe" k="gearbox" />
                <Col label="Farbe" k="color" />
              </>}
              <Col label="Ort" k="location" />
              <Col label="Datum" k="date_posted" />
              <th style={{ padding: "8px 12px", borderBottom: "1px solid var(--border2)" }} />
            </tr>
          </thead>
          <tbody>
            {visible.map((l, i) => {
              const isDeal = avgPrice && l.price_value > 0 && l.price_value < avgPrice * 0.8;
              return (
                <tr key={l.id || i}
                  style={{
                    background: isDeal ? "rgba(5,150,105,0.04)" : i % 2 === 0 ? "transparent" : "rgba(34,31,26,0.015)",
                    borderLeft: isDeal ? "2px solid var(--green)" : "2px solid transparent"
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = "rgba(15,23,42,0.04)"}
                  onMouseLeave={e => e.currentTarget.style.background = isDeal ? "rgba(5,150,105,0.04)" : i % 2 === 0 ? "transparent" : "rgba(34,31,26,0.015)"}
                >
                  <td style={{ padding: "9px 12px", maxWidth: 260 }}>
                    <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 13 }} title={l.title}>{l.title || "—"}</div>
                    {l.description && <div style={{ fontSize: 11, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.description}>{l.description}</div>}
                  </td>
                  <td style={{ padding: "9px 12px", whiteSpace: "nowrap" }}>
                    {l.price_value > 0
                      ? <span style={{ fontFamily: "var(--mono)", fontWeight: 700, color: isDeal ? "var(--green)" : "var(--accent)" }}>{fmt.eur(l.price_value)}</span>
                      : <span style={{ color: "var(--muted)", fontSize: 12 }}>{l.price_text || "—"}</span>
                    }
                    {isDeal && <span style={{ marginLeft: 6, fontSize: 10, color: "var(--green)", fontWeight: 700 }}>DEAL</span>}
                  </td>
                  {isCarMode && <>
                    <td style={{ padding: "9px 12px", fontFamily: "var(--mono)", fontSize: 12, color: "var(--muted)" }}>{fmt.km(l.km)}</td>
                    <td style={{ padding: "9px 12px", fontFamily: "var(--mono)", fontSize: 12, color: "var(--muted)" }}>{l.year || "—"}</td>
                    <td style={{ padding: "9px 12px", fontFamily: "var(--mono)", fontSize: 12, color: "var(--muted)" }}>{l.power_hp ? `${l.power_hp} PS` : "—"}</td>
                    <td style={{ padding: "9px 12px", fontSize: 12 }}>{l.fuel ? <Badge color="blue">{l.fuel}</Badge> : "—"}</td>
                    <td style={{ padding: "9px 12px", fontSize: 12 }}>{l.gearbox ? <Badge>{l.gearbox}</Badge> : "—"}</td>
                    <td style={{ padding: "9px 12px", fontSize: 12, color: "var(--muted)" }}>{l.color || "—"}</td>
                  </>}
                  <td style={{ padding: "9px 12px", fontSize: 12, color: "var(--muted)", whiteSpace: "nowrap" }}>{l.location || "—"}</td>
                  <td style={{ padding: "9px 12px", fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>{l.date_posted || "—"}</td>
                  <td style={{ padding: "9px 12px" }}>
                    {l.url && <a href={l.url} target="_blank" rel="noreferrer"
                      style={{ color: "var(--muted)", display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12 }}
                      onMouseEnter={e => e.currentTarget.style.color = "var(--accent)"}
                      onMouseLeave={e => e.currentTarget.style.color = "var(--muted)"}
                    ><Icon name="link" size={13} /> Öffnen</a>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "center" }}>
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            style={{
              background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)",
              borderRadius: 6, padding: "5px 14px", fontSize: 12, opacity: page === 0 ? 0.4 : 1
            }}>‹ Zurück</button>
          <span style={{ padding: "5px 10px", fontSize: 12, color: "var(--muted)" }}>{page + 1} / {pages}</span>
          <button onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={page === pages - 1}
            style={{
              background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)",
              borderRadius: 6, padding: "5px 14px", fontSize: 12, opacity: page === pages - 1 ? 0.4 : 1
            }}>Weiter ›</button>
        </div>
      )}
    </div>
  );
};

// ── History Sidebar ────────────────────────────────────────────────────────────
const HistorySidebar = ({ searches, onSelect, onDelete, activeId }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
    <div style={{
      fontSize: 11, color: "var(--muted)", textTransform: "uppercase",
      letterSpacing: "0.1em", marginBottom: 4
    }}>Verlauf</div>
    {searches.length === 0 && <div style={{ color: "var(--muted)", fontSize: 12 }}>Noch keine Suchen</div>}
    {searches.map(s => {
      const isActive = s.id === activeId;
      const isDone = s.status === "done";
      const isErr = s.status?.startsWith("error");
      return (
        <div key={s.id} onClick={() => isDone && onSelect(s.id)}
          style={{
            background: isActive ? "rgba(79,70,229,0.08)" : "var(--surface2)",
            border: `1px solid ${isActive ? "rgba(99,102,241,0.45)" : "var(--border)"}`,
            borderRadius: 8, padding: "10px 12px", cursor: isDone ? "pointer" : "default", transition: "all 0.15s"
          }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
            <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{s.query}</div>
            <button onClick={e => { e.stopPropagation(); onDelete(s.id); }}
              aria-label={`Suche „${s.query}" löschen`}
              style={{ background: "none", border: "none", color: "var(--muted)", padding: "0 2px" }}
              onMouseEnter={e => e.currentTarget.style.color = "var(--red)"}
              onMouseLeave={e => e.currentTarget.style.color = "var(--muted)"}>
              <Icon name="x" size={13} />
            </button>
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
            {s.category === "cars" && <Badge color="blue">Auto</Badge>}
            {isDone && <Badge color="green">{s.count} Ins.</Badge>}
            {isErr && <Badge color="red">Fehler</Badge>}
            {!isDone && !isErr && <Spinner size={12} />}
          </div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
            {new Date(s.created_at).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
          </div>
        </div>
      );
    })}
  </div>
);

// ── Main App ───────────────────────────────────────────────────────────────────

const ArbitrageView = () => {
  const [runs, setRuns] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.get("/api/arbitrage/runs");
      setRuns(d.runs || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const remove = async (id) => {
    await api.del(`/api/arbitrage/runs/${id}`);
    setRuns(rs => rs.filter(r => r.id !== id));
    if (expanded === id) setExpanded(null);
  };

  const safeParse = (s) => { try { return JSON.parse(s); } catch { return null; } };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Arbitrage-Pipeline Verlauf</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
            {runs.length} Einträge · Stage 1 (Trend-Hunter) + Stage 3 (Orchestrator)
          </div>
        </div>
        <button onClick={load} disabled={loading}
          style={{
            background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)",
            borderRadius: 7, padding: "7px 14px", fontSize: 12, cursor: "pointer"
          }}>
          {loading ? "Lädt..." : "Reload"}
        </button>
      </div>

      {runs.length === 0 && !loading && (
        <div style={{ color: "var(--muted)", fontSize: 13, padding: 40, textAlign: "center" }}>
          Noch keine Runs. Starte eine Pipeline im Tab <strong>Pipeline</strong>.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {runs.map(r => {
          const isOpen = expanded === r.id;
          const market = safeParse(r.market_json);
          const deals = safeParse(r.deals_json) || [];
          const products = safeParse(r.products_json) || [];
          return (
            <div key={r.id} style={{
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "12px 14px"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
                onClick={() => setExpanded(isOpen ? null : r.id)}>
                <Badge color={r.stage === "trend_hunter" ? "blue" : r.stage === "reviewer" ? "purple" : "amber"}>{r.stage}</Badge>
                {r.domain && <Badge>{r.domain}</Badge>}
                <div style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>
                  {r.product_query || (products.length ? `${products.length} Produkte` : "—")}
                </div>
                {market && <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--muted)" }}>
                  Median {fmt.eur(market.median_price)} · {market.count} Listings
                </span>}
                <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>
                  {new Date(r.ran_at).toLocaleString("de-DE")}
                </span>
                <button onClick={e => { e.stopPropagation(); remove(r.id); }}
                  aria-label="Eintrag löschen"
                  style={{ background: "transparent", border: "none", color: "var(--muted)", cursor: "pointer" }}>
                  <Icon name="trash" size={14} />
                </button>
              </div>

              {isOpen && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border2)" }}>
                  {products.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                        Produkte ({products.length})
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 8 }}>
                        {products.map((p, i) => (
                          <div key={i} style={{ background: "var(--surface2)", borderRadius: 7, padding: "10px 12px", fontSize: 12 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                              <div style={{ fontWeight: 600, flex: 1 }}>{p.query}</div>
                              {p.verdict && (
                                <Badge color={p.verdict === "approve" ? "green" : "red"}>
                                  {p.verdict} {p.score != null ? p.score : ""}
                                </Badge>
                              )}
                            </div>
                            <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 4 }}>
                              {p.category} · {fmt.eur(p.price_min || 0)}–{fmt.eur(p.price_max || 0)}
                              {p.verified_resell_eur != null && (
                                <> · eBay {fmt.eur(p.verified_resell_eur)} ({p.verified_sample || 0})</>
                              )}
                            </div>
                            {p.reasoning && <div style={{ color: "var(--muted)", fontSize: 11, lineHeight: 1.4 }}>{p.reasoning}</div>}
                            {p.concerns && <div style={{ color: "var(--warn, #c97)", fontSize: 11, lineHeight: 1.4, marginTop: 4 }}>⚠ {p.concerns}</div>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {deals.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                        Top Deals ({deals.length})
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {deals.map((d, i) => (
                          <a key={i} href={d.url} target="_blank" rel="noreferrer"
                            style={{
                              background: "var(--surface2)", borderRadius: 7, padding: "10px 12px",
                              textDecoration: "none", color: "var(--text)", display: "block",
                              border: "1px solid transparent"
                            }}
                            onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
                            onMouseLeave={e => e.currentTarget.style.borderColor = "transparent"}>
                            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 4 }}>
                              <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.title}</div>
                              <span style={{ fontFamily: "var(--mono)", fontWeight: 700, color: "var(--green)", whiteSpace: "nowrap" }}>{fmt.eur(d.price)}</span>
                            </div>
                            {d.reason && <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.4 }}>{d.reason}</div>}
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {!products.length && !deals.length && r.raw_text && (
                    <pre style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "pre-wrap", margin: 0 }}>
                      {r.raw_text.slice(0, 2000)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── Pipeline Live View ────────────────────────────────────────────────────────
const PIPELINE_CSS = `
@keyframes pipeBreath {
  0%, 100% { box-shadow: 0 0 0 0 rgba(99,102,241,0.25); }
  50%      { box-shadow: 0 0 0 5px rgba(99,102,241,0.08); }
}
@keyframes pipeBlink {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.4; }
}
@keyframes pipeFadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.stage-card.active {
  animation: pipeBreath 2.4s ease-in-out infinite;
  border-color: var(--accent2) !important;
}
.stage-card.active .scanline { display: none; }
.stage-card.done   { border-color: rgba(5,150,105,0.45) !important; }
.stage-card.error  { border-color: var(--red) !important; }
.dot-blink { animation: pipeBlink 1.2s ease-in-out infinite; }
.flip-in   { animation: pipeFadeIn 0.35s ease-out both; }
.log-line  { font-size: 11px; line-height: 1.6; padding: 1px 0; white-space: pre-wrap; word-break: break-word; }
.log-text   { color: #4B5563; }
.log-tool   { color: var(--blue); }
.log-result { color: var(--green); }
.log-error  { color: var(--red); font-weight: 600; }
`;

const STAGE_DEFS = [
  { id: "trend_hunter", label: "Stage 1 — Trend-Hunter", desc: "Findet Produkte via WebSearch + ebay_sold" },
  { id: "reviewer",     label: "Stage 2 — Reviewer",     desc: "Bewertet Kandidaten, vergibt Score 0-100" },
  { id: "orchestrator", label: "Stage 3 — Orchestrator", desc: "Scrapt Kleinanzeigen, findet Deals" },
];

const StageCard = ({ id, label, desc, state, log, extra }) => {
  const logRef = useRef(null);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [log]);

  const stateBadge = {
    idle:    { txt: "WARTET",   col: "var(--muted)" },
    active:  { txt: "AKTIV",    col: "var(--accent)" },
    done:    { txt: "FERTIG",   col: "var(--green)" },
    error:   { txt: "FEHLER",   col: "var(--red)" },
    skipped: { txt: "ÜBERSPRUNGEN", col: "var(--muted)" },
  }[state] || { txt: "—", col: "var(--muted)" };

  return (
    <div className={`stage-card ${state}`} style={{
      flex: 1, minWidth: 280, position: "relative", overflow: "hidden",
      background: "var(--surface)", border: "1px solid var(--border2)",
      borderRadius: 12, padding: "16px 18px", minHeight: 260,
      display: "flex", flexDirection: "column", gap: 10, transition: "border-color 0.3s"
    }}>
      {state === "active" && <div className="scanline" />}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.03em" }}>{label}</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{desc}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {state === "active" && <span className="dot-blink" style={{
            width: 8, height: 8, borderRadius: "50%", background: stateBadge.col,
          }} />}
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
            color: stateBadge.col, padding: "2px 9px", borderRadius: 999,
            background: state === "active" ? "rgba(99,102,241,0.12)" : "rgba(15,23,42,0.05)",
          }}>{stateBadge.txt}</span>
        </div>
      </div>

      {extra}

      <div ref={logRef} style={{
        flex: 1, background: "var(--surface2)", border: "1px solid var(--border)",
        borderRadius: 6, padding: "8px 10px", overflowY: "auto", maxHeight: 220, minHeight: 120,
      }}>
        {log.length === 0
          ? <div style={{ color: "var(--muted)", fontSize: 11, fontStyle: "italic" }}>—</div>
          : log.slice(-60).map((l, i) => (
              <div key={i} className={`log-line log-${l.kind}`}>{l.text}</div>
            ))}
      </div>
    </div>
  );
};

const PipelineView = () => {
  const [domains, setDomains] = useState(["general"]);
  const [skipReview, setSkipReview] = useState(false);
  const [stage3Pages, setStage3Pages] = useState(15);
  const [useRegion, setUseRegion] = useState(false);
  const [plz, setPlz] = useState("");
  const [radius, setRadius] = useState(0);
  const [minScore, setMinScore] = useState(50);

  const [pid, setPid] = useState(null);
  const [status, setStatus] = useState("idle"); // idle|running|done|error|cancelled
  const [stageStates, setStageStates] = useState({ trend_hunter: "idle", reviewer: "idle", orchestrator: "idle" });
  const [logs, setLogs] = useState({ trend_hunter: [], reviewer: [], orchestrator: [] });
  const [products, setProducts] = useState([]);
  const [productResults, setProductResults] = useState({});
  const [currentProduct, setCurrentProduct] = useState(null);

  const esRef = useRef(null);
  const lastToolRef = useRef({});  // stage -> last tool name

  useEffect(() => () => { if (esRef.current) esRef.current.close(); }, []);

  const pushLog = useCallback((stage, kind, text) => {
    setLogs(prev => ({ ...prev, [stage]: [...prev[stage].slice(-120), { kind, text }] }));
  }, []);

  const handleEvent = useCallback((evt) => {
    const stage = evt.stage;
    switch (evt.type) {
      case "pipeline_start":
        break;
      case "stage_start":
        setStageStates(s => ({ ...s, [stage]: "active" }));
        pushLog(stage, "tool", `▶ Stage gestartet${evt.domain ? ` (${evt.domain})` : ""}`);
        break;
      case "stage_done":
        setStageStates(s => ({ ...s, [stage]: "done" }));
        pushLog(stage, "result", `✓ Stage abgeschlossen`);
        if (stage === "trend_hunter" && Array.isArray(evt.products)) {
          setProducts(prev => [
            ...prev,
            ...evt.products.map(p => ({ ...p, _domain: evt.domain })),
          ]);
        }
        if (stage === "reviewer" && Array.isArray(evt.reviewed)) {
          setProducts(prev => prev.map(p => {
            const r = evt.reviewed.find(x => x.query === p.query);
            return r ? { ...p, ...r } : p;
          }));
        }
        break;
      case "stage_skipped":
        setStageStates(s => ({ ...s, [stage]: "skipped" }));
        pushLog(stage, "text", "(übersprungen)");
        break;
      case "product_start":
        setCurrentProduct(evt.product_query);
        pushLog("orchestrator", "tool", `▶ ${evt.product_query}`);
        break;
      case "product_done":
        setProductResults(prev => ({
          ...prev,
          [evt.product_query]: { market: evt.market, deals: evt.deals || [] },
        }));
        pushLog("orchestrator", "result",
          `✓ ${evt.product_query} — ${evt.deals?.length || 0} deals, median ${evt.market?.median_price ?? "?"}€`);
        break;
      case "agent_text":
        if (stage) pushLog(stage, "text", (evt.text || "").trim().slice(0, 240));
        break;
      case "tool_call":
        if (stage) {
          lastToolRef.current[stage] = evt.tool || "";
          pushLog(stage, "tool", `→ ${evt.tool}(${JSON.stringify(evt.input || {}).slice(0, 120)})`);
        }
        break;
      case "tool_result":
        if (stage) pushLog(stage, "result", `← ${(evt.preview || "").slice(0, 160)}`);
        break;
      case "error":
        if (stage) {
          pushLog(stage, "error", `✕ ${evt.message}`);
          setStageStates(s => ({ ...s, [stage]: "error" }));
        }
        break;
      case "pipeline_done":
        setStatus(prev => (prev === "cancelled" ? prev : "done"));
        if (esRef.current) esRef.current.close();
        break;
      default:
        break;
    }
  }, [pushLog]);

  const start = async () => {
    if (status === "running") return;
    if (esRef.current) esRef.current.close();
    setLogs({ trend_hunter: [], reviewer: [], orchestrator: [] });
    setProducts([]);
    setProductResults({});
    setCurrentProduct(null);
    setStageStates({
      trend_hunter: "idle",
      reviewer: skipReview ? "skipped" : "idle",
      orchestrator: "idle",
    });
    setStatus("running");

    const d = await api.post("/api/pipeline/start", {
      domains, skip_review: skipReview, stage3_max_pages: Number(stage3Pages),
      plz: useRegion ? plz.trim() : "",
      radius: useRegion ? Number(radius) : 0,
      min_review_score: Number(minScore),
    });
    setPid(d.pipeline_id);

    const es = new EventSource(`/api/pipeline/stream/${d.pipeline_id}`);
    esRef.current = es;
    const types = ["pipeline_start","stage_start","stage_done","stage_skipped",
      "product_start","product_done","agent_text","tool_call","tool_result","error","pipeline_done","close"];
    types.forEach(t => {
      es.addEventListener(t, (e) => {
        try {
          const data = JSON.parse(e.data || "{}");
          handleEvent({ ...data, type: t });
        } catch {}
        if (t === "close") es.close();
      });
    });
    es.onerror = () => {
      // backend reload or net hiccup — close to stop infinite reconnect attempts
      if (es.readyState === EventSource.CLOSED) setStatus(s => s === "running" ? "error" : s);
    };
  };

  const cancel = async () => {
    if (!pid) return;
    await api.del(`/api/pipeline/${pid}`);
    if (esRef.current) esRef.current.close();
    setStatus("cancelled");
  };

  const toggleDomain = (id) => {
    setDomains(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const stageExtra = {
    trend_hunter: products.length > 0 && (
      <div style={{ fontSize: 11, color: "var(--muted)" }}>
        {products.length} Produkt{products.length === 1 ? "" : "e"} gefunden
      </div>
    ),
    reviewer: products.filter(p => p.verdict).length > 0 && (
      <div style={{ fontSize: 11, color: "var(--muted)" }}>
        {products.filter(p => p.verdict === "approve").length} approve · {products.filter(p => p.verdict === "reject").length} reject
      </div>
    ),
    orchestrator: currentProduct && (
      <div style={{ fontSize: 11, color: "var(--accent)", fontFamily: "var(--mono)" }}>
        ► {currentProduct}
      </div>
    ),
  };

  const inputStyle = {
    background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)",
    borderRadius: 6, padding: "6px 10px", fontSize: 12, fontFamily: "var(--mono)", width: "100%",
  };

  return (
    <div>
      <style>{PIPELINE_CSS}</style>

      {/* Config Form */}
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10,
        padding: 16, marginBottom: 16
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>Pipeline starten</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              Trend-Hunter → Reviewer → Orchestrator. Backend muss auf :8000 laufen.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {status === "running" ? (
              <button onClick={cancel} style={{
                background: "var(--red)", color: "#fff", border: "none", borderRadius: 6,
                padding: "8px 18px", fontWeight: 700, fontSize: 13
              }}>STOP</button>
            ) : (
              <button onClick={start} disabled={domains.length === 0} style={{
                background: domains.length === 0 ? "var(--border2)" : "var(--accent)",
                color: "#fff", border: "none", borderRadius: 6,
                padding: "8px 18px", fontWeight: 700, fontSize: 13,
                cursor: domains.length === 0 ? "not-allowed" : "pointer"
              }}>▶ START</button>
            )}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          <div>
            <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Domains</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {["general", "cars"].map(d => (
                <label key={d} style={{
                  display: "flex", alignItems: "center", gap: 5, cursor: "pointer",
                  background: domains.includes(d) ? "rgba(79,70,229,0.1)" : "var(--surface2)",
                  border: `1px solid ${domains.includes(d) ? "var(--accent)" : "var(--border2)"}`,
                  borderRadius: 5, padding: "5px 10px", fontSize: 12,
                }}>
                  <input type="checkbox" checked={domains.includes(d)} onChange={() => toggleDomain(d)} style={{ accentColor: "var(--accent)" }} />
                  {d}
                </label>
              ))}
            </div>
          </div>

          <div style={{ gridColumn: "span 2" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer", marginBottom: 6 }}>
              <input type="checkbox" checked={useRegion} onChange={e => setUseRegion(e.target.checked)} style={{ accentColor: "var(--accent)" }} />
              <span style={{ fontWeight: 600 }}>Regional einschränken</span>
              <span style={{ color: "var(--muted)", fontSize: 11 }}>(empfohlen: OFF — Arbitrage profitiert von DE-weit)</span>
            </label>
            <div style={{ display: "flex", gap: 8, opacity: useRegion ? 1 : 0.4, pointerEvents: useRegion ? "auto" : "none" }}>
              <div style={{ flex: "0 0 110px" }}>
                <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>PLZ</div>
                <input value={plz} onChange={e => setPlz(e.target.value)} placeholder="z.B. 10115" style={inputStyle} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
                  Radius (km): {radius || "alle"}
                </div>
                <input type="range" min="0" max="200" step="10" value={radius} onChange={e => setRadius(e.target.value)} style={{ width: "100%", accentColor: "var(--accent)" }} />
              </div>
            </div>
          </div>

          <div>
            <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
              Stage-3 Seiten: {stage3Pages}
            </div>
            <input type="range" min="3" max="30" step="1" value={stage3Pages} onChange={e => setStage3Pages(e.target.value)} style={{ width: "100%", accentColor: "var(--accent)" }} />
          </div>

          <div>
            <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
              Min. Score: {minScore}
            </div>
            <input type="range" min="0" max="100" step="5" value={minScore} onChange={e => setMinScore(e.target.value)} style={{ width: "100%", accentColor: "var(--accent)" }} />
          </div>

          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
              <input type="checkbox" checked={skipReview} onChange={e => setSkipReview(e.target.checked)} style={{ accentColor: "var(--accent)" }} />
              Reviewer überspringen
            </label>
          </div>
        </div>
      </div>

      {/* Stage Cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        {STAGE_DEFS.map(def => (
          <StageCard
            key={def.id}
            id={def.id}
            label={def.label}
            desc={def.desc}
            state={stageStates[def.id]}
            log={logs[def.id]}
            extra={stageExtra[def.id]}
          />
        ))}
      </div>

      {/* Products grid */}
      {products.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
            Produkte ({products.length})
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
            {products.map((p, i) => {
              const isCurrent = p.query === currentProduct;
              const hasResult = productResults[p.query];
              return (
                <div key={i} className="flip-in" style={{
                  background: "var(--surface)",
                  border: `1px solid ${isCurrent ? "var(--accent)" : hasResult ? "var(--green)" : "var(--border)"}`,
                  borderRadius: 8, padding: "10px 12px", fontSize: 12, position: "relative",
                  boxShadow: isCurrent ? "0 0 0 3px rgba(99,102,241,0.2)" : "none",
                  transition: "border-color 0.3s",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    <div style={{ fontWeight: 600, flex: 1 }}>{p.query}</div>
                    {p.verdict && (
                      <Badge color={p.verdict === "approve" ? "green" : "red"}>
                        {p.verdict} {p.score != null ? p.score : ""}
                      </Badge>
                    )}
                  </div>
                  <div style={{ color: "var(--muted)", fontSize: 11 }}>
                    {p.category || "all"} · {fmt.eur(p.price_min || 0)}–{fmt.eur(p.price_max || 0)}
                    {p.verified_resell_eur != null && <> · eBay {fmt.eur(p.verified_resell_eur)}</>}
                  </div>
                  {hasResult && (
                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid var(--border2)", fontSize: 11, fontFamily: "var(--mono)" }}>
                      <span style={{ color: "var(--green)" }}>{hasResult.deals.length} deals</span>
                      {hasResult.market && (
                        <span style={{ color: "var(--muted)" }}>
                          {" · median "}{fmt.eur(hasResult.market.median_price)}
                          {" · n="}{hasResult.market.count}
                          {hasResult.market.raw_count != null && hasResult.market.raw_count !== hasResult.market.count
                            && <span style={{ opacity: 0.7 }}> /{hasResult.market.raw_count}</span>}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Live deals feed */}
      {Object.keys(productResults).length > 0 && (
        <div>
          <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
            Deals
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {Object.entries(productResults).map(([query, res]) => (
              <div key={query} className="flip-in" style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: 8, padding: "10px 12px"
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>{query}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>
                    {res.market && <>median {fmt.eur(res.market.median_price)} · n={res.market.count}</>}
                  </div>
                </div>
                {res.deals.length === 0 ? (
                  <div style={{ color: "var(--muted)", fontSize: 12, fontStyle: "italic" }}>Keine Deals.</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {res.deals.slice(0, 12).map((d, i) => (
                      <a key={i} href={d.url} target="_blank" rel="noreferrer" style={{
                        display: "flex", justifyContent: "space-between", gap: 12,
                        padding: "6px 8px", background: "var(--surface2)", borderRadius: 5,
                        fontSize: 12, color: "var(--text)",
                      }}>
                        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.title}</span>
                        <span style={{ fontFamily: "var(--mono)", color: "var(--green)", fontWeight: 700 }}>{fmt.eur(d.price)}</span>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {status === "idle" && products.length === 0 && (
        <div style={{ color: "var(--muted)", fontSize: 13, padding: 40, textAlign: "center" }}>
          Konfiguriere Parameter oben und klicke <strong>START</strong>. Events streamen live in die Stage-Karten.
        </div>
      )}
    </div>
  );
};

export default function App() {
  const [view, setView] = useState("search");
  const [menuOpen, setMenuOpen] = useState(false);
  const [user, setUserState] = useState(getUser());

  const logout = () => {
    storeUser(null);
    setUserState(null);
    setSearches([]); setActiveId(null); setAnalysis(null); setListings([]);
  };
  const [query, setQuery] = useState("");
  const [maxPages, setMaxPages] = useState(3);
  const [category, setCategory] = useState("all");
  const [dealThreshold, setDealThreshold] = useState(0.80);
  const [plz, setPlz] = useState("");
  const [radius, setRadius] = useState(0);
  const [detailScrape, setDetailScrape] = useState(false);
  // Car filters
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [kmMax, setKmMax] = useState("");
  const [priceMin, setPriceMin] = useState("");
  const [priceMax, setPriceMax] = useState("");
  const [psMin, setPsMin] = useState("");
  const [psMax, setPsMax] = useState("");
  // Exclude words
  const [excludeInput, setExcludeInput] = useState("");
  const [excludeTerms, setExcludeTerms] = useState([]);
  const excludeTermsRef = useRef([]);

  const [searches, setSearches] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(false);

  const pollRef = useRef(null);

  useEffect(() => {
    if (user) api.get("/api/searches").then(d => setSearches(d.searches || []));
  }, [user]);

  const refreshSearches = useCallback(() =>
    api.get("/api/searches").then(d => setSearches(d.searches || [])), []);

  const loadResults = useCallback(async (id, terms) => {
    const activeTerms = terms !== undefined ? terms : excludeTermsRef.current;
    try {
      const excludeParam = activeTerms.join(",");
      const [res, ana] = await Promise.all([
        api.get(`/api/results/${id}`),
        api.get(`/api/analyze/${id}?deal_threshold=${dealThreshold}&exclude=${encodeURIComponent(excludeParam)}`),
      ]);
      if (ana && !ana.detail) {
        setListings(ana.listings || res.listings || []);
        setAnalysis(ana);
      } else {
        setListings(res.listings || []);
      }
      setActiveId(id);
    } catch (err) {
      console.error("loadResults Fehler:", err);
    }
  }, [dealThreshold]);

  const startPolling = useCallback((id) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const data = await api.get(`/api/status/${id}`);
        setJobStatus(data);
        if (data.status === "done") {
          clearInterval(pollRef.current);
          setLoading(false);
          await loadResults(id, excludeTermsRef.current);
          await refreshSearches();
        } else if (data.status?.startsWith("error")) {
          clearInterval(pollRef.current);
          setLoading(false);
          await refreshSearches();
        }
      } catch {
        clearInterval(pollRef.current);
        setLoading(false);
      }
    }, 1500);
  }, [loadResults, refreshSearches]);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const updateExcludeTerms = (newTerms) => {
    excludeTermsRef.current = newTerms;
    setExcludeTerms(newTerms);
    if (activeId) loadResults(activeId, newTerms);
  };

  const addExcludeTerm = (e) => {
    if (e.key === "Enter" && excludeInput.trim()) {
      e.preventDefault();
      const term = excludeInput.trim().toLowerCase();
      if (!excludeTermsRef.current.includes(term)) {
        updateExcludeTerms([...excludeTermsRef.current, term]);
      }
      setExcludeInput("");
    }
  };

  const removeExcludeTerm = (term) => {
    updateExcludeTerms(excludeTermsRef.current.filter(t => t !== term));
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setJobStatus({ status: "pending", progress: 0 });
    setAnalysis(null); setListings([]); setActiveId(null);

    const { search_id } = await api.post("/api/search", {
      query: query.trim(), max_pages: maxPages, category,
      plz: plz.trim(), radius: Number(radius),
      year_from: Number(yearFrom) || 0, year_to: Number(yearTo) || 0,
      km_max: Number(kmMax) || 0, price_min: Number(priceMin) || 0, price_max: Number(priceMax) || 0,
      ps_min: Number(psMin) || 0,
      ps_max: Number(psMax) || 0,
      detail_scrape: detailScrape,
    });
    await refreshSearches();
    startPolling(search_id);
  };

  const handleSelectHistory = async (id) => {
    setLoading(true);
    setJobStatus(null);
    await loadResults(id, excludeTermsRef.current);
    setLoading(false);
  };

  const handleDelete = async (id) => {
    await api.del(`/api/searches/${id}`);
    if (activeId === id) { setActiveId(null); setAnalysis(null); setListings([]); }
    await refreshSearches();
  };

  const isCarMode = category === "cars" || searches.find(s => s.id === activeId)?.category === "cars";

  if (!user) {
    return <LoginView onLogin={(u) => { storeUser(u); setUserState(u); }} />;
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", flexDirection: "column" }}>
      {/* Header — dark navy with tabs */}
      <header className="app-header">
        <button className="menu-btn" onClick={() => setMenuOpen(true)} aria-label="Verlauf öffnen">
          <Icon name="menu" size={18} />
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 10,
            background: "linear-gradient(135deg, #6366F1, #22D3EE)",
            display: "flex", alignItems: "center", justifyContent: "center", color: "#111633",
          }}>
            <Icon name="tag" size={16} />
          </div>
          <span style={{ fontWeight: 800, fontSize: 16, letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>
            Kleinanzeigen Analyzer
          </span>
        </div>
        <nav className="header-tabs" aria-label="Hauptnavigation">
          {[
            { id: "search", label: "Suche" },
            { id: "agents", label: "Agenten" },
            { id: "pipeline", label: "Pipeline" },
            { id: "arbitrage", label: "Arbitrage-Verlauf" },
          ].map(t => (
            <button key={t.id} onClick={() => setView(t.id)}
              className={`htab ${view === t.id ? "on" : ""}`}>
              {t.label}
            </button>
          ))}
        </nav>
        <div style={{ flex: 1 }} />
        <div className="header-note" style={{ fontSize: 12, color: "#9AA3D0" }}>Nur für persönlichen Gebrauch</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            background: "rgba(255,255,255,0.08)", borderRadius: 999, padding: "5px 12px 5px 6px",
          }}>
            <div style={{
              width: 24, height: 24, borderRadius: "50%", fontSize: 12, fontWeight: 800,
              background: "linear-gradient(135deg, #6366F1, #22D3EE)", color: "#111633",
              display: "flex", alignItems: "center", justifyContent: "center",
            }} aria-hidden="true">
              {user.name.charAt(0).toUpperCase()}
            </div>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{user.name}</span>
          </div>
          <button onClick={logout} aria-label="Nutzer wechseln" title="Nutzer wechseln"
            style={{
              background: "transparent", border: "none", color: "#9AA3D0",
              padding: 6, borderRadius: 8, display: "inline-flex",
            }}>
            <Icon name="refresh" size={15} />
          </button>
        </div>
      </header>

      {/* Mobile history drawer */}
      {menuOpen && (
        <>
          <div className="drawer-backdrop" onClick={() => setMenuOpen(false)} />
          <div className="drawer" role="dialog" aria-label="Verlauf">
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
              <button className="btn btn-ghost" onClick={() => setMenuOpen(false)} aria-label="Verlauf schließen">
                <Icon name="x" size={16} />
              </button>
            </div>
            <HistorySidebar searches={searches}
              onSelect={(id) => { setMenuOpen(false); setView("search"); handleSelectHistory(id); }}
              onDelete={handleDelete} activeId={activeId} />
          </div>
        </>
      )}

      <div style={{ display: "flex", flex: 1 }}>
        {/* Sidebar */}
        <aside className="app-sidebar" style={{
          width: 230, background: "var(--surface)", borderRight: "1px solid var(--border)",
          padding: "20px 14px", overflowY: "auto", flexShrink: 0
        }}>
          <HistorySidebar searches={searches} onSelect={handleSelectHistory}
            onDelete={handleDelete} activeId={activeId} />
        </aside>

        {/* Main */}
        <main className="app-main" style={{ flex: 1, padding: "24px 28px", overflowY: "auto", minWidth: 0 }}>

          {view === "agents" && <AgentsView />}
          {view === "pipeline" && <PipelineView />}
          {view === "arbitrage" && <ArbitrageView />}

          {view === "search" && <>

          {/* Search Panel */}
          <div style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 12, padding: "18px 22px", marginBottom: 22
          }}>
            <div style={{
              fontSize: 11, color: "var(--muted)", textTransform: "uppercase",
              letterSpacing: "0.1em", marginBottom: 14
            }}>Neue Suche</div>

            {/* Row 1: main fields */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
              <div style={{ flex: "2 1 220px" }}>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 5 }}>Suchbegriff</label>
                <input value={query} onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && !loading && handleSearch()}
                  placeholder='z.B. "Golf 6 GTI" oder "Logitech G29"'
                  style={{
                    width: "100%", background: "var(--surface2)", border: "1px solid var(--border2)",
                    borderRadius: 7, padding: "9px 13px", color: "var(--text)", fontSize: 14, outline: "none"
                  }} />
              </div>

              <div style={{ flex: "0 0 130px" }}>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 5 }}>Kategorie</label>
                <select value={category} onChange={e => setCategory(e.target.value)}
                  style={{
                    width: "100%", background: "var(--surface2)", border: "1px solid var(--border2)",
                    borderRadius: 7, padding: "9px 12px", color: "var(--text)", fontSize: 13, appearance: "none"
                  }}>
                  <option value="all">Alle Kategorien</option>
                  <option value="cars">🚗 Autos (nur PKW)</option>
                </select>
              </div>

              <InputField label="PLZ (optional)" value={plz} onChange={setPlz} placeholder="z.B. 65428" width={100} />

              <div style={{ flex: "0 0 110px" }}>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 5 }}>Umkreis</label>
                <select value={radius} onChange={e => setRadius(e.target.value)} disabled={!plz}
                  style={{
                    width: "100%", background: "var(--surface2)", border: "1px solid var(--border2)",
                    borderRadius: 7, padding: "9px 12px", color: "var(--text)", fontSize: 13,
                    appearance: "none", opacity: plz ? 1 : 0.5
                  }}>
                  <option value={0}>Ganz DE</option>
                  <option value={10}>10 km</option>
                  <option value={20}>20 km</option>
                  <option value={50}>50 km</option>
                  <option value={100}>100 km</option>
                  <option value={200}>200 km</option>
                </select>
              </div>

              <div style={{ flex: "0 0 100px" }}>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 5 }}>Seiten</label>
                <select value={maxPages} onChange={e => setMaxPages(Number(e.target.value))}
                  style={{
                    width: "100%", background: "var(--surface2)", border: "1px solid var(--border2)",
                    borderRadius: 7, padding: "9px 12px", color: "var(--text)", fontSize: 13, appearance: "none"
                  }}>
                  {[1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 75, 100].map(n => <option key={n} value={n}>{n} Seiten</option>)}
                </select>
              </div>

              <div style={{ flex: "0 0 auto" }}>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 5 }}>
                  Deal &lt; <span style={{ color: "var(--accent)", fontFamily: "var(--mono)" }}>{fmt.pct(dealThreshold)}</span> Ø
                </label>
                <input type="range" min={0.5} max={0.95} step={0.05} value={dealThreshold}
                  onChange={e => setDealThreshold(Number(e.target.value))}
                  style={{ width: 100, accentColor: "var(--accent)", marginTop: 10 }} />
              </div>

              <div style={{ flex: "0 0 auto" }}>
                <div style={{ fontSize: 11, color: "transparent", marginBottom: 5 }}>_</div>
                <button onClick={handleSearch} disabled={loading || !query.trim()}
                  style={{
                    background: loading ? "rgba(79,70,229,0.12)" : "var(--accent)",
                    color: loading ? "var(--accent)" : "#fff",
                    border: `1px solid ${loading ? "rgba(99,102,241,0.35)" : "var(--accent)"}`,
                    borderRadius: 7, padding: "9px 20px", fontWeight: 700, fontSize: 13,
                    display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap",
                    opacity: !query.trim() ? 0.5 : 1
                  }}>
                  {loading ? <Spinner size={15} /> : <Icon name="search" size={15} />}
                  {loading ? "Läuft..." : "Suchen"}
                </button>
              </div>
            </div>

            {/* Row 2: filters + exclude words */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
              <InputField label="Min. Preis €" value={priceMin} onChange={setPriceMin} placeholder="z.B. 3000" type="number" width={110} />
              <InputField label="Max. Preis €" value={priceMax} onChange={setPriceMax} placeholder="z.B. 12000" type="number" width={110} />
              {category === "cars" && (
                <>
                  <InputField label="Baujahr von" value={yearFrom} onChange={setYearFrom} placeholder="z.B. 2010" type="number" width={110} />
                  <InputField label="Baujahr bis" value={yearTo} onChange={setYearTo} placeholder="z.B. 2018" type="number" width={110} />
                  <InputField label="Max. KM" value={kmMax} onChange={setKmMax} placeholder="z.B. 150000" type="number" width={120} />
                  <InputField label="Min. PS" value={psMin} onChange={setPsMin} placeholder="z.B. 100" type="number" width={100} />
                  <InputField label="Max. PS" value={psMax} onChange={setPsMax} placeholder="z.B. 200" type="number" width={100} />
                  <div style={{ flex: "0 0 auto", display: "flex", alignItems: "flex-end", paddingBottom: 2 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={detailScrape}
                        onChange={e => setDetailScrape(e.target.checked)}
                        style={{ width: 15, height: 15, accentColor: "var(--accent)", cursor: "pointer" }}
                      />
                      <span style={{ color: detailScrape ? "var(--accent)" : "var(--muted)" }}>
                        Detailsuche <span style={{ fontSize: 11 }}>(langsamer, mehr Daten)</span>
                      </span>
                    </label>
                  </div>
                </>
              )}

              {/* Exclude words */}
              <div style={{ flex: "1 1 240px" }}>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 5 }}>
                  Ausschlusswörter <span style={{ fontSize: 10 }}>(Enter zum Hinzufügen)</span>
                </label>
                <div style={{
                  background: "var(--surface2)", border: "1px solid var(--border2)",
                  borderRadius: 7, padding: "5px 8px", display: "flex", flexWrap: "wrap",
                  gap: 5, minHeight: 38, alignItems: "center"
                }}>
                  {excludeTerms.map((term, i) => (
                    <span key={i} style={{
                      background: "rgba(194,54,47,0.15)", color: "var(--red)",
                      borderRadius: 4, padding: "2px 8px", fontSize: 12,
                      display: "inline-flex", alignItems: "center", gap: 5
                    }}>
                      {term}
                      <span onClick={() => removeExcludeTerm(term)}
                        style={{ cursor: "pointer", fontWeight: 700 }}>×</span>
                    </span>
                  ))}
                  <input value={excludeInput} onChange={e => setExcludeInput(e.target.value)}
                    onKeyDown={addExcludeTerm}
                    placeholder={excludeTerms.length === 0 ? 'z.B. "defekt", "suche"...' : "weiteres Wort..."}
                    style={{
                      background: "none", border: "none", outline: "none",
                      color: "var(--text)", fontSize: 13, minWidth: 130, flex: 1
                    }} />
                </div>
              </div>
            </div>

            {/* Progress */}
            {jobStatus?.status === "running" && (
              <div style={{ marginTop: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                  <span style={{ fontSize: 11, color: "var(--muted)", fontFamily: "var(--mono)" }}>Scraping kleinanzeigen.de...</span>
                  <span style={{ fontSize: 11, color: "var(--accent)", fontFamily: "var(--mono)" }}>{jobStatus.progress}%</span>
                </div>
                <ProgressBar value={jobStatus.progress} />
              </div>
            )}
            {jobStatus?.status?.startsWith("error") && (
              <div style={{
                marginTop: 12, padding: "10px 14px", background: "rgba(194,54,47,0.08)",
                border: "1px solid rgba(194,54,47,0.2)", borderRadius: 7, fontSize: 12, color: "var(--red)"
              }}>
                <Icon name="info" size={13} /> Fehler beim Scraping. Prüfe das Backend-Terminal.
              </div>
            )}
          </div>

          {/* Results */}
          {analysis && (
            <>
              <div className="hero-dark" style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                gap: 16, padding: "20px 26px", marginBottom: 16, flexWrap: "wrap",
              }}>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 800, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    {searches.find(s => s.id === activeId)?.query || "Ergebnisse"} — Marktübersicht
                    {isCarMode && <Badge color="blue">Autos</Badge>}
                  </div>
                  <div style={{ fontSize: 13, color: "rgba(255,255,255,0.78)", marginTop: 4 }}>
                    {analysis.count} Inserate · {analysis.deals?.length || 0} Deals unter {fmt.eur(analysis.deal_threshold_value)}
                    {analysis.excluded_count > 0 && <span style={{ color: "#FDA4AF", marginLeft: 8 }}>{analysis.excluded_count} ausgeblendet</span>}
                  </div>
                </div>
                <button className="btn-hero" onClick={() => window.open(`/api/export/${activeId}`, "_blank")}>
                  <Icon name="down" size={13} /> CSV Export
                </button>
              </div>

              {/* Stats */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 20 }}>
                <Stat label="Inserate" value={analysis.count} sub={`${analysis.with_price} mit Preis`} tone="indigo" icon="chart" />
                <Stat label="Ø Preis" value={fmt.eur(analysis.avg_price)} tone="blue" icon="tag" />
                <Stat label="Median" value={fmt.eur(analysis.median_price)} tone="cyan" icon="info" />
                <Stat label="Günstigster" value={fmt.eur(analysis.min_price)} color="var(--green)" tone="green" icon="down" />
                <Stat label="Teuerster" value={fmt.eur(analysis.max_price)} color="var(--red)" tone="rose" icon="chevronUp" />
                <Stat label="Deals" value={analysis.deals?.length || 0} sub={`unter ${fmt.pct(analysis.deal_threshold_pct)} Median`} color="var(--green)" tone="amber" icon="check" />
              </div>

              {/* Resale Calc */}
              <ResaleCalc analysis={analysis} excludedCount={analysis.excluded_count} />

              {/* MLR */}
              {analysis.mlr && <MLRPanel mlr={analysis.mlr} />}

              {/* Chart */}
              {analysis.price_distribution?.length > 0 && (
                <div style={{
                  background: "var(--surface)", border: "1px solid var(--border)",
                  borderRadius: 12, padding: "18px 20px", marginBottom: 20
                }}>
                  <PriceChart distribution={analysis.price_distribution} />
                </div>
              )}

              {/* Deals */}
              {analysis.deals?.length > 0 && (
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: "var(--green)" }}>◆</span> Top Deals
                    <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 400 }}>
                      (unter {fmt.eur(analysis.deal_threshold_value)})
                    </span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(270px, 1fr))", gap: 10 }}>
                    {analysis.deals.slice(0, 6).map((d, i) => (
                      <a key={i} href={d.url} target="_blank" rel="noreferrer"
                        style={{
                          background: "var(--surface)", border: "1px solid rgba(5,150,105,0.2)",
                          borderRadius: 10, padding: "12px 14px", display: "block",
                          textDecoration: "none", color: "var(--text)", transition: "all 0.15s"
                        }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--green)"; e.currentTarget.style.background = "rgba(5,150,105,0.05)"; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(5,150,105,0.2)"; e.currentTarget.style.background = "var(--surface)"; }}>
                        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.title}</div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontFamily: "var(--mono)", fontWeight: 700, fontSize: 18, color: "var(--green)" }}>{fmt.eur(d.price_value)}</span>
                          {analysis.median_price > 0 && (
                            <span style={{ fontSize: 11, color: "var(--green)" }}>
                              −{Math.round((1 - d.price_value / analysis.median_price) * 100)}% vs Median
                            </span>
                          )}
                        </div>
                        {d.location && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{d.location}</div>}
                        {isCarMode && (
                          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3, display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {d.km && <span>{fmt.km(d.km)}</span>}
                            {d.year && <span>{d.year}</span>}
                            {d.power_hp && <span>{d.power_hp} PS</span>}
                            {d.fuel && <Badge color="blue">{d.fuel}</Badge>}
                            {d.gearbox && <Badge>{d.gearbox}</Badge>}
                          </div>
                        )}
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* Table */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "18px 20px" }}>
                <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 14 }}>
                  Alle Inserate
                </div>
                <ResultsTable listings={listings} avgPrice={analysis.median_price}
                  isCarMode={!!isCarMode} excludeTerms={excludeTerms} />
              </div>
            </>
          )}

          {!analysis && !loading && (
            <div style={{
              display: "flex", flexDirection: "column", alignItems: "center",
              justifyContent: "center", minHeight: 300, color: "var(--muted)", gap: 12, textAlign: "center"
            }}>
              <Icon name="chart" size={40} />
              <div style={{ fontSize: 16, fontWeight: 500, color: "var(--text)" }}>Bereit für deine erste Suche</div>
              <div style={{ fontSize: 13, maxWidth: 400, lineHeight: 1.7 }}>
                Gib ein Produkt oder Fahrzeug ein. Bei Autos kannst du Baujahr, KM-Stand und Preisbereich direkt filtern.
                Die MLR-Analyse zeigt dir welche Faktoren den Preis am stärksten beeinflussen.
              </div>
            </div>
          )}
          </>}
        </main>
      </div>
    </div>
  );
}
