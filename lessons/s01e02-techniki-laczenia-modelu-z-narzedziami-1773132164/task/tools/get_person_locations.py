import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def _make_api_request(url, payload):
    print(f"\n[get_person_locations] API request to {url}")
    response = requests.post(url, json=payload)
    print(f"[get_person_locations] API Response Status: {response.status_code}")
    if response.status_code != 200:
        print(f"[get_person_locations] API Error Text: {response.text}")
    response.raise_for_status()
    return response.json()
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")

def get_person_locations(name: str, surname: str) -> str:
    """
    Pobiera historię lokalizacji (współrzędne) podejrzanej osoby i zapisuje je w bezpiecznym sandboxie (pliku JSON).
    Zwraca agentowi id stworzonego pliku bez wyjawiania fizycznych ścieżek na dysku.
    """
    # Sandboxing - narzucamy stałe miejsce przechowywania
    base_dir = Path(__file__).parent.parent.absolute()
    sandbox_dir = base_dir / "data" / "get_person_locations"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    file_id = f"loc_{name}_{surname}"
    file_path = sandbox_dir / f"{file_id}.json"
    
    # 1. Caching: Sprawdzamy, czy plik już istnieje
    if file_path.exists():
        print(f"[get_person_locations] Plik {file_id}.json już istnieje. Używam cache.")
        return f"Sukces. Pomyślnie pobrano 10 punktów (współrzędnych) lokacji, w których poruszała się ta osoba. Zostały one przez nas przechwycone i zrzucone na twój system plików. Od tej pory możesz operować nimi odwołując się do identyfikatora pliku: '{file_id}'."

    url = "https://***REMOVED***"
    payload = {
        "apikey": AIDEVS_API_KEY,
        "name": name,
        "surname": surname
    }
    
    # 2. Jeśli nie ma pliku, pobieramy z API używając tenacity
    try:
        data = _make_api_request(url, payload)
    except Exception as e:
        return f"Błąd pobierania danych z API (przekroczono liczbę prób): {e}"
    

    
    # Zapis
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    return f"Sukces. Pomyślnie pobrano 10 punktów (współrzędnych) lokacji, w których poruszała się ta osoba. Zostały one przez nas przechwycone i zrzucone na twój system plików. Od tej pory możesz operować nimi odwołując się do identyfikatora pliku: '{file_id}'."
