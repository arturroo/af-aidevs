import argparse
import sys
import os
from fastapi import FastAPI
from pydantic import BaseModel

# Map custom LANGSMITH_API_KEY to standard LANGCHAIN_API_KEY
if "LANGSMITH_API_KEY" in os.environ:
    os.environ["LANGCHAIN_API_KEY"] = os.environ["LANGSMITH_API_KEY"]

app = FastAPI()

# Global dict for memory keeping
sessions = {}

class MessageReq(BaseModel):
    sessionID: str
    msg: str

class MessageRes(BaseModel):
    msg: str

# Global backend module reference
backend_module = None

def get_backend():
    """Returns the selected backend module (langchain or adk)."""
    global backend_module
    if backend_module is None:
        import os
        # Read from environment variable, default to langchain
        backend_name = os.getenv("BACKEND") or "langchain"
        if backend_name == "adk":
            import agent_adk
            backend_module = agent_adk
        else:
            import agent_langchain
            backend_module = agent_langchain
    return backend_module

@app.post("/", response_model=MessageRes)
async def chat_endpoint(req: MessageReq):
    backend = get_backend()
    if req.sessionID not in sessions:
        sessions[req.sessionID] = backend.create_session(req.sessionID)
        
    session_data = sessions[req.sessionID]
    response_msg = await backend.process_message(session_data, req.msg)
    
    return {"msg": response_msg}


if __name__ == "__main__":
    import os
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["langchain", "adk"], default=os.getenv("BACKEND") or "langchain", help="Framework (domyślnie langchain)")
    args = parser.parse_args()

    # Set environment variable so get_backend() picks it up
    os.environ["BACKEND"] = args.backend
    
    uvicorn.run(app, host="0.0.0.0", port=8080)

