"""Centrala API client for task filesystem."""

import logging
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from schemas import FilesystemFile

logger = logging.getLogger("services.centrala")


class CentralaService:
    """Client for Centrala /verify/ endpoint with batch_mode and retry support."""

    def __init__(
        self,
        verify_url: str = config.AIDEVS_VERIFY_URL,
        api_key: str = config.AIDEVS_API_KEY,
        task_name: str = config.TASK_NAME,
    ):
        self.verify_url = verify_url
        self.api_key = api_key
        self.task_name = task_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def _post_verify(
        self, answer: dict[str, Any] | list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Dispatches an answer payload to Centrala /verify/."""
        payload = {
            "apikey": self.api_key,
            "task": self.task_name,
            "answer": answer,
        }
        logger.info(
            f"POST {self.verify_url} (task={self.task_name}, payload_type={type(answer).__name__})"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.verify_url, json=payload)
            try:
                data = resp.json()
            except Exception:
                data = {"code": resp.status_code, "message": resp.text}

            if resp.status_code >= 400:
                logger.warning(f"Centrala error response ({resp.status_code}): {data}")
                return data

            logger.info(f"Centrala response: {data}")
            return data

    async def get_help(self) -> dict[str, Any]:
        """Calls action: 'help' to discover available commands and specs."""
        return await self._post_verify({"action": "help"})

    async def reset(self) -> dict[str, Any]:
        """Calls action: 'reset' to completely wipe the virtual filesystem."""
        return await self._post_verify({"action": "reset"})

    async def list_files(self, path: str = "/") -> dict[str, Any]:
        """Lists files and directories under the given path."""
        return await self._post_verify({"action": "listFiles", "path": path})

    async def create_directory(self, path: str) -> dict[str, Any]:
        """Creates a directory in Centrala virtual filesystem."""
        logger.info(f"Creating directory in Centrala: '{path}'")
        return await self._post_verify({"action": "createDirectory", "path": path})

    async def delete_file(self, path: str) -> dict[str, Any]:
        """Deletes a single file from Centrala's virtual filesystem."""
        logger.info(f"Deleting file in Centrala: '{path}'")
        try:
            return await self._post_verify({"action": "deleteFile", "path": path})
        except Exception as e:
            logger.warning(f"Error deleting file '{path}' in Centrala: {e}")
            return {"code": -1, "message": str(e)}

    async def create_file(self, path: str, content: str) -> dict[str, Any]:
        """Creates a single file in Centrala's virtual filesystem.

        If Centrala returns an error indicating that the file already exists,
        it automatically calls deleteFile and retries createFile.
        """
        logger.info(f"Creating file in Centrala: '{path}' ({len(content)} bytes)")
        try:
            res = await self._post_verify(
                {
                    "action": "createFile",
                    "path": path,
                    "content": content,
                }
            )
            code = res.get("code", 0)
            msg = str(res.get("message", "")).lower()
            if code < 0 and ("already exists" in msg or "file exists" in msg):
                logger.info(
                    f"File '{path}' already exists in Centrala. Deleting and recreating..."
                )
                await self.delete_file(path)
                return await self._post_verify(
                    {
                        "action": "createFile",
                        "path": path,
                        "content": content,
                    }
                )
            return res
        except Exception as e:
            logger.error(f"Error creating file '{path}': {e}", exc_info=True)
            return {"code": -1, "message": str(e)}

    async def batch_create_files(self, files: list[FilesystemFile]) -> dict[str, Any]:
        """Ensures directories exist (ignoring -960) and sends all files atomically in batch_mode."""
        # Collect unique parent directories
        dirs_to_create: list[str] = []
        for f in files:
            p = f.path.rsplit("/", 1)[0]
            if p and p not in dirs_to_create:
                dirs_to_create.append(p)

        # Create directories first, gracefully ignoring -960 (Directory already exists)
        for d in dirs_to_create:
            try:
                res = await self.create_directory(d)
                code = res.get("code", 0)
                if (
                    code == -960
                    or "already exists" in str(res.get("message", "")).lower()
                ):
                    logger.info(
                        f"Directory '{d}' already exists in Centrala (ignoring -960)."
                    )
                elif code < 0:
                    logger.warning(f"Centrala directory response for '{d}': {res}")
            except Exception as e:
                logger.warning(f"Error ensuring directory '{d}': {e}")

        # Build batch payload containing exclusively createFile operations
        batch_payload: list[dict[str, Any]] = []
        for idx, f in enumerate(files):
            logger.info(
                f"Batch payload item [{idx + 1}/{len(files)}]: createFile -> '{f.path}' ({len(f.content)} bytes)"
            )
            batch_payload.append(
                {
                    "action": "createFile",
                    "path": f.path,
                    "content": f.content,
                }
            )

        logger.info(f"Uploading {len(files)} files to Centrala in batch_mode")
        res = await self._post_verify(batch_payload)
        code = res.get("code", 0)
        msg = str(res.get("message", "")).lower()
        if code < 0 and ("already exists" in msg or "file exists" in msg):
            logger.info(
                "Batch upload reported file already exists in Centrala. Deleting files and retrying..."
            )
            for f in files:
                await self.delete_file(f.path)
            res = await self._post_verify(batch_payload)
        return res

    async def done(self) -> tuple[dict[str, Any], str | None]:
        """Calls action: 'done' to trigger evaluation and extract flag."""
        data = await self._post_verify({"action": "done"})
        raw_text = str(data)
        flag = None
        match = re.search(r"\{FLG:[^}]+\}", raw_text)
        if match:
            flag = match.group(0)
            logger.info(f"Flag captured: {flag}")
        return data, flag
