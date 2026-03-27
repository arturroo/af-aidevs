import os
import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def _make_api_request(url, payload):
    response = requests.post(url, json=payload)
    print(f"[get_access_level] API Response {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.text

def get_access_level(name: str, surname: str, birthYear: int) -> str:
    """
    Pobiera z serwera poziom dostępu (accessLevel) osoby o podanych danych.
    Wymagane jest dokładne imię, nazwisko i poprawny rok urodzenia (jako liczba całkowita).
    Zwraca JSON z wynikiem od serwera (tekstem bez parsowania, do oczytania przez LLM).
    """
    url = "https://***REMOVED***"
    payload = {
        "apikey": AIDEVS_API_KEY,
        "name": name,
        "surname": surname,
        "birthYear": int(birthYear)
    }
    
    try:
        return _make_api_request(url, payload)
    except Exception as e:
        return f"Błąd pobierania dostępu z API (przekroczono liczbę prób): {e}"
