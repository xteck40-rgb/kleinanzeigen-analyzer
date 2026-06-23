# 🚀 Kleinanzeigen Analyzer — auf einem (anderen) PC betreiben

Die App läuft jetzt im **Ein-Prozess-Modus**: ein einziges Programm liefert
Backend **und** Frontend aus. Es gibt nur **eine Adresse** und **einen Port (8000)** —
kein zweites Fenster, kein Node zum Laufen nötig.

```
dieser PC:          http://localhost:8000
im Netz / Tailscale: http://<IP-des-PCs>:8000
```

---

## A) Auf diesem PC (schon eingerichtet)

```powershell
.\start.ps1
```
Fenster offen lassen. Im Browser `http://localhost:8000` öffnen.

Soll die App nach jedem Windows-Neustart von selbst starten:
```powershell
.\autostart.ps1 -Install
```

---

## B) Auf einem komplett neuen PC einrichten

### 1. Voraussetzungen installieren
- **Python 3.11** → https://www.python.org/downloads/release/python-3119/
  Beim Installieren **„Add python.exe to PATH"** anhaken. (Pflicht.)
- **Node.js** → https://nodejs.org
  Nur nötig, wenn der Ordner `frontend\dist` NICHT mitkopiert wurde.
  (Tipp: Wenn du `frontend\dist` mitkopierst, brauchst du auf dem neuen PC **kein** Node.)

### 2. Projektordner kopieren
Den kompletten Ordner `kleinanzeigen-analyzer` auf den neuen PC kopieren
(USB-Stick, Netzwerk, …).
**Nicht mitkopieren** (wird neu erzeugt, spart Platz):
- `backend\venv`
- `frontend\node_modules`

`backend\kleinanzeigen.db` mitkopieren = deine Suchen/Agenten/Nutzer wandern mit.
Weglassen = frische, leere Datenbank.

### 3. Einrichten (einmalig)
PowerShell im Projektordner öffnen, dann:
```powershell
.\setup.ps1
```
Das erstellt das venv mit Python 3.11, installiert alle Pakete + den
Playwright-Browser und baut das Frontend. Dauert beim ersten Mal ein paar Minuten.

### 4. Starten
```powershell
.\start.ps1
```
Fertig — `http://localhost:8000` im Browser.

### 5. Von überall erreichbar machen (Tailscale)
1. https://tailscale.com/download → installieren, **mit deinem Account** anmelden
   (gleicher Account wie auf deinen anderen Geräten → selbes Netz).
2. Tailscale-IP anzeigen: `start.ps1` zeigt sie beim Start an, oder im Terminal:
   ```powershell
   & "C:\Program Files\Tailscale\tailscale.exe" ip -4
   ```
3. Vom Handy (Tailscale-App an): `http://<diese-IP>:8000`

### 6. Autostart nach Neustart
```powershell
.\autostart.ps1 -Install
```
Für einen echten „immer an"-Server zusätzlich:
- **Energiesparmodus aus:** Einstellungen → System → Strom → „Nie" (bei Netzbetrieb).
- **Auto-Anmeldung** (optional, damit nach Reboot ohne Eingabe alles hochfährt):
  `netplwiz` ausführen → Haken bei „Benutzer müssen Namen und Kennwort eingeben" entfernen.

---

## Falls die Windows-Firewall blockt

Wenn andere Geräte die App nicht erreichen (Timeout), einmalig in einer
PowerShell **als Administrator**:
```powershell
New-NetFirewallRule -DisplayName "Kleinanzeigen Analyzer" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000
```

---

## Befehls-Übersicht

| Was | Befehl |
|---|---|
| Einrichten (einmalig / neuer PC) | `.\setup.ps1` |
| Starten | `.\start.ps1` |
| Autostart an | `.\autostart.ps1 -Install` |
| Autostart aus | `.\autostart.ps1 -Uninstall` |
| Autostart-Status | `.\autostart.ps1 -Status` |
| Sofort über Aufgabe starten | `Start-ScheduledTask -TaskName KleinanzeigenAnalyzer` |

---

## Wichtige Hinweise

- **OpenRouter-Key** ist pro Installation/DB gespeichert (Tab *Agenten → Einstellungen*).
  Neuer PC ohne mitkopierte `kleinanzeigen.db` → Key dort einmal neu eintragen.
- **Scraping-IP:** Kleinanzeigen blockt Rechenzentrums-IPs. Auf einem normalen
  PC/Mini-PC mit Heim-Internet läuft es zuverlässig; auf einem Cloud-Server (VPS)
  kann es zu leeren Ergebnissen / Captchas kommen.
- **Entwicklung mit Hot-Reload** (nur wenn du am Code arbeitest): weiterhin
  `cd backend; .\venv\Scripts\python -m uvicorn main:app` **und** in einem zweiten
  Fenster `cd frontend; npm run dev` → dann über `http://localhost:5173`.
  Für den normalen Betrieb ist das **nicht** nötig.
