# Slajd: Kod czy AI? Strategia Wyboru Architektury

## Nagłówek: Determinizm vs. Probabilistyka (Fundament S01E01)

| Kryterium | Tradycyjny Kod (Determinizm) | Model / Agent AI (Probabilistyka) |
| :--- | :--- | :--- |
| **Główny cel** | Precyzyjna egzekucja instrukcji | Autonomiczne osiągnięcie celu (Goal-oriented) |
| **Zasada** | **Pierwszy wybór (Najwyższe ROI).** Jeśli da się coś zrobić kodem — zrób to kodem. | **Ostateczność (Last Resort).** Używaj tylko tam, gdzie kod zawodzi. |
| **Gwarancja** | 100% powtarzalności (A -> B) | Brak gwarancji. Wymaga obsługi ryzyka błędu. |
| **Stabilność procesu** | W pełni zdefiniowany i stały (np. faktury) | Dynamiczny, ewoluujący, niejednoznaczny (np. ChatBot) |
| **Precyzja** | Krytyczna (Finanse, Compliance, 100%) | Niuansowanie, kontekst, interpretacja treści (np. streszczenia PDF) |
| **Opóźnienie (Latency)** | Milisekundy (Real-time) | Sekundy/Minuty (NRT - Near Real Time), zależne od długości odpowiedzi i szybkości generowania tokenów |
| **Logika** | Liniowa (if-then-else) | Rozumowanie, planowanie, adaptacja do nieprzewidywalnego kontekstu i intencji |
| **Zastosowanie** | Algorytmy, RegEx, SQL (np. stałe formaty dat) | Dane nieustrukturyzowane, intencje (wyliczanie dat z kontekstu, np. "Spotkajmy się w przyszły piątek") |
| **Koszt** | Stały / Minimalny (CPU, Memory) | Wysoki (płacimy za każdy **token**) |
| **Błędy** | Logiczne (Łatwe do debugowania) | Halucynacje, błędy w rozumowaniu, Autoregresja (brak "cofnij" w trakcie generowania tokenów) |
| **Dane wejściowe** | Ustrukturyzowane, czyste | Nieustrukturyzowane, niejednoznaczne |

---

### Złota zasada z lekcji:
> "Jeśli potrafisz narysować algorytm zadania na kartce — użyj kodu. AI wprowadzaj tylko tam, gdzie elastyczność i 'wyczucie' kontekstu są niezbędne."

---

### Kluczowe zasady z lekcji:
- **Autoregresja:** Model nie może "cofnąć" wygenerowanego tokenu. Błąd na początku generowania psuje cały wynik.
- **Agent:** To nie tylko czat, to LLM wyposażony w **narzędzia** (Tools) i zdolny do elastycznej interakcji z otoczeniem przez te narzędzia.

---

## Rozszerzenie: Kiedy AI Workflow, a kiedy AI Agent?
Gdy tradycyjny kod to za mało, wybierz odpowiedni stopień autonomii AI:

### Anthropic (Workflow vs. Agent)
- **AI Workflow:** Używaj, gdy proces da się zamknąć w stałych krokach (sztywny łańcuch promptów).
- **AI Agent:** Używaj tylko wtedy, gdy ścieżka do celu jest nieznana i wymaga autonomicznego podejmowania decyzji w pętli.
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) – Kluczowy artykuł o przejściu z prostych workflowów do zaawansowanych agentów.
