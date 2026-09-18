# cr-s04e01-okoeditor

Cloud Run microservice for S04E01 `okoeditor` covert surveillance record manipulation.

## Local Execution

```powershell
# Run with LangChain backend
uv run python main.py --backend langchain

# Run with Google ADK backend
uv run python main.py --backend adk

# Run tests
uv run pytest -v
```
