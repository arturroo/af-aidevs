import os
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from dotenv import load_dotenv

load_dotenv()

def run_agent_langchain(people, tools_list):
    """
    Funkcja testująca jak poradzi sobie Langchain (bind_tools lub pełnoprawny Agent)
    """
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "your_gcp_project_here"
    LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6"
    
    # Inicjacja po staremu, ale korzystająca najpewniej z Langchaina
    llm = ChatVertexAI(
        model_name="gemini-2.5-flash", 
        project=PROJECT_ID, 
        location=LOCATION
    )
    
    system_instruction = (
        "Jesteś potężnym agentem śledczym wykonanym we frameworku LangChain. \n"
        "Twoim zadaniem jest ustalić, czy dana osoba przebywała blisko polskiej elektrowni.\n"
        "Masz serię unikalnych narzędzi z izolowanym IO podanych Ci przy wywołaniu. \n"
        "Gdy upewnisz się czy osoba była blisko, pobierz dla niej z API accessLevel i zwróć w pożądanym formacie JSON: {'name': '...', 'surname': '...', 'accessLevel': ..., 'powerPlant': '...'}"
    )
    
    # -----------------------------------------------------------------------
    # TODO dla Artura: Konfiguracja Agent-a za pomocą LangChain!
    # Narzędzia z Pythona idealnie potrafią zgrywać się w LangChainie (przy pomocy pydantica czy docstringów).
    # 1. Zbuduj instancję agenta z wpiętymi narzędziami:
    #    agent = llm.bind_tools(tools_list)
    # 2. Utwórz listę logów `messages = [SystemMessage(content=system_instruction), HumanMessage(content="...")]`
    # 3. Zaczyna się pętla. Odpytaj `response = agent.invoke(messages)`. Dołóż to na listę messages.
    # 4. Sprawdź `if response.tool_calls:`. Jeśli prawda - Langchain fajnie to parsuje z JSONa funkcyjnego na dict pod ".tool_calls".
    #    Dla każdej funkcji w iteracji można ją odpalić od razu podając słownik argumentów jako listę kwargs (**args_dict).
    #    Należy wynik zawinąć w `ToolMessage(content=wynik_python, tool_call_id=tutaj_podaj_oryginalne_id)` i dodać do history list messages!
    # Alternatywnie dla ambitnych: Przenieś ten model do `create_react_agent` bazującym na module `langgraph.prebuilt` by wykonać całą mechanikę w dwóch małych linijkach ukrywając pętlę while!
    # -----------------------------------------------------------------------
    
    for person in people:
        print(f"\n[LangChain] Detektyw sprawdza profil: {person['name']} {person['surname']} (ur. {person['born']})")
        
        print("[TODO] Architektura pętli wykonawczej (ReAct Loop) dla LangChain uśpiona i czeka na implementację w llm_langchain.py!")
        break # Czekamy na Artura
