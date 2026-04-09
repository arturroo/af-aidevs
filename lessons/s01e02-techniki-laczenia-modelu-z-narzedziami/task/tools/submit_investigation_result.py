import json
from pathlib import Path

def submit_investigation_result(name: str, surname: str, access_level: int, power_plant: str, reasoning: str) -> dict:
    """
    Wywołaj to narzędzie TYLKO po przeprowadzeniu śledztwa za pomocą pozostałych narzędzi, gdy jesteś absolutnie pewien wszystkich faktów.
    Zwraca ostateczny wynik w ustalonym schemacie dla głównej pętli aplikacji.

    Args:
        name: Imię podejrzanego (np. Jan).
        surname: Nazwisko wytypowanej osoby (np. Kowalski).
        access_level: Zebrany poziom dostępu / ranga z systemu bazodanowego elektrowni.
        power_plant: Kod elektrowni wokół której osoba przebywała, np. PWR1234PL.
        reasoning: Dokładne uzasadnienie agenta podsumowujące dlaczego to ta osoba została wybrana (np. "Osoba przebywała 0.5km od elektrowni, więc...").
    """
    
    result = {
        "name": name,
        "surname": surname,
        "accessLevel": access_level,
        "powerPlant": power_plant
    }
    
    # -------------------------------------------------------------------------------------------------
    # [BEST PRACTICE Z PRODUKCJI - STATE DECOUPLING]
    # Zamiast zawracać zmienną przez RAM prosto do Orkiestratora, zapisujemy ją na twardo.
    # Uodparnia to system na pady sieci i pozwala innym mikroserwisom przetwarzać zrzucony plik.
    # -------------------------------------------------------------------------------------------------
    base_dir = Path(__file__).parent.parent.absolute()
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Konwencja nazewnicza: stage_N_nazwa_akcji.json
    file_path = data_dir / "result_submit.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4)
        
    # ---------------------------------------------------------------------------------------------------------
    # [BEST PRACTICE Z PRODUKCJI - CONTEXT THREADING / TRACEABILITY]
    # Nawet po zapisaniu na dysk, powiadamiamy LLMa o sukcesie wskazując dokładnie, 
    # czyje akta zostały właśnie bezpiecznie odłożone do archiwum.
    # ---------------------------------------------------------------------------------------------------------
    return {
        "status": "FINAL_ANSWER_SAVED_TO_DISK",
        "file_path": str(file_path),
        "trace": f"[Śledztwo: {name} {surname}] Śledztwo zakończone i dane zapisane."
    }
