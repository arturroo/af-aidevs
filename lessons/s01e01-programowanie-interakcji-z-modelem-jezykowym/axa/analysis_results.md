# Raport: Agenci vs. Tradycyjne Programy (Analiza AI_devs S01E01)

Na podstawie analizy materiałów lekcyjnych oraz najnowszych wytycznych od Google, Anthropic i OpenAI, przygotowałam zestawienie kluczowych różnic i zasad implementacji.

## 1. Fundament: Kod (Determinizm) vs. AI (Probabilistyka)

Zgodnie z lekcją S01E01, kluczowym wyzwaniem jest łączenie dwóch sprzecznych natur:

| Cecha | Tradycyjny Kod (Software) | Modele LLM / Agenci AI |
| :--- | :--- | :--- |
| **Natura** | **Deterministyczna** (Przewidywalna) | **Probabilistyczna** (Prawdopodobna) |
| **Gwarancja** | Zawsze ten sam wynik dla tych samych danych. | Brak gwarancji powtarzalności (niedeterminizm). |
| **Koszt** | Minimalny (koszt procesora/pamięci). | Wysoki (płacimy za każdy **token**). |
| **Zasada wyboru** | **Pierwszy wybór.** Jeśli da się coś zrobić kodem — zrób to kodem. | **Ostateczność (Last Resort).** Używaj tylko tam, gdzie kod zawodzi. |

### Kluczowe zasady z lekcji:
- **Zarządzanie Kontekstem:** Sterowanie AI to w rzeczywistości programistyczne zarządzanie tym, co trafia do "okna kontekstowego".
- **Autoregresja:** Model nie może "cofnąć" wygenerowanego tokenu. Błąd na początku generowania psuje cały wynik.
- **Agent:** To nie tylko czat, to LLM wyposażony w **narzędzia** (Tools) i zdolny do elastycznej interakcji z otoczeniem przez te narzedzia.

## 2. Rozszerzenie: Wybór typu AI (Wytyczne Google & Anthropic)
Gdy już zdecydujesz, że tradycyjny kod to za mało, użyj poniższych kryteriów do wyboru rodzaju AI:

### Google Cloud (Kiedy Predictive, a kiedy Generative?)
- **Predictive AI (Tradycyjne AI):** Wybieraj dla danych strukturalnych (SQL/Tabele) i konkretnych liczb (prognozy sprzedaży, klasyfikacja spamu).
- **Generative AI (Agentic):** Wybieraj dla danych nieustrukturyzowanych (tekst, audio, wideo) i zadań wymagających "rozumowania" (streszczenia, research).
- **Kryterium GTM:** GenAI jest szybsze wdrożeniowo, jeśli nie masz czasu na zbieranie danych i trenowanie modelu.

### Anthropic (Kiedy Workflow, a kiedy Agent?)
- **Workflow:** Używaj, gdy proces da się zamknąć w stałych krokach (sztywny łańcuch promptów).
- **Agent:** Używaj tylko wtedy, gdy ścieżka do celu jest nieznana i wymaga autonomicznego podejmowania decyzji w pętli.

## 3. Rekomendowane materiały źródłowe (Verified Links)

### Google Cloud (Agentic AI)
- [Agentic AI Architecture Overview](https://cloud.google.com/architecture/agentic-ai-overview) – Główne centrum wiedzy o architekturze agentowej w Google Cloud.
- [Choose an Agent Design Pattern](https://cloud.google.com/architecture/choose-design-pattern-agentic-ai-system) – Przewodnik po wyborze wzorców projektowych (Single-agent vs Multi-agent).
- [Choose Agentic Architecture Components](https://cloud.google.com/architecture/choose-agentic-ai-architecture-components) – Jak dobierać komponenty (Orchestration, Tools, Memory).

### Anthropic
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) – Kluczowy artykuł o przejściu z prostych workflowów do zaawansowanych agentów.

