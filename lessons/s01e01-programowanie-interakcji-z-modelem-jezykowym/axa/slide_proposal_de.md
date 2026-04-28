# Slide: Code oder KI? Strategie zur Architekturauswahl

## Header: Determinismus vs. Probabilismus (Fundament S01E01)

| Kriterium | Traditioneller Code (Determinismus) | KI-Modell / Agent (Probabilismus) |
| :--- | :--- | :--- |
| **Hauptziel** | Präzise Ausführung von Anweisungen | Autonome Zielerreichung (Zielorientiert) |
| **Prinzip** | **Erste Wahl (Höchster ROI).** Wenn es mit Code machbar ist – mach es mit Code. | **Ultima Ratio.** Nur dort einsetzen, wo Code scheitert. |
| **Garantie** | 100% Wiederholbarkeit (A -> B) | Keine Garantie. Erfordert Risikomanagement. |
| **Prozessstabilität** | Vollständig definiert und stabil (z.B. Rechnungen) | Dynamisch, evolvierend, mehrdeutig (z.B. ChatBot) |
| **Präzision** | Kritisch (Finanzen, Compliance, 100%) | Nuancen, Kontext, Interpretation (z.B. PDF-Zusammenfassungen) |
| **Latenz** | Millisekunden (Real-time) | Sekunden/Minuten (NRT - Near Real Time), abhängig von Antwortlänge und Token-Generierungsgeschwindigkeit |
| **Logik** | Linear (if-then-else) | Schlussfolgerung, Planung, Anpassung an unvorhersehbaren Kontext und Intention |
| **Anwendung** | Algorithmen, RegEx, SQL (z.B. feste Datumsformate) | Unstrukturierte Daten, Intentionen (Berechnung von Daten aus dem Kontext, z.B. „Lass uns am nächsten Freitag treffen“) |
| **Kosten** | Konstant / Minimal (CPU, Speicher) | Hoch (wir zahlen für jeden **Token**) |
| **Fehler** | Logisch (leicht zu debuggen) | Halluzinationen, Denkfehler, Autoregression (kein „Rückgängig“ während der Token-Generierung) |
| **Eingabedaten** | Strukturiert, sauber | Unstrukturiert, mehrdeutig |

---

### Goldene Regel aus der Lektion:
> „Wenn du den Algorithmus der Aufgabe auf ein Blatt Papier zeichnen kannst – benutze Code. Führe KI nur dort ein, wo Flexibilität und das 'Gespür' für den Kontext notwendig sind.“

---

### Kernprinzipien aus der Lektion:
- **Autoregression:** Das Modell kann einen generierten Token nicht „rückgängig“ machen. Ein Fehler zu Beginn verdirbt das gesamte Ergebnis.
- **Agent:** Das ist nicht nur ein Chat, sondern ein LLM, das mit **Werkzeugen** ausgestattet ist und in der Lage ist, über diese Werkzeuge flexibel mit der Umgebung zu interagieren.

---

## Erweiterung: KI-Workflow oder KI-Agent?
Wenn traditioneller Code nicht ausreicht, wählen Sie die richtige Stufe der KI-Autonomie:

### Anthropic (Workflow vs. Agent)
- **KI-Workflow:** Verwenden Sie diesen, wenn der Prozess in festen Schritten abgeschlossen werden kann (starre Kette von Prompts).
- **KI-Agent:** Nur verwenden, wenn der Weg zum Ziel unbekannt ist und autonome Entscheidungsfindung in einer Schleife erfordert.
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) – Wichtiger Artikel über den Übergang von einfachen Workflows zu fortgeschrittenen Agenten.

---
**Erstellt von: Joi für Artur (2026-04-28)**
