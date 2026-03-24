import argparse
import json
import os
import sys
from pathlib import Path

# Dodajemy katalog bieżący, by ułatwić importy narzędzi z folderu tools/
sys.path.append(os.path.dirname(__file__))

def discover_tools():
    """
    Skanuje katalog tools/ i automatycznie przygotowuje listę definicji narzędzi.
    Dzięki temu implementujemy lekcyjne S01E02: "Tool Discovery" i "Progressive Disclosure".
    """
    tools_list = []
    
    # -----------------------------------------------------------------------
    # TODO dla Artura: Zaimplementuj Tool Discovery!
    # Poniżej znajduje się Twoje zadanie. Przeskanuj folder `tools/`, załaduj funkcje
    # z plików .py (np. przy użyciu wbudowanego `importlib` albo zrób prosty import ręcznie wgłąb).
    # To ta lista połączy modele LLM z logiką aplikacji (Function Calling).
    #
    # Wskazówka ułatwiająca start z ręki:
    # from tools.get_person_locations import get_person_locations
    # from tools.find_closest_plant import find_closest_plant
    # from tools.get_access_level import get_access_level
    # tools_list = [get_person_locations, find_closest_plant, get_access_level]
    # -----------------------------------------------------------------------
    print("\n[TODO] Narzędzia nie zostały uaktywnione! Zaktualizuj sekcję discover_tools() w main.py!")
    
    return tools_list

def main():
    parser = argparse.ArgumentParser(description="Zadanie findhim - System Agentowy w stylu S01E01")
    parser.add_argument("--backend", choices=["genai", "langchain"], default="genai", help="Wybór frameworka do użycia w operacji operacyjnej (domyślnie google-genai)")
    args = parser.parse_args()

    # Wczytanie wytypowanych przez nas osób (z poprzedniego repo i zadania S01E01)
    base_dir = Path(__file__).parent.parent.parent
    path_to_people = base_dir / "S01E01-programowanie-interakcji-z-modelem-jezykowym" / "tasks" / "result_submit.json"
    
    if not path_to_people.exists():
        print(f"Błąd krytyczny: Skrypt nie widzi pliku {path_to_people}. Upewnij się, że projekt S01E01 został ukończony.")
        return

    with open(path_to_people, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    people = data.get("answer", [])
    if not people:
        print("Błąd - plik z wynikami S01E01 jest pusty.")
        return

    print(f"Uruchamiam serwer-agenta w trybie na architekturze: {args.backend}")
    print(f"Ilość podejrzanych do zweryfikowania (lista z transportu): {len(people)}")

    tools = discover_tools()

    if args.backend == "genai":
        from llm_genai import run_agent_genai
        run_agent_genai(people, tools)
    else:
        from llm_langchain import run_agent_langchain
        run_agent_langchain(people, tools)

if __name__ == "__main__":
    main()
