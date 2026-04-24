import json
import urllib.request

packages = [
    "fastapi", "uvicorn", "langchain", "langchain-google-vertexai", 
    "google-cloud-aiplatform", "mcp", "google-cloud-bigquery", 
    "google-cloud-secret-manager", "python-dotenv", "python-frontmatter"
]

for pkg in packages:
    try:
        url = f"https://pypi.org/pypi/{pkg}/json"
        req = urllib.request.urlopen(url)
        data = json.loads(req.read())
        print(f"{pkg}=={data['info']['version']}")
    except Exception as e:
        print(f"Error for {pkg}: {e}")
