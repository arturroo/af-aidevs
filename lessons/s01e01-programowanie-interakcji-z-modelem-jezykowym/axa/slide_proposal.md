# Kiedy stosować tradycyjne oprogramowanie, a kiedy program z AI lub agenta AI?

## Determinizm vs. Probabilistyka (Fundament S01E01)

| Kryterium | Tradycyjny Kod (Determinizm) | Model / Agent AI (Probabilistyka) |
| :--- | :--- | :--- |
| **Główny cel** | Precyzyjna egzekucja instrukcji | Autonomiczna ocena (w zadanych ramach) kolejnych kroków (Autonomous judgment) aby osiągnąć zadany cel |
| **Zasada** | **Pierwszy wybór (Najwyższe ROI).** Jeśli da się coś zrobić kodem — zrób to kodem | **Ostateczność (Last Resort).** Używaj tylko tam, gdzie kod zawodzi |
| **Gwarancja** | 100% powtarzalności (A -> B) | Brak gwarancji. Wymaga obsługi ryzyka błędu |
| **Stabilność procesu** | W pełni zdefiniowany i stały (np. faktury) | Dynamiczny, ewoluujący, niejednoznaczny (np. ChatBot) |
| **Precyzja** | Krytyczna (Finanse, Compliance, 100%) | Niuansowanie, kontekst, interpretacja treści (np. streszczenia PDF) |
| **Opóźnienie (Latency)** | Milisekundy (Real-time) | Sekundy/Minuty (NRT - Near Real Time), zależne od długości odpowiedzi i szybkości generowania tokenów |
| **Logika** | Liniowa (if-then-else) | Rozumowanie, planowanie, adaptacja do nieprzewidywalnego kontekstu i intencji |
| **Zastosowanie** | Algorytmy, RegEx, SQL (np. stałe formaty dat) | Dane nieustrukturyzowane, rozpoznawanie intencji (wyliczanie dat z kontekstu, np. "Spotkajmy się w przyszły piątek") |
| **Koszt** | Stały / Minimalny (CPU, Memory) | Wysoki (płacimy za każdy **token**) |
| **Błędy** | Logiczne (Łatwe do debugowania) | Halucynacje, błędy w rozumowaniu, Autoregresja (brak "cofnij" w trakcie generowania tokenów — błąd na starcie psuje cały wynik) |
| **Dane wejściowe** | Ustrukturyzowane, czyste | Nieustrukturyzowane, niejednoznaczne |

---

### Złota zasada z kursu:
> "Jeśli potrafisz narysować algorytm zadania na kartce — użyj kodu. AI wprowadzaj tylko tam, gdzie elastyczność i zrozumienie kontekstu są niezbędne."

---

### Ścieżka Decyzyjna (Decision Flow):
1. **Czy proces jest stały i opisany twardymi regułami?** ➔ **TRADYCYJNY KOD**
2. **Przewidujesz wartości lub klasyfikujesz i masz dane historyczne?** ➔ **TRADYCYJNE AI (ML)**
3. **Zadanie wymaga rozumowania lub interpretacji treści?** ➔ **GENERATIVE AI (Workflow lub Agent)**

---

### Rozszerzenie: Workflow czy Agent?
Gdy już wybierzesz AI, dopasuj stopień autonomii:
- **AI Workflow:** Używaj, gdy proces da się zamknąć w stałych krokach (sztywny łańcuch promptów).
- **AI Agent:** Używaj, gdy ścieżka do celu jest nieznana i wymaga autonomicznego podejmowania decyzji w pętli.

---
*Źródła:*
- *Kurs: [AI_devs 4 Builders](https://aidevs.pl)*
- *Anthropic: [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)*
- *Google Cloud: [GenAI or Traditional AI](https://cloud.google.com/docs/ai-ml/generative-ai/generative-ai-or-traditional-ai)*
