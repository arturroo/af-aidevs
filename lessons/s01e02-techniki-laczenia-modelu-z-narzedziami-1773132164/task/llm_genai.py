import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def run_agent_genai(people, tools_list):
    """
    Funkcja zarządzająca badaniami agenta bazującego całkowicie na silnikach natywnego Google GenAI SDK.
    """
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "your_gcp_project_here"
    LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6"
    
    # Inicjalizacja stabilnego klienta na cloudzie
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    
    for person in people:
        print(f"\n[SDK] Detektyw bierze pod lupę osobę: {person['name']} {person['surname']} (ur. {person['born']})")
        
        system_instruction = (
            "Jesteś potężnym agentem śledczym. Szukamy osoby, która przebywała nieopodal jednej z tajnych elektrowni.\n"
            "Do dyspozycji masz zaawansowane narzędzia wczytane z Tool Discovery (Sandbox I/O).\n"
            "Wykonuj po kolei akcje (krok po kroku):\n"
            "1. Pobierz lokacje osoby by przechwycić je do tajnego sandboxa archiwum na dysku.\n"
            "2. Sprawdź i poproś by maszyna kalkulacyjna zliczyła, jaka elektrownia znajduje się blisko.\n"
            "3. Sprawdź accessLevel wytypowanego, jeśli okaże się on powiązany z punktem.\n"
            "Gdy będziesz absolutnie pewny faktu odnalezienia winnego i zgromadzenia o nim wiedzy, odpowiedz obiektem JSON {name, surname, accessLevel, powerPlant}."
        )
        
        # Inicjalne okno rozmowy od samego usera - do dopchnięcia historycznie
        messages = [
            types.Content(role="user", parts=[
                types.Part.from_text(f"Zbadaj podejrzanego: {person['name']} {person['surname']}. Rok urodzenia: {person['born']}")
            ])
        ]
        
        # -----------------------------------------------------------------------
        # TODO dla Artura: Zaimplementuj Agent Loop (pętlę) dla GenAI SDK!
        # Upewnij się, jak obsługuje się tu tzw. Function Calling.
        # Flow wygląda zwykle następująco:
        # Pętla `while True:`
        #   Wywołaj: response = client.models.generate_content(
        #          model='gemini-2.5-flash', 
        #          contents=messages, 
        #          config=types.GenerateContentConfig(tools=tools_list, system_instruction=system_instruction) # Przekazanie tools!
        #   )
        #   Dodaj zapisaną w 'response.candidates[0].content' odpowiedź z powrotem do listy `messages` (aby zachować stały log historii).
        #   Jeżeli model wywołał narzędzie (`if response.function_calls:`):
        #       Uruchom Twoją pythonową funkcję samemu, podając argumenty. 
        #       Skonstruuj fizyczny element typu `types.Part.from_function_response` mówiący "rolą: tool" jaka wyszła wartość z Pythona.
        #       Dołóż go do 'messages'.
        #   W przeciwnym wypadku (`else`): nie ma calli, znaczy że LLM skończył rezonować i podał zwykły text - zrób 'break' !
        # -----------------------------------------------------------------------
        print("[TODO] Manualna pętla operacyjna (Function Calling Loop) dla google-genai czeka na rozpisanie w pliku llm_genai.py!")
        break # Uciekamy, dopóki TODO nie jest napisane, by uniknąć wyrzucania exceptionów.
