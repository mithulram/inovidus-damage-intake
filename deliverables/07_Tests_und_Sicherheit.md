# Tests und Sicherheit

## Wie ich getestet habe
- **Von Hand, Ende zu Ende:** alle 14 Beispiele im Prüfplatz durchgespielt, eigene E-Mails live verarbeitet (mit und ohne KI),
  über n8n eingespielt und bis zur Prüfliste und Freigabe verfolgt – lokal und online.
- **Automatisch:** **993 Tests** mit `pytest`, Start mit `uv run pytest` (ca. 1 Minute). Jeder gefundene Fehler bekommt einen Test,
  damit er nicht zurückkommt.
- **Beispiel-Szenarien:** `uv run intake-scenarios` prüft alle 14 Fälle gegen ihr erwartetes Ergebnis
  (Status, Vertrag, Dringlichkeit, verletzte Prüfregeln). Im Prüfplatz geht das auch per Klick: *Regeln → Alle Beispiele neu prüfen*.

## Was die Tests abdecken

| Bereich | Tests | Beispiele |
|---|---|---|
| Lesen ohne KI (Regelmodus) | 457 | Etagen in Worten und Zahlen, „2. bzw. 3. OG“, „nicht links“, Hausnummern, PLZ/Ort, Englisch |
| Sonderfälle aus dem Testen | 115 + 75 | ungewöhnliche Formulierungen, jemand schreibt für eine andere Person, „Hinterhaus“, „Wohnung 5“ |
| Zuordnung | 47 | Punkte je Merkmal, Widerspruch = Ausschluss, Schwelle, Abstand, Vertrag inaktiv |
| Dringlichkeit | 43 | Regeln setzen die Untergrenze, KI darf nur erhöhen, Heizperiode, Sicherheitshinweise bei Gas |
| Antwort und Aufgabe | 47 | Sprache der E-Mail, keine ERP-Daten bei unklarer Zuordnung, Rückfrage-Text |
| KI-Anbindung | 47 | ungültige KI-Antwort, Ausfall, Limit → automatisch Regelmodus |
| Freigabe und Aktionen | 39 | nichts ohne Freigabe, manuelle Zuordnung nur mit Begründung, kein Sendebefehl im Code |
| Schnittstelle (API) | 38 | Versiegelung, Versionsprüfung, Reihenfolge der Schritte, Zugangsschutz |
| Beispiel-Szenarien | 39 | die 14 Fälle mit genauem erwarteten Ergebnis |
| Übrige | 46 | frühere Vorgänge, Übersetzungen, n8n-Export, Hosting |

## Sicherheit – was es gibt
- **Kein automatischer Versand.** Es gibt im Code keine Sendefunktion; der Entwurf wird nur in die Zwischenablage kopiert.
- **Keine Aktion ohne Freigabe.** Aktionen am Vertrag laufen nur über einen Freigabe-Punkt; jede Freigabe steht im Protokoll.
- **Zugangsschutz online:** Passwort für den Prüfplatz, eigenes Konto für n8n, der n8n-Eingang (Webhook) braucht einen geheimen Schlüssel.
- **Die KI muss zitieren:** Adresse, Etage und Seite, die die KI liefert, müssen wörtlich in der E-Mail stehen – sonst werden sie nicht verwendet (fehlt dadurch die Etage: Prüfung nötig).
- **Versiegelte Vorgänge:** Der Server unterschreibt jeden Vorgang (HMAC). Ein veränderter Vorschlag wird abgelehnt.
- **Versionsprüfung:** Ändern sich Regeln oder ERP-Daten, gelten alte Freigaben nicht mehr – der Vorgang muss neu geprüft werden.
- **Geheimnisse nur in `.env`** bzw. in den Einstellungen von Render, nie im Code.
- **Datenschutz:** erfundene Testdaten, dazu ein eigener Testmieter mit meinem Namen und meiner E-Mail-Adresse. Im Modus „Groq live“ geht der E-Mail-Text an einen US-Anbieter – darauf weist die Oberfläche hin. Ist ein Groq-Schlüssel gesetzt, gilt das auch für die Leseübersetzung eigener E-Mails im Sprachwechsel.

## Sicherheit – was bewusst fehlt (für den Produktivbetrieb nötig)
- Benutzerkonten und Rollen (heute ein gemeinsames Demo-Passwort).
- Dauerhafte Datenbank (heute Dateien; ein Neustart der kostenlosen Hosting-Instanz leert die Prüfliste).
- Begrenzung der Anfragen pro Minute, Überwachung und Alarme.
- Auftragsverarbeitung (DSGVO) mit einem KI-Anbieter in der EU oder ein lokales Modell.
- Echte Anbindung von Postfach und ERP mit eigenen, eingeschränkten Zugängen.

Mehr zu Grenzen und Risiken: [03_Einschaetzung.md](03_Einschaetzung.md).
