# S03E05 Savethem Autonomous Routing Microservice (`cr-s03e05-savethem`)

This service solves task `savethem` (S03E05) using an autonomous meta-agent that discovers external tools via `$AIDEVS_API_TOOLSEARCH`, pulls terrain topology and vehicle physics, executes Multi-State A* pathfinding on a 10x10 grid within a 10-food and 10-fuel budget, and submits the itinerary to `$AIDEVS_API_VERIFY`.

## Execution

### Direct CLI Mode
```powershell
uv run python main.py --backend langchain
uv run python main.py --backend adk
```

### Local FastAPI Server
```powershell
uv run uvicorn main:app --port 8080
```
