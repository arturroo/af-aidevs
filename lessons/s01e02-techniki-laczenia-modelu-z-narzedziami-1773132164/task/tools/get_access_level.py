import os
import requests
from dotenv import load_dotenv

load_dotenv()
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")

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
    
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        return f"Błąd pobierania dostępu z API: {response.text}"
        
    return response.text
