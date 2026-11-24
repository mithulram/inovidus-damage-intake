# Überblick – so kannst du den Prototyp prüfen

**Kurz gesagt:** Eine Mieter-E-Mail wird in sechs Schritten zu einem geprüften Vorgang. Die KI liest die E-Mail,
feste Regeln ordnen sie dem richtigen Vertrag zu, ein Mensch gibt frei. Ist etwas unklar, rät das System nicht,
sondern sagt **„Prüfung nötig“**. Nichts wird automatisch gesendet.

**Bebilderter Rundgang mit allen Funktionen:** [00_Rundgang.md](00_Rundgang.md)

## Zugang

| Was | Link | Anmeldung |
|---|---|---|
| Prüfplatz (Oberfläche) | https://inovidus-intake.onrender.com | Benutzer `demo`, Passwort `demo` |
| n8n (sichtbarer Ablauf) | https://inovidus-n8n.onrender.com | `owner@intake-demo.example` / `Demo1234` |
| Quellcode | https://github.com/mithulram/inovidus-damage-intake | öffentlich |

Beide Dienste laufen im kostenlosen Tarif von Render. Nach längerer Pause schlafen sie ein: Der erste Aufruf des
Prüfplatzes dauert dann etwa eine Minute, n8n braucht beim Aufwachen einige Minuten. Danach läuft alles normal.

## In 5 Minuten durchklicken
1. **Prüfplatz öffnen**, oben rechts *Sprache* wählen (Deutsch, English oder beides).
2. Links das Beispiel **S1 „Wasserschaden Küche, Musterstraße 12“** öffnen – das ist die E-Mail aus der Aufgabe.
   Ergebnis: **MV-10245**, 0,90 Punkte. MV-10487 ist ausgeschlossen, weil Etage und Seite widersprechen.
   Darunter: früherer Vorgang „Rohrverstopfung Küche“, Dringlichkeit DRINGEND, Antwortentwurf, interne Aufgabe, JSON.
3. **S2** öffnen (gleiche E-Mail ohne „zweite Etage links“): beide Verträge passen gleich gut → **Prüfung nötig**,
   der Entwurf fragt beim Mieter nach. Genau das ist der Umgang mit Unsicherheit.
4. Unten links **„Eigene E-Mail prüfen“**: eine eigene Schadenmeldung eintippen und verarbeiten lassen.
   Oben *Leser* wählen: „Regeln (ohne KI)“, „Groq · live“ (KI liest live) oder „Groq · Aufzeichnung“
   (gespeicherte KI-Antworten für fünf Beispiele, z. B. S1 – funktioniert auch ohne Verbindung zu Groq).
5. Reiter **Regeln**: die fachlichen Werte stehen in einer Datei (`config/rules.yaml`). Lokal: ändern, speichern – gilt sofort, kein Deployment. Online-Version: ändern, speichern, dann neu deployen. Reiter **Protokoll**: jede
   Freigabe wird festgehalten. Reiter **Ablauf**: der n8n-Workflow.

## Wo steht was (deine Liste aus der Aufgabe)

| Gefordert | Datei |
|---|---|
| Funktionsfähiger Prototyp / Workflow | Links oben · Start lokal: `README.md` („In 3 Befehlen starten“) |
| Workflow-Export / Quellcode | `workflows/n8n_schadenmeldung.json` · Quellcode in `src/` |
| Beispielhafte Ausgabe | `examples/` (JSON der Beispiel-E-Mail, mit und ohne KI) |
| Architekturübersicht | `deliverables/02_Architektur.md` |
| Was funktioniert, was nicht, Risiken, Produktivbetrieb | `deliverables/03_Einschaetzung.md` |
| Wiederverwendung für einen Wissensassistenten | `deliverables/04_Wiederverwendung_Wissensassistent.md` |
| KI-Nutzung und eigene Prüfung | `deliverables/05_KI_Nutzung.md` |
| Tatsächlicher Aufwand | `deliverables/06_Aufwand.md` |
| Tests und Sicherheit | `deliverables/07_Tests_und_Sicherheit.md` |
| Priorisierung und Entscheidungen | `deliverables/01_Priorisierung_und_Entscheidungen.md` |

Die Unterlagen 01–07 und diese Übersicht gibt es auch auf Englisch in `deliverables/en/`. Der bebilderte Rundgang ist auf Deutsch.
