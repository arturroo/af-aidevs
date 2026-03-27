import os
from dotenv import load_dotenv

# Zgodnie z poleceniem, używamy wyłącznie integracji Google Cloud Vertex AI
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

load_dotenv()

async def run_agent_langchain(people, tools_list):
    """
    Funkcja demonstrująca "State of the Art" w obsłudze agentów w ekosystemie LangChain (LangGraph).
    Pozbywamy się jakiejkolwiek ręcznej pętli czy nasłuchiwania - LangGraph robi wszystko pod spodem.
    """
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "your_gcp_project_here"
    LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "europe-west6"

    # Używamy pełnoprawnego Vertex AI
    llm = ChatVertexAI(
        model_name="gemini-3.1-flash-lite-preview",
        project=PROJECT_ID,
        location=LOCATION,
        temperature=0
    )
    
    system_message = open("prompts/system_message.md").read()

    suspects_text = "\n".join([f"- {p['name']} {p['surname']}. Rok urodzenia: {p['born']}" for p in people])
    user_message = f"Lista podejrzanych wytypowanych przez system:\n{suspects_text}"
    
    # 1. Konwersja czystych funkcji Pythona na narzędzia LangChain.
    # Używamy prostego dekoratora tool.
    lc_tools = [tool(f) for f in tools_list]
    
    # 2. Magia LangGraph prebuilt: create_react_agent generuje skompilowany graf (StateGraph),
    # który sam potrafi: wywołać LLM -> zdekodować Tool Call -> odpalić Tool -> zwrócić ToolMessage -> ponowić zapytanie.
    agent = create_react_agent(llm, tools=lc_tools, prompt=system_message)
    
    print("\n[LangGraph] Uruchamiam zautomatyzowaną pętlę agenta (invoke)...")
    
    inputs = {"messages": [HumanMessage(content=user_message)]}
    
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    
    try:
        # Odpalamy agenta asynchronicznie (ainvoke)
        response = await agent.ainvoke(inputs, config={"recursion_limit": 50})
        
        print("\n" + "="*50)
        print("[LangGraph] HISTORIA KOMUNIKACJI (Co LLM dostał i co odpowiedział):")
        print("="*50)
        
        for msg in response['messages']:
            msg_type = type(msg).__name__
            if msg_type == "HumanMessage":
                print(f"\n👨‍💻 [USER / SYSTEM]:\n{msg.content[:300]}...\n")
            elif msg_type == "AIMessage":
                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        args = tc.get('args', {})
                        reasoning = args.get('reasoning', 'Brak wyjaśnienia (brak pola w tool call)')
                        print(f"🤖 [LLM MYŚLI - CHCE AKCJI] Wywołuje narzędzie: {tc['name']}")
                        print(f"       Zostało powiedziane: '{reasoning}'")
                        print(f"       Aktywowane z argumentami: {args}")
                if msg.content:
                    print(f"🤖 [LLM MÓWI]: {msg.content}")
            elif msg_type == "ToolMessage":
                print(f"🛠️ [WYNIK NARZĘDZIA '{msg.name}']: {msg.content[:200]}...")
        
        print("\n" + "="*50)

        # print("\n--- RAW LLM INPUT ---")
        # print(inputs)
        # 
        # print("\n--- RAW LLM OUTPUT (FULL STATE) ---")
        # print(response)

        print("\n[LangGraph] Agent zakończył globalne myślenie!")
        print(f"[Końcowa odpowiedź LLM] {response['messages'][-1].content}")
                 
    except Exception as e:
        print(f"[LangChain] Błąd podczas działania agenta: {e}")
        
    # Wczytujemy finalny plik zgłoszeniowy by program gładko przeszedł w main.py
    from pathlib import Path
    submit_file = Path(__file__).parent / "data" / "result_submit_langchain.json"
    if submit_file.exists():
        return {
            "status": "FINAL_ANSWER_SAVED_TO_DISK",
            "file_path": str(submit_file)
        }
    return None
