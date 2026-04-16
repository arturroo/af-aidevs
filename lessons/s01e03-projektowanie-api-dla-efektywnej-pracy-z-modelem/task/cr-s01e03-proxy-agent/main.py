import argparse
import sys
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Global dict for memory keeping
sessions = {}

class MessageReq(BaseModel):
    sessionID: str
    msg: str

class MessageRes(BaseModel):
    msg: str

# To switch between adk and langchain depending on the launch arguments
backend_module = None

def get_backend():
    global backend_module
    if backend_module is None:
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["langchain", "adk"], default="langchain", help="Framework (domyślnie langchain)")
    args = parser.parse_args()

    if args.backend == "adk":
        import agent_adk
        backend_module = agent_adk
    else:
        import agent_langchain
        backend_module = agent_langchain

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
else:
    # If starting via uvicorn directly, we can read backend from env
    import os
    backend = os.environ.get("BACKEND", "langchain")
    if backend == "adk":
        import agent_adk
        backend_module = agent_adk
    else:
        import agent_langchain
        backend_module = agent_langchain
