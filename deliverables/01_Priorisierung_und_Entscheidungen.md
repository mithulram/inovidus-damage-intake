# Priorisierung und technische Entscheidungen

## Was mir am wichtigsten war

Die Aufgabe sagt: **Eine unklare Zuordnung darf nie zu einer Aktion am falschen Vertrag führen.** Darum habe ich zuerst die Zuordnung gebaut und erst danach alles andere. Die Daten enthalten eine Falle: Max Mustermann hat **zwei aktive Verträge** in der Musterstraße 12. Nur „zweite Etage links“ entscheidet – und das steht im ERP anders geschrieben („2. OG li.“).

## Die 9 Schritte nach Priorität

| Schritt | Priorität | Warum |
|---|---|---|
| 4 Zuordnung zum ERP | **Muss** | Der eigentliche Test: falscher Vertrag = falsche Aktion. |
| 7 Strukturierter Datensatz (JSON) | **Muss** | Schnittstelle zu ERP und Workflow; macht jede Entscheidung prüfbar. |
| 3 Informationen extrahieren | **Muss** | Ohne Adresse, Etage, Seite keine Zuordnung. |
| 2 Art erkennen | **Muss** | Schaden oder z. B. Mietfrage? Welches Gewerk? |
| 6 Dringlichkeit | **Muss** | Wasser läuft jetzt – falsche Priorität kostet Geld. |
| 8 Antwortentwurf | **Muss** | Ausdrücklich gefordert – und nie automatisch senden. |
| 5 Frühere Vorgänge | Soll | Die frühere „Rohrverstopfung Küche“ ist ein wichtiger Hinweis für den Handwerker. |
| 9 Interne Aufgabe | Soll | Macht aus dem Ergebnis Arbeit; einfache Vorlage reicht. |
| 1 Nachricht einlesen | Soll (einfach) | Im Prototyp: Webhook/Beispiele. Echtes Postfach ist Produktionsarbeit. |

**Bewusst nicht gebaut:** echtes Postfach, echte ERP-Schnittstelle, Foto-Analyse, Benutzerrollen. Das ist für einen Prototyp nicht nötig und steht in der Einschätzung als nächster Schritt.

## Technik – Alternativen und Entscheidung

| Option | Stärken | Schwächen | Entscheidung |
|---|---|---|---|
| **Python-Dienst + n8n + eigene Oberfläche** | Logik testbar (über 700 Tests), Regeln in einer Datei, n8n zeigt den Ablauf sichtbar | etwas mehr Aufbau | **gewählt** |
| nur n8n | sehr anschaulich, selbst hostbar | Zuordnungslogik in Code-Knoten schwer zu testen und zu versionieren | n8n nur als „Kleber“ |
| LangChain / LangGraph | viele Bausteine | zu schwer für 6 feste Schritte, versteckt die einfache Logik | nicht nötig |
| Dify | schnelle KI-Apps, RAG eingebaut | Logik in Plattform-Einstellungen, schwach für feste Regeln | eher für den Wissensassistenten |
| Streamlit als Oberfläche | sehr schnell | alle Streamlit-Apps sehen gleich aus, wenig Kontrolle | nicht gewählt |

**Grundidee:** *Die KI liest, feste Regeln entscheiden, ein Mensch handelt.*

| Teil | KI oder Regel? | Warum |
|---|---|---|
| Art erkennen, Fakten herauslesen | KI (Groq), ohne Schlüssel Regeln | freie Sprache, auch Englisch |
| Vertrag zuordnen, Status | **nur feste Regeln** | muss gleich, prüfbar und erklärbar sein – die KI wählt nie den Vertrag |
| Dringlichkeit | Regeln als Untergrenze + KI-Hinweis, die strengere Stufe gewinnt | Sicherheit: die KI darf nur erhöhen |
| Antwort und Aufgabe | Textvorlagen | eine Antwort enthält Zusagen – Wortlaut muss die Fachabteilung freigeben |

**KI-Anbieter:** Groq (kostenloser Tarif, Modell `openai/gpt-oss-120b`, strenges JSON-Schema). Fällt Groq aus oder liefert ungültige Daten: einmal neu versuchen, dann automatisch Regelmodus. Der Prototyp läuft **komplett ohne Schlüssel**. Echte Groq-Antworten sind aufgezeichnet (`examples/llm_recorded/`), damit jede:r sie ohne Schlüssel nachvollziehen kann.

## Umgang mit Unsicherheit (der Kern)

1. **Punkte je Merkmal:** Name 0,30 · Adresse 0,30 · Etage 0,20 · Seite 0,10 · Kontakt 0,10. Jedes Merkmal: passt / teilweise / fehlt / widerspricht – mit Begründung auf Deutsch.
2. **Widerspruch = Veto:** Sagt die E-Mail „2. OG“ und der Vertrag ist im 3. OG, ist der Vertrag raus – egal, wie hoch die Schwelle eingestellt ist.
3. **Schwelle (0,85) und Abstand (0,15):** Der beste Vertrag muss gut genug **und** klar besser als der zweite sein.
4. **Vertrag aktiv?** Erst wenn die Einheit eindeutig ist. Ist der Vertrag beendet: Prüfung – **nie** auf einen anderen Vertrag ausweichen.
5. **Zusätzliche Prüfgründe:** Name nur ähnlich, Absender ist nicht Vertragsinhaber, Etage fehlt oder unklar, englische Etagenangabe („2nd floor“ – britisch 2. OG, amerikanisch 1. OG), mehrere oder unsichere Ortsangaben (ist sogar das Gebäude unsicher, gibt es auch keine Gebäude-Maßnahme).

Ergebnis: **„Bitte freigeben“** oder **„Prüfung nötig“** oder **„Weiterleiten“**. Kein Status handelt allein. Jede Aktion am Vertrag braucht eine Freigabe mit Name und Zeit; bei „Prüfung nötig“ zusätzlich eine Begründung. Alles steht im Protokoll.

Bei **Notfällen** (Gas, Rohrbruch) gilt: sofort oben in der Liste, Sicherheitshinweise in der Antwort – und Maßnahmen für das **Gebäude** (Notdienst, Hausmeister) sind erlaubt, auch wenn die Wohnung noch unklar ist (nicht aber, wenn das Gebäude unsicher ist).

## Regeln live ändern

Alle Regeln stehen in `config/rules.yaml`. Beispiel: Schwelle auf 0,95 setzen → Datei speichern → im Prüfplatz „Regeln → Alle Beispiele neu prüfen“. Die Tabelle zeigt sofort, welche Fälle sich ändern.
