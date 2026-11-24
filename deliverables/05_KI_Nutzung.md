# KI-Nutzung

Die Idee der Lösung, die fachlichen Regeln und alle Entscheidungen sind von mir.

Für die **Umsetzung** habe ich LLM-Werkzeuge eingesetzt: Sie haben nach meinen Anweisungen Pläne, Texte, Code und
Tests geschrieben. Ich habe die Ergebnisse geprüft, entschieden, was korrigiert
wird, und jede Änderung freigegeben, bevor sie veröffentlicht wurde.

Im Produkt selbst liest **Groq** (`openai/gpt-oss-120b`) die E-Mails – nur mit Demo-Daten.

## Meine Entscheidungen
- Das System rät nie: unklare oder fehlende Angaben → **Prüfung nötig**, keine Aktion am Vertrag.
- Die Antwort an den Mieter wird **nie automatisch gesendet** – nur Entwürfe, ein Mensch gibt frei.
- **Nur kostenlose Werkzeuge**; die Anwendung läuft auch ohne API-Schlüssel (Regelmodus, aufgezeichnete KI-Antworten).
- Die KI liest nur; **den Vertrag wählen feste Regeln** (Punkte je Merkmal, Schwelle, Abstand, Widerspruch, Vertrag aktiv).
- Deutsche Etagen-Zählweise (EG = Erdgeschoss); fehlende oder unklare Etage → immer nachfragen.
- Unbekannte Absenderadresse: nicht blockieren, sondern deutliche Warnung und drei Optionen für die Sachbearbeitung.
- Eigene Oberfläche, **n8n als sichtbarer Prozess**, alles auf Deutsch und Englisch lesbar, kostenloses Hosting.
- Qualitätsregel: jeder gefundene Fehler wird mit einem Test abgesichert (993 Tests, 14 Beispiel-Szenarien).

## Was ich selbst geprüft habe
- Die ganze Anwendung Schritt für Schritt: alle Beispiel-Testfälle selbst durchgespielt.
- Eigene E-Mails live verarbeitet und Ende zu Ende geprüft – vom Eingang über n8n bis zur Prüfliste und Freigabe.
- Den n8n-Ablauf auf meinem Laptop mit der Online-Anwendung ausgeführt.
