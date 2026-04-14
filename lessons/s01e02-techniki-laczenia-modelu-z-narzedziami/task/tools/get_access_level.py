import os
import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")
AIDEVS_API_ACCESSLEVEL = os.getenv("AIDEVS_API_ACCESSLEVEL")

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def _make_api_request(url, payload):
    response = requests.post(url, json=payload)
    print(f"[get_access_level] API Response {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.text

def get_access_level(name: str, surname: str, birthYear: int, reasoning: str) -> str:
    """
    Pobiera z serwera poziom dostępu (accessLevel) osoby o podanych danych.
    Wymagane jest dokładne imię, nazwisko i poprawny rok urodzenia (jako liczba całkowita).
    Zwraca JSON z wynikiem od serwera (tekstem bez parsowania, do oczytania przez LLM).
    
    Args:
        name: Imię sprawdzanej osoby.
        surname: Nazwisko sprawdzanej osoby.
        birthYear: Rok urodzenia.
        reasoning: Krótkie uzasadnienie agenta (Chain of Thought), dlaczego wywołuje to narzędzie.
    """
    url = AIDEVS_API_ACCESSLEVEL
    payload = {
        "apikey": AIDEVS_API_KEY,
        "name": name,
        "surname": surname,
        "birthYear": int(birthYear)
    }
    
    try:
        result = _make_api_request(url, payload)
        # ---------------------------------------------------------------------------------------------------------
        # [BEST PRACTICE Z PRODUKCJI - CONTEXT THREADING / TRACEABILITY]
        # Tworzymy bezpośrednie, werbalne ugruntowanie podmiotu (Subject Threading) by LLM po kilkunastu 
        # asynchronicznych iteracjach i tysiącach przetworzonych tokenów historii nie miał problemu z 
        # identyfikacją faktu, komu właśnie przypisaliśmy dany poziom dostępu i nie pomieszał osób ze sobą.
        # ---------------------------------------------------------------------------------------------------------
        return f"[Śledztwo: {name} {surname}] Otrzymano poziom dostępu z API: {result}"
    except Exception as e:
        return f"[Śledztwo: {name} {surname}] Błąd pobierania dostępu z API (przekroczono liczbę prób): {e}"
