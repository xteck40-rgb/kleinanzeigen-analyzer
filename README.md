# 🔍 Kleinanzeigen Analyzer

Scrape, analyse und visualisiere Inserate von kleinanzeigen.de — finde Deals, berechne Durchschnittspreise und exportiere Daten als CSV.

---

## ⚡ Schnellstart (Windows) — für Freunde zum Kopieren

```powershell
# 1. Projekt herunterladen
git clone https://github.com/xteck40-rgb/kleinanzeigen-analyzer.git
cd kleinanzeigen-analyzer

# 2. Einmalige Einrichtung (Python-Pakete, Browser, Frontend-Build)
.\setup.ps1

# 3. Starten
.\start.ps1
```

Dann **http://localhost:8000** im Browser öffnen.

> Kein Git? Stattdessen oben rechts auf GitHub **Code → Download ZIP**, entpacken, dann `setup.ps1` / `start.ps1` ausführen.
>
> Den eigenen **OpenRouter API-Key** (https://openrouter.ai/keys) trägt jeder selbst in der App unter *Einstellungen* ein — er wird **nicht** mitgeliefert.

---

## ⚙️ Voraussetzungen

- **Python 3.11** → https://www.python.org/downloads/release/python-3119/ (beim Installieren *„Add python.exe to PATH"* anhaken)
- **Node.js 18+** → https://nodejs.org/
- **Git** (optional) → https://git-scm.com/download/win

---

## 🚀 Setup (einmalig)

### 1. Backend einrichten

Öffne ein Terminal im Ordner `backend/`:

```bash
cd backend

# Virtuelle Python-Umgebung erstellen (empfohlen)
python -m venv venv

# Aktivieren:
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Playwright Browser herunterladen (WICHTIG!)
playwright install chromium
```

### 2. Frontend einrichten

Öffne ein zweites Terminal im Ordner `frontend/`:

```bash
cd frontend
npm install
```

---

## ▶️ Starten

Du brauchst **zwei Terminals** gleichzeitig:

**Terminal 1 – Backend:**
```bash
cd backend
# venv aktivieren (falls nicht schon aktiv)
venv\Scripts\activate   # Windows
source venv/bin/activate # Mac/Linux

uvicorn main:app --reload
```
→ API läuft auf http://localhost:8000

**Terminal 2 – Frontend:**
```bash
cd frontend
npm run dev
```
→ App läuft auf http://localhost:5173

Öffne dann **http://localhost:5173** im Browser.

---

## 🖥️ Benutzung

### Produktsuche
1. Suchbegriff eingeben, z.B. `Logitech G29`
2. Kategorie: **Alle** für Produkte
3. Seiten auswählen (1 Seite ≈ 25 Inserate, mehr Seiten = genauere Analyse)
4. Auf **Suchen** klicken und warten

### Autosuche
1. Suchbegriff eingeben, z.B. `VW Golf GTI`
2. Kategorie: **Autos & KFZ** auswählen → extrahiert zusätzlich KM-Stand, Baujahr, Kraftstoff
3. Suchen starten

### Ergebnisse
- **Stats-Karten**: Anzahl Inserate, Ø Preis, Min/Max, Median
- **Preisverteilung**: Balkendiagramm der Preise
- **Top Deals**: Inserate deutlich unter dem Durchschnitt
- **Tabelle**: Alle Inserate, sortierbar nach Preis, Datum, KM-Stand
- **CSV Export**: Alle Daten herunterladen für Excel-Analyse

### Deal-Schwellwert
- Standard: 80% des Durchschnittspreises
- Anpassbar über den Schieberegler (50% – 95%)

### Produkt-Agenten (Tab „Agenten")
Autonome Such-Agenten, die in festem Intervall (z.B. alle 20 Min.) nach einem Produkt suchen
und jedes neue Inserat per LLM prüfen.

1. **Einstellungen**: OpenRouter API-Key (https://openrouter.ai/keys) + Modell eintragen,
   z.B. `deepseek/deepseek-chat-v3.1` (günstig & stark).
2. **Agent anlegen**: Produktname, Suchbegriff, Preisrahmen, PLZ/Umkreis, Intervall —
   optional ein eigener Prompt (z.B. „Unfallwagen aussortieren").
3. Der Agent pro Runde:
   - scrapt mit deinen Kriterien (sie gelten **immer**),
   - berechnet Marktmetriken (Median, Preisverteilung, Deals),
   - reviewt nur **neue** Inserate per LLM: richtiges Produkt? Fake-Risiko? Deal-Score?
   - ein zweiter skeptischer Review-Pass bestätigt die Top-Kandidaten,
   - pflegt eigene Kriterien-Notizen und verfeinert ggf. den Suchbegriff.
4. Ergebnisse: pro Runde unter „Suchrunden" (mit Begründung je Inserat),
   produktübergreifend unter „Top-Liste".

---

## 🛠️ Fehlerbehebung

**"playwright install" fehlt:**
```bash
playwright install chromium
```

**CORS-Fehler im Browser:**
Stelle sicher, dass das Backend auf Port 8000 läuft.

**Keine Ergebnisse beim Scraping:**
- Kleinanzeigen.de kann ihre HTML-Struktur ändern → selectors in `scraper.py` ggf. anpassen
- VPN oder zu viele Anfragen können blockiert werden → `max_pages` reduzieren

**Datenbank zurücksetzen:**
```bash
cd backend
del kleinanzeigen.db   # Windows
rm kleinanzeigen.db    # Mac/Linux
```

---

## 📁 Projektstruktur

```
kleinanzeigen-analyzer/
├── backend/
│   ├── main.py          ← FastAPI App & Endpoints
│   ├── scraper.py       ← Playwright Web-Scraper
│   ├── database.py      ← SQLite Datenbanklogik
│   └── requirements.txt ← Python-Abhängigkeiten
└── frontend/
    ├── vite.config.js   ← Vite + API-Proxy Konfig
    └── src/
        └── App.jsx      ← Komplette React-App
```

---

## ⚠️ Rechtlicher Hinweis

Dieses Tool ist ausschließlich für den **privaten, persönlichen Gebrauch** bestimmt.
Das Scraping von Webseiten kann gegen deren Nutzungsbedingungen verstoßen.
Kein kommerzieller Einsatz. Bitte scrape verantwortungsbewusst (wenige Seiten, kein automatisches Dauerscraping).

---

## 🔮 Erweiterungsideen

- [ ] Preisalarm: benachrichtigen wenn ein neues Deal-Inserat erscheint
- [ ] Automatisches tägliches Scraping (cron job)
- [ ] Preishistorie über Zeit tracken
- [ ] Mehrere Suchanfragen gleichzeitig vergleichen
- [ ] Kartenansicht der Inserate (nach Ort)
