# Einschätzung: Was funktioniert, was nicht, Risiken, Produktion

## Was bereits funktioniert

- Die Original-E-Mail wird **MV-10245** zugeordnet (0,90 Punkte). MV-10487 wird mit Begründung ausgeschlossen („Etage widerspricht: 2. OG ≠ 3. OG“).
- Die frühere „Rohrverstopfung Küche“ wird als **möglicher Zusammenhang** erkannt und landet in der internen Aufgabe – nicht in der Antwort an den Mieter.
- **14 Testfälle** laufen automatisch (u. a. ohne Etage, Vertrag inaktiv, anderer Absender, Notfall Gas, Mietfrage, Englisch, gesenkte Schwelle). Alle verhalten sich wie erwartet. Insgesamt über 500 automatische Tests.
- Ohne API-Schlüssel (Regelmodus) und mit Groq (live oder aufgezeichnet).
- n8n-Workflow mit einem Knoten pro Schritt, echt ausgeführt; Ergebnis landet in der Prüfliste.
- Oberfläche für Sachbearbeiter: Begründungen, Hausraster, Freigabe mit Stempel, Protokoll. **Es gibt keinen Senden-Knopf.**

## Was noch nicht zuverlässig funktioniert

- **Regelmodus ohne KI** erkennt nur bekannte Formulierungen (Schlüsselwörter). Ungewöhnliche Sätze („bei uns ist alles nass“) werden schlechter erkannt → dann eher „Prüfung nötig“, nicht falsch zugeordnet.
- **Groq** liefert gute Ergebnisse in den getesteten Fällen, aber nur 5 Fälle sind echt aufgezeichnet. Für eine Aussage zur Qualität braucht es ein größeres Test-Set mit echten (anonymisierten) E-Mails.
- **Identität:** Eine E-Mail beweist nicht, wer schreibt. Der Prototyp zeigt eine Warnung bei unbekannter Absenderadresse; die Entscheidung trifft der Mensch.
- **Zeitangaben** („seit gestern“) werden nur als Text übernommen, nicht in ein Datum umgerechnet.
- **Fotos/Anhänge** werden nicht ausgewertet.
- Die Antworttexte sind Vorlagen; sie sind korrekt, aber noch nicht von einer Fachabteilung freigegeben.

## Risiken

| Risiko | Wie der Prototyp damit umgeht | Was in Produktion dazukommt |
|---|---|---|
| Falscher Vertrag | Veto, Schwelle, Abstand, aktiv-Prüfung, menschliche Freigabe | Auswertung: wie oft ändern Menschen den Vorschlag? |
| KI erfindet Daten | KI kopiert nur Textstellen; Regeln rechnen um; Schema-Prüfung; Ausfall → Regelmodus | regelmäßiges Test-Set, Monitoring |
| Notfall bleibt liegen | Notfall oben, Sicherheitshinweise, Gebäude-Maßnahme ohne Einheit erlaubt | 24/7-Bereitschaft, SMS/Anruf; ggf. freigegebene automatische Eingangsbestätigung |
| Datenschutz (DSGVO) | nur erfundene Testdaten; an die KI geht nur der E-Mail-Text, nie ERP-Daten | EU-Hosting oder Vertrag zur Auftragsverarbeitung (AVV), Löschfristen, Rollen |
| Groq ist ein US-Anbieter, kostenloser Tarif | nur für die Demo | EU-Modell (z. B. Azure OpenAI EU, Mistral) oder selbst gehostet |
| Antwort mit falscher Zusage | Vorlagen statt freiem KI-Text; nie automatisch senden | Fachabteilung gibt Vorlagen frei |

## Was für den produktiven Einsatz fehlt

1. **Postfach-Anbindung** (Microsoft 365 / IMAP) über n8n, Warteschlange, keine Doppelverarbeitung (Message-ID).
2. **Echte ERP-Schnittstelle** hinter der vorhandenen `ERPConnector`-Schnittstelle: lesen für die Zuordnung, schreiben nur nach Freigabe.
3. **Anmeldung und Rollen** im Prüfplatz; Protokoll in einer Datenbank statt Datei.
4. **Test-Set** mit 100–200 anonymisierten echten E-Mails; Schwellen danach einstellen (Ziel: falsche Zuordnung ≈ 0, lieber mehr Prüfungen).
5. **Kennzahlen:** Anteil „bitte freigeben“, wie oft Menschen den Vorschlag ändern, Zeit bis zur ersten Antwort, Notfall-Reaktionszeit.
6. **Kosten:** Regelmodus ≈ 0 €; ein KI-Aufruf ≈ 1.500 Tokens pro E-Mail – bei bezahlten EU-Modellen Bruchteile eines Cents pro E-Mail.
7. Anhänge (Fotos) auswerten, Virenprüfung.
