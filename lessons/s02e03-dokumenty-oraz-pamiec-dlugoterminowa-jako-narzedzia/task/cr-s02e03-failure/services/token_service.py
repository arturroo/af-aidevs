import logging
from typing import Tuple, Optional
import tiktoken
from google import genai
import config

logger = logging.getLogger("services.token")


class TokenService:
    """Service to measure token counts accurately using Vertex AI models with local tiktoken fallback."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.project_id = project_id or config.GOOGLE_CLOUD_PROJECT
        self.location = location or config.GOOGLE_CLOUD_LOCATION
        self.model = model or config.GEMINI_MODEL
        self._genai_client: Optional[genai.Client] = None
        self._tiktoken_enc = tiktoken.get_encoding("cl100k_base")

    @property
    def genai_client(self) -> genai.Client:
        if self._genai_client is None:
            self._genai_client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
            )
        return self._genai_client

    def count_tokens_local(self, text: str) -> int:
        """Computes token count locally via tiktoken (cl100k_base)."""
        return len(self._tiktoken_enc.encode(text))

    def count_tokens(self, text: str) -> int:
        """
        Counts tokens using Vertex AI count_tokens API.
        Falls back to local tiktoken tokenizer if Vertex AI is unavailable (e.g. unit tests or network failure).
        """
        if not text:
            return 0

        try:
            response = self.genai_client.models.count_tokens(
                model=self.model,
                contents=text,
            )
            return int(response.total_tokens)
        except Exception as e:
            logger.warning(f"Vertex AI count_tokens fallback to tiktoken due to: {e}")
            return self.count_tokens_local(text)

    def validate_budget(
        self, text: str, max_limit: int = config.MAX_TOKENS_LIMIT
    ) -> Tuple[int, bool]:
        """
        Checks if candidate string satisfies the token limit.
        Returns (token_count, is_valid).
        """
        count = self.count_tokens(text)
        return count, (count <= max_limit)
