import os
from google import genai
from google.genai import types

system_message = open("prompts/system_message.md").read()

def _print_response_metadata(response):
    if response.text:
        print("RESPONSE TEXT:")
        print(response.text)
    
    if response.candidates[0].content.parts:
        print("RESPONSE PARTS (RAW):")
        part_nr = 0
        for part in response.candidates[0].content.parts:
            part_nr += 1
            # Zamiast part.text, drukujemy cały obiekt 'part' by zobaczyć function_call!
            print(f"part {part_nr}: {part}")

    if response.usage_metadata:
        print(f"RESPONSE USAGE_METADATA TOKENS(prompt | output | total): {response.usage_metadata.prompt_token_count} | {response.usage_metadata.candidates_token_count} | {response.usage_metadata.total_token_count}")

    # print("RESPONSE PROMPT_FEEDBACK:")
    # print(response.prompt_feedback)

def run_agent_genai(people, tools_list):
    """
    Funkcja zarządzająca badaniami agenta bazującego całkowicie na silnikach natywnego Google GenAI SDK.
    """
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "your_gcp_project_here"
    LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6"
    
    # Inicjalizacja stabilnego klienta na cloudzie
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    # KONFIGURACJA: Na etapie myślenia/działania NIE narzucamy JSON Schema,              system_instruction=system_message,
    response_config = types.GenerateContentConfig(
        system_instruction=system_message,
        temperature=0,
        top_p=0.1,
        max_output_tokens=8192,
        # AF not needed as we will force model to respond by calling a special tool when it is sure.
        # and it will take the schema from the tool definition.
        # response_mime_type="application/json",
        # response_schema=InvestigationResult,
        tools=tools_list,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
    )
    # print("RAW TOOL SCHEMA SENT TO LLM:")
    # print(response_config.tools)
    
    suspects_text = "\n".join([f"- {p['name']} {p['surname']}. Rok urodzenia: {p['born']}" for p in people])
    user_message = f"Lista podejrzanych wytypowanych przez system:\n{suspects_text}"
    
    messages = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_message)
            ])
    ]
        # print("MESSAGES INITIAL:", messages)

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
    # Zwiększamy ilość kroków na 30, bo ma aż 5 osób do zbadania (5x location, 5x plant, itd.)
    for _ in range(30):
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=messages,
            config=response_config
        )

        response_content = response.candidates[0].content
        messages.append(response_content)
        print("MESSAGES AFTER RESPONSE:", messages)
        _print_response_metadata(response)

        if response.function_calls:
            tool_parts = []
            for call in response.function_calls:
                print(f"{call.name} - Model chce odpalić funkcję z argumentami: {call.args}")
                tool_func = next((f for f in tools_list if f.__name__ == call.name), None)
                if tool_func:
                    print(f"{tool_func.__name__} znaleziona, odpalam...")
                    result = tool_func(**call.args)
                    print(f"{tool_func.__name__}({call.args}) -> {result}")
                    # --- WYZNACZANIE GLOBALNEGO PODMIOTU DLA TEGO KROKU ---
                    if "name" in call.args and "surname" in call.args:
                        osoba = f"{call.args['name']} {call.args['surname']}"
                    elif "file_id" in call.args:
                        # W przypadku find_closest_plant wyciągamy imię z nazwy pliku loc_Imie_Nazwisko
                        osoba = call.args["file_id"].replace("loc_", "").replace("_", " ")
                    else:
                        osoba = "Nieznany obiekt"
                    
                    # ---------------------------------------------------------------------------------------------------------
                    # [BEST PRACTICE Z PRODUKCJI - CONTEXT THREADING / TRACEABILITY]
                    # UWAGA DLA ARTURA: W zadaniu AI_Devs S01E02 to podejście nie jest w 100% wymagane, ponieważ nasze 
                    # narzędzia korzystają wprost z pól "name" / "surname", lub "loc_Cezary_Zurek", więc model sam się domyśli.
                    #
                    # JEDNAK na produkcji w systemach dużej skali, gdy narzędzia korzystają z niezrozumiałych 
                    # identyfikatorów relacyjnych (np. pobierz_dane_podatkowe(id_uzytkownika=59382)), 
                    # asynchroniczne lub wieloetapowe odpowiedzi kompletnie zacierają kontekst dla modelu ("Do kogo należało to 59382?").
                    # 
                    # Model zaczyna wtedy marnować tokeny na cofanie się w potężnej historii konwersacji, żeby dopasować ID do osoby.
                    # Ratuje nas wtedy narzucenie "Ludzko-Czytelnego Kontekstu Globalnego" bezpośrednio od strony warstwy Orchestratora.
                    # My, jako Orchestrator (kod w Pythonie, na zewnątrz LLMa), doskonale wiemy dla KOGO dany tool był aktualnie 
                    # odpalany, więc wstrzykujemy to imię NA SZYWNO do stringa z odpowiedzią z narzędzia (co gwarantuje tzw. Grounding).
                    # ---------------------------------------------------------------------------------------------------------
                    
                    # 1. Doklejamy ugruntowanie PODMIOTU (Subject Context Threading)
                    grounding_subject = f"[Śledztwo: {osoba}]"

                    # 2. Doklejamy ugruntowanie ARGUMENTÓW (Argument Context Grounding), aby uciąć wszelkie szanse na pomyłkę Async
                    grounding_arguments = f"Odpowiedź dla argumentów {call.args}:"

                    # 3. Złączenie w jedną kuloodporną na milisekundy Asynchroniczności (idempotentną) odpowiedź
                    grounded_result = f"{grounding_subject} {grounding_arguments} {result}"

                    
                    tool_parts.append(
                        types.Part.from_function_response(
                            name=call.name,
                            response={"result": grounded_result}
                        )
                    )
                    if tool_func.__name__ == "submit_investigation_result":
                        print(f"  [BINGO] Mamy winnego! Wynik: {result}")
                        return result
                else:
                    print(f"{call.name} - Error - Narzędzie nie zostało znalezione!")
            
            if tool_parts:
                messages.append(types.Content(
                    role="tool",
                    parts=tool_parts
                ))
            continue
        else:
            # Brak wywołań funkcji - model spróbował odpowiedzieć samym tekstem!
            print(f"  [UWAGA] Model odpowiedział tekstem zamiast użyć narzędzia. Wysyłam reprymendę.")
            correction = "Niedozwolone zachowanie. Złamałeś zasady (Constraints). Nie wolno ci odpowiadać tekstem. Jeśli skończyłeś śledztwo, UŻYJ NARZĘDZIA `submit_investigation_result` z wynikami. Jeśli nie skończyłeś, użyj innego odpowiedniego narzędzia."
            messages.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=correction)]
            ))
    
    print("  [ERROR] Agent przekroczył limit 30 iteracji i zablokował się.")
    return None
