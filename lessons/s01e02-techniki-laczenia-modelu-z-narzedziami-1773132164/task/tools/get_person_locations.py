import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")

def get_person_locations(name: str, surname: str) -> str:
    """
    Pobiera historię lokalizacji (współrzędne) podejrzanej osoby i zapisuje je w bezpiecznym sandboxie (pliku JSON).
    Zwraca agentowi id stworzonego pliku bez wyjawiania fizycznych ścieżek na dysku.
    """
    url = "https://hub.ag3nts.org/api/location"
    payload = {
        "apikey": AIDEVS_API_KEY,
        "name": name,
        "surname": surname
    }
    
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        return f"Błąd pobierania danych: {response.text}"
        
    data = response.json()
    
    # Sandboxing - narzucamy stałe miejsce przechowywania
    base_dir = Path(__file__).parent.parent.absolute()
    sandbox_dir = base_dir / "data" / "get_person_locations"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    file_id = f"loc_{name}_{surname}"
    file_path = sandbox_dir / f"{file_id}.json"
    
    # Zapis
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    return f"Sukces. Pomyślnie pobrano 10 punktów (współrzędnych) lokacji, w których poruszała się ta osoba. Zostały one przez nas przechwycone i zrzucone na twój system plików. Od tej pory możesz operować nimi odwołując się do identyfikatora pliku: '{file_id}'."
