import argparse
import json
import os
import sys
from pathlib import Path
import importlib
from dotenv import load_dotenv

load_dotenv()

# Dodajemy katalog bieżący, by ułatwić importy narzędzi z folderu tools/
sys.path.append(os.path.dirname(__file__))

def discover_tools():
    """
    Skanuje katalog tools/ i automatycznie przygotowuje listę definicji narzędzi.
    Dzięki temu implementujemy lekcyjne S01E02: "Tool Discovery" i "Progressive Disclosure".
    """
    
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

    tools_list = []
    
    # Katalog z narzędziami
    tools_path = Path(__file__).parent / "tools"
    
    # Skanujemy folder w poszukiwaniu plików .py
    for file_path in tools_path.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
            
        # Tworzymy nazwę modułu (np. tools.get_person_locations)
        module_name = f"tools.{file_path.stem}"
        
        try:
            # Dynamicznie importujemy moduł
            module = importlib.import_module(module_name)
            
            # Pobieramy funkcję o tej samej nazwie co plik (stem)
            tool_func = getattr(module, file_path.stem)
            
            if callable(tool_func):
                tools_list.append(tool_func)
                print(f"[Discovery] Załadowano narzędzie: {file_path.stem}")
        except (ImportError, AttributeError) as e:
            print(f"[Discovery] Błąd ładowania {file_path.name}: {e}")
    
    if not tools_list:
        print("\n[WARNING] Nie znaleziono żadnych narzędzi w folderze tools/!")
    
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
    import requests
    AIDEVS_API_KEY = os.getenv("AIDEVS_API_KEY")

    if args.backend == "genai":
        from llm_genai import run_agent_genai
        final_data = run_agent_genai(people, tools)
        
        if final_data and final_data.get("status") == "FINAL_ANSWER_SAVED_TO_DISK":
            print("\n=======================================================")
            print(f"[Orchestrator] Odebrano sygnał ukończenia Agenta! Ładuję payload z dysku...")
            
            # Wczytujemy plik
            file_path = final_data.get("file_path")
            with open(file_path, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
                
            # Wzorzec asynchronicznej walidacji - Pydantic chroni nas przed halucynacją w payloadzie
            from pydantic import BaseModel, Field
            class AnswerSchema(BaseModel):
                name: str
                surname: str
                accessLevel: int
                powerPlant: str
                
            try:
                # Jeśli model podał '7' jako string, Pydantic sam to zrzutuje na int
                validated_answer = AnswerSchema(**raw_json)
                print(f"[Orchestrator] Schema zweryfikowany lokalnie (Pydantic: OK). Wysyłam wniosek do Centrali (/verify)...")
            except Exception as e:
                print(f"[Orchestrator] BŁĄD WALIDACJI DANYCH OD LLM! Przerwano próbę wysyłki: {e}")
                return
            
            url = "https://hub.ag3nts.org/verify"
            payload = {
                "apikey": AIDEVS_API_KEY,
                "task": "findhim",
                "answer": validated_answer.model_dump()
            }
            try:
                resp = requests.post(url, json=payload)
                print(f"[{resp.status_code}] Odpowiedź serwera: {resp.text}")
                
                # Zapisujemy potwierdzenie do pliku kaskadowego
                verify_path = Path(file_path).parent / "result_verify.json"
                
                try:
                    server_json = resp.json()
                except Exception:
                    server_json = {"raw_text": resp.text}
                    
                with open(verify_path, "w", encoding="utf-8") as f:
                    json.dump(server_json, f, indent=4)
                    
                print(f"[Orchestrator] Odpowiedź serwera zapisana w: {verify_path}")
            except Exception as e:
                print(f"Błąd wysyłania: {e}")
            print("=======================================================\n")
    else:
        from llm_langchain import run_agent_langchain
        run_agent_langchain(people, tools)

if __name__ == "__main__":
    main()
