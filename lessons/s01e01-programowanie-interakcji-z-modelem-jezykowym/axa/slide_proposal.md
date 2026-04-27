# Slajd: Kod czy AI? Strategia Wyboru Architektury

## Nagłówek: Determinizm vs. Probabilistyka (Fundament S01E01)

| Kryterium | Tradycyjny Kod (Determinizm) | Model / Agent AI (Probabilistyka) |
| :--- | :--- | :--- |
| **Gwarancja** | 100% powtarzalności (A -> B) | Brak gwarancji (Wynik prawdopodobny) |
| **Zastosowanie** | Logika, RegEx, obliczenia, SQL | Dane nieustrukturyzowane, rozumowanie |
| **Zasada** | **Pierwszy wybór** (Efektywność) | **Ostateczność** (Last Resort) |
| **Koszt** | Stały / Minimalny (CPU) | Wysoki (płacimy za każdy **token**) |
| **Błędy** | Łatwe do debugowania | Trudne (Autoregresja - brak "cofnij") |

---

### Złota zasada z lekcji:
> "Jeśli potrafisz narysować algorytm zadania na kartce — użyj kodu. AI wprowadzaj tylko tam, gdzie elastyczność i 'wyczucie' kontekstu są niezbędne."

---

### Rekomendacja: Strategia Hybrydowa (The Google Way)
Nie wybieraj między AI a Kodem. Łącz je:
1. **Predictive AI** (Tradycyjne) – do twardych prognoz i liczb.
2. **Generative AI** (Agent) – do interpretacji tych prognoz i kontaktu z ludźmi.

**Zasada GTM (Go-To-Market):** Jeśli nie masz czasu na zbieranie ogromnych zbiorów danych do trenowania tradycyjnego AI — użyj Agenta z odpowiednim promptem, by szybciej dowieźć wartość biznesową.

