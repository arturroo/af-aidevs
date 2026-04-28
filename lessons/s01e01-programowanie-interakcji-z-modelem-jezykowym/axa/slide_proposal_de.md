# Wann sollte man traditionelle Software einsetzen und wann ein KI-Programm oder einen KI-Agenten?

## Determinismus vs. Probabilismus (Fundament S01E01)

| Kriterium | Traditioneller Code (Determinismus) | KI-Modell / Agent (Probabilismus) |
| :--- | :--- | :--- |
| **Hauptziel** | Präzise Ausführung von Anweisungen | Autonome Bewertung (im vorgegebenen Rahmen) der nächsten Schritte (Autonomous judgment), um das vorgegebene Ziel zu erreichen |
| **Prinzip** | **Erste Wahl (Höchster ROI).** Wenn es mit Code machbar ist – mach es mit Code | **Ultima Ratio.** Nur dort einsetzen, wo Code scheitert |
| **Garantie** | 100% Wiederholbarkeit (A -> B) | Keine Garantie. Erfordert Risikomanagement |
| **Prozessstabilität** | Vollständig definiert und stabil (z.B. Rechnungen) | Dynamisch, evolvierend, mehrdeutig (z.B. ChatBot) |
| **Präzision** | Kritisch (Finanzen, Compliance, 100%) | Nuancen, Kontext, Interpretation (z.B. PDF-Zusammenfassungen) |
| **Latenz** | Millisekunden (Real-time) | Sekunden/Minuten (NRT - Near Real Time), abhängig von Antwortlänge und Token-Generierungsgeschwindigkeit |
| **Logik** | Linear (if-then-else) | Schlussfolgerung, Planung, Anpassung an unvorhersehbaren Kontext und Intention |
| **Anwendung** | Algorithmen, RegEx, SQL (z.B. feste Datumsformate) | Unstrukturierte Daten, Intent-Erkennung (Berechnung von Daten aus dem Kontext, z.B. „Lass uns am nächsten Freitag treffen“) |
| **Kosten** | Konstant / Minimal (CPU, Speicher) | Hoch (wir zahlen für jeden **Token**) |
| **Fehler** | Logisch (leicht zu debuggen) | Halluzinationen, Denkfehler, Autoregression (kein „Rückgängig“ während der Token-Generierung – ein früher Fehler verdirbt das gesamte Ergebnis) |
| **Eingabedaten** | Strukturiert, sauber | Unstrukturiert, mehrdeutig |

---

### Goldene Regel aus dem Kurs:
> „Wenn du den Algorithmus der Aufgabe auf ein Blatt Papier zeichnen kannst – benutze Code. Führe KI nur dort ein, wo Flexibilität und das Verständnis des Kontextes notwendig sind.“

---

### Entscheidungsflow (Decision Flow):
1. **Ist der Prozess stabil und durch harte Regeln beschreibbar?** ➔ **TRADITIONELLER CODE**
2. **Prognostizieren Sie Werte oder klassifizieren Sie mit historischen Daten?** ➔ **TRADITIONELLE KI (ML)**
3. **Erfordert die Aufgabe logisches Denken, Interpretation oder eine schnelle Markteinführung (GTM)?** ➔ **GENERATIVE KI (Workflow or Agent)**

---

### Erweiterung: Workflow oder Agent?
Sobald Sie sich für KI entschieden haben, wählen Sie den Grad der Autonomie:
- **KI-Workflow:** Verwenden Sie diesen, wenn der Prozess in festen Schritten abgeschlossen werden kann (starre Kette von Prompts).
- **KI-Agent:** Nur verwenden, wenn der Weg zum Ziel unbekannt ist und autonome Entscheidungsfindung in einer Schleife erfordert.

---
*Quellen:*
- *Kurs: [AI_devs 4 Builders](https://aidevs.pl)*
- *Anthropic: [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)*
- *Google Cloud: [GenAI or Traditional AI](https://cloud.google.com/docs/ai-ml/generative-ai/generative-ai-or-traditional-ai)*
