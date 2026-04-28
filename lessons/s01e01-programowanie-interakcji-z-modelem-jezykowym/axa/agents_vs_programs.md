# Agents vs. Traditional Programs: Strategic Decision Framework

Ten dokument zawiera syntezę wiedzy z lekcji S01E01 oraz najlepszych praktyk branżowych (Google, Anthropic, OpenAI) dotyczących wyboru między agentami AI a tradycyjnym oprogramowaniem.

## 1. Fundament: Workflows vs. Agents (Anthropic Strategy)
Anthropic wprowadza kluczowe rozróżnienie, które pomaga szefowi zrozumieć skalę ryzyka i elastyczności:

- **Workflows (Przepływy):** Systemy sterowane kodem. LLM jest używany tylko jako "inteligentna funkcja" wewnątrz sztywnego algorytmu. Przewidywalne, tanie, bezpieczne.
- **Agents (Agenci):** Systemy sterowane przez model. To LLM decyduje o kolejnych krokach, wyborze narzędzi i pętli działania. Elastyczne, ale trudniejsze w kontroli i droższe.

---

## 2. Slajd dla Szefa: Kiedy co wybrać? (PROPOSAL)

> [!TIP]
> **Kryterium decyzyjne: "Predictability vs. Adaptability"**

| Cecha | Tradycyjny Program (Deterministyczny) | Agent AI (Agentyczny/Probabilistyczny) |
| :--- | :--- | :--- |
| **Główny cel** | Precyzyjna egzekucja instrukcji | Autonomiczne osiągnięcie celu (Goal-oriented) |
| **Logika** | Liniowa (if-then-else) | Rozumowanie, planowanie, adaptacja |
| **Dane wejściowe** | Ustrukturyzowane, czyste | Nieustrukturyzowane, niejednoznaczne, mess |
| **Środowisko** | Stabilne, przewidywalne | Zmienne, dynamiczne, nieznane |
| **Ryzyko** | Błąd logiczny (crash) | Halucynacja / Błąd w rozumowaniu |
| **Koszt** | Stały, niski | Zmienny, zależny od "myślenia" modelu |

---

## 3. Best Practices od Gigantów (Google, Anthropic, OpenAI)

### A. Google: "Decomposition & Microservices"
- **Rozbijaj monolity:** Nie buduj jednego agenta "do wszystkiego". Twórz małe, wyspecjalizowane mikro-agenty (np. jeden do SQL, drugi do analizy PDF).
- **Agent2Agent (A2A):** Agenci powinni komunikować się przez ustrukturyzowane protokoły (np. MCP), a nie tylko luźny tekst.
- **Separacja logiczna:** LLM powinien służyć do wyciągania intencji, ale egzekucja (np. przelew, usunięcie pliku) musi być zatwierdzona przez kod deterministyczny.

### B. Anthropic: "Simple is Better"
- **"Do you need AI?":** Jeśli problem rozwiążesz RegExem lub 5 liniami kodu – zrób to kodem. AI to "ostatnia deska ratunku" dla problemów zbyt złożonych na algorytm.
- **Observability:** Agenci muszą logować swój proces myślowy (Chain of Thought). Szef musi widzieć, *dlaczego* agent podjął taką decyzję.

### C. OpenAI: "Structured Reliability"
- **Structured Outputs:** Zawsze wymuszaj format JSON Schema. To jedyny sposób, by "niedeterministyczny" model bezpiecznie połączyć z "deterministycznym" systemem bankowym/ERP.
- **Model Routing:** Proste zadania (klasyfikacja) deleguj do tanich modeli (GPT-4o mini / Gemini Flash). Tylko trudne wnioskowanie puszczaj przez modele "Premium".

---

## 4. Podsumowanie (The Golden Rule)
Zacznij od **tradycyjnego programu** z elementami LLM (Workflow). Przejdź na **pełnego agenta** tylko wtedy, gdy liczba wyjątków w logice staje się niemożliwa do zakodowania ręcznie.

---
*Opracowano na podstawie materiałów AI_devs 4 oraz oficjalnych wytycznych Google Cloud, Anthropic i OpenAI.*
