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
    
    suspects_text = "\n".join([f"- {p['name']} {p['surname']}. Rok urodzenia: {p['born']}" for p in people])
    user_message = f"Oto lista podejrzanych wytypowanych przez system. Zbadaj ich wszystkich po kolei pobierając ich lokacje i sprawdzając kto był absolutnie najbliżej dowolnej elektrowni. Kiedy znajdziesz osobę, dla której ten dystans jest GLOBLANIE najmniejszy, pobierz jej poziom dostępu i wyślij finalny raport poprzez funkcję submit_investigation_result:\n{suspects_text}"
    
    from langchain.agents import create_tool_calling_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.tools import tool
    
    # Konwersja czystych funkcji Pythona na narzędzia rozumiene przez Langchain
    lc_tools = [tool(f) for f in tools_list]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_instruction),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    
    # Tworzymy agenta
    agent = create_tool_calling_agent(llm, lc_tools, prompt)
    
    # Tworzymy pętlę wykonawczą (Orchestrator Langchainowy)
    agent_executor = AgentExecutor(agent=agent, tools=lc_tools, verbose=True, max_iterations=30)
    
    print("\n[LangChain] Agent rozpoczyna globalne badanie przy użyciu AgentExecutor ReAct...")
    
    try:
        agent_executor.invoke({"input": user_message})
    except Exception as e:
        print(f"[LangChain] Błąd podczas działania agenta: {e}")
        
    # Wczytujemy finalny plik, by zwrócić sygnał do głównego pętli main.py (identycznie jak w genai)
    from pathlib import Path
    submit_file = Path(__file__).parent / "data" / "result_submit.json"
    if submit_file.exists():
        return {
            "status": "FINAL_ANSWER_SAVED_TO_DISK",
            "file_path": str(submit_file)
        }
    return None
