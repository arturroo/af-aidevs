# /// script
# dependencies = [
#   "httpx",
#   "python-dotenv",
# ]
# ///

import os
import asyncio
import json
import httpx
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Constants from environment
AIDEVS_DANE_DOC = os.getenv("AIDEVS_DANE_DOC")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

class Scraper:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.downloaded = set()
        os.makedirs(DATA_DIR, exist_ok=True)

    async def download_file(self, filename: str, headers: Optional[Dict] = None) -> str:
        """Downloads a file and its response headers to the local data directory."""
        if filename in self.downloaded:
            return ""
        
        url = f"{self.base_url}/{filename}"
        local_path = os.path.join(DATA_DIR, filename)
        headers_path = f"{local_path}.headers.json"
        
        print(f"Attempting to download: {url}")
        
        headers = headers or {}
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        async with httpx.AsyncClient(timeout=30.0, http2=False) as client:
            try:
                response = await client.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()
                
                # Save headers
                with open(headers_path, "w", encoding="utf-8") as f:
                    json.dump(dict(response.headers), f, indent=4)
                
                # Save content
                with open(local_path, "wb") as f:
                    f.write(response.content)
                
                self.downloaded.add(filename)
                
                content = ""
                if not filename.endswith((".png", ".jpg", ".jpeg")):
                    content = response.text
                
                return content
            except Exception as e:
                print(f"ERROR downloading {filename}: {type(e).__name__}: {str(e)}")
                return ""

    def find_links(self, content: str) -> List[str]:
        """Finds potential file links in markdown content."""
        # Match [text](filename) or [include file="filename"]
        links = re.findall(r'\[.*?\]\((.*?)\)', content)
        includes = re.findall(r'\[include file="(.*?)"\]', content)
        
        # Filter for local files (not full URLs)
        all_links = links + includes
        valid_links = []
        for link in all_links:
            if not link.startswith("http") and "." in link:
                valid_links.append(link)
        return list(set(valid_links))

async def main():
    if not AIDEVS_DANE_DOC:
        print("Error: AIDEVS_DANE_DOC not set in .env")
        return

    scraper = Scraper(AIDEVS_DANE_DOC)
    
    # Start with index.md and recently discovered poziomy.md
    queue = ["index.md", "poziomy.md"]
    processed = set()
    
    while queue:
        current = queue.pop(0)
        if current in processed:
            continue
        
        content = await scraper.download_file(current)
        processed.add(current)
        
        if content:
            new_links = scraper.find_links(content)
            for link in new_links:
                if link not in processed:
                    queue.append(link)

    print(f"\nScraping finished. Total files downloaded: {len(processed)}")
    print(f"Check the '{DATA_DIR}' directory for files and .headers.json files.")

if __name__ == "__main__":
    asyncio.run(main())
