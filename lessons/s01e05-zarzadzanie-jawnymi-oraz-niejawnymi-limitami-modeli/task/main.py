import argparse
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agent_langchain import run_langchain_agent
from agent_adk import run_adk_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("s01e05_task")

BASE_DIR = Path(__file__).resolve().parent

async def main():
    parser = argparse.ArgumentParser(description="Run S01E05 Railway Task Agent")
    parser.add_argument(
        "--backend", 
        choices=["langchain", "genai"], 
        default="langchain", 
        help="Wybór frameworka do użycia w operacji operacyjnej (domyślnie langchain)"
    )
    args = parser.parse_args()
    
    logger.info(f"Starting agent with backend: {args.backend}")
    
    if args.backend == "langchain":
        await run_langchain_agent(BASE_DIR)
    else:
        await run_adk_agent(BASE_DIR)

if __name__ == "__main__":
    asyncio.run(main())
