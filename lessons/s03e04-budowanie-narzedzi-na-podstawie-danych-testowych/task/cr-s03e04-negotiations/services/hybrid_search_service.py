"""Hybrid Search Service combining RapidFuzz lexical matching and sqlite-vec cosine similarity."""

import logging
import struct
from typing import Dict, List, Optional

from google import genai
from google.genai import types
from rapidfuzz import fuzz

from config import (
    EMBEDDING_MODEL,
    GOOGLE_CLOUD_LOCATION,
    GOOGLE_CLOUD_PROJECT,
)
from schemas import EntitySearchResult, ItemCandidate
from services.db_service import DatabaseService

logger = logging.getLogger(__name__)


def serialize_float32(vector: List[float]) -> bytes:
    """Serialize a list of floats to binary float32 buffer for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


class HybridSearchService:
    """Performs symmetric single-query Hybrid RAG (RapidFuzz + sqlite-vec) and co-occurrence analysis."""

    def __init__(self, db_service: Optional[DatabaseService] = None):
        self.db_service = db_service or DatabaseService.get_instance()
        self._genai_client = genai.Client(
            vertexai=True,
            project=GOOGLE_CLOUD_PROJECT,
            location=GOOGLE_CLOUD_LOCATION,
        )

    def _embed_query(self, query: str) -> List[float]:
        """Generate 768d embedding for search query using asymmetric retrieval format."""
        if "gemini-embedding" in EMBEDDING_MODEL:
            content = f"task: search result | query: {query}"
            config = types.EmbedContentConfig(output_dimensionality=768)
        else:
            content = query
            config = types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            )

        response = self._genai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=content,
            config=config,
        )
        return response.embeddings[0].values

    def _get_vector_candidates(self, query: str, limit: int = 40) -> Dict[str, float]:
        """Perform vector search using sqlite-vec returning {item_code: cosine_similarity}."""
        try:
            query_vector = self._embed_query(query)
            query_bytes = serialize_float32(query_vector)

            query_sql = """
                SELECT item_code, distance
                FROM vec_items
                WHERE embedding MATCH ? AND k = ?
                ORDER BY distance;
            """

            vector_scores: Dict[str, float] = {}
            with self.db_service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query_sql, (query_bytes, limit))
                for row in cursor.fetchall():
                    # In sqlite-vec distance is cosine distance (1 - cos_sim)
                    distance = float(row["distance"])
                    similarity = max(0.0, min(1.0, 1.0 - distance))
                    vector_scores[row["item_code"]] = similarity
            return vector_scores
        except Exception as e:
            logger.error("Vector search failed for query '%s': %s", query, e)
            return {}

    def _get_lexical_candidates(self, query: str) -> Dict[str, float]:
        """Perform RapidFuzz token matching returning {item_code: normalized_score}."""
        all_items = self.db_service.get_all_items()
        query_lower = query.lower()

        lexical_scores: Dict[str, float] = {}
        for item in all_items:
            name_lower = item["name"].lower()
            # Combine token_set_ratio and partial_ratio
            score_set = fuzz.token_set_ratio(query_lower, name_lower)
            score_partial = fuzz.partial_ratio(query_lower, name_lower)
            combined = (0.6 * score_set + 0.4 * score_partial) / 100.0
            if combined > 0.3:
                lexical_scores[item["code"]] = combined
        return lexical_scores

    def search_candidates_for_entity(
        self, query_entity: str, top_k: int = 3
    ) -> List[ItemCandidate]:
        """Execute hybrid search (0.4 * BM25 + 0.6 * Cosine) for a single query entity."""
        vector_scores = self._get_vector_candidates(query_entity, limit=50)
        lexical_scores = self._get_lexical_candidates(query_entity)

        # Merge candidate codes from both retrieval strategies
        candidate_codes = set(vector_scores.keys()) | set(
            sorted(lexical_scores, key=lexical_scores.get, reverse=True)[:50]
        )

        all_items_dict = {item["code"]: item["name"] for item in self.db_service.get_all_items()}
        stocking_cities_map = self.db_service.get_stocking_cities_for_items(list(candidate_codes))

        scored_candidates: List[ItemCandidate] = []
        for code in candidate_codes:
            item_name = all_items_dict.get(code, "Nieznany")
            v_score = vector_scores.get(code, 0.0)
            l_score = lexical_scores.get(code, 0.0)

            # Hybrid formula: 0.4 * BM25 + 0.6 * Cosine
            hybrid_score = round(0.4 * l_score + 0.6 * v_score, 4)

            scored_candidates.append(
                ItemCandidate(
                    item_code=code,
                    item_name=item_name,
                    hybrid_score=hybrid_score,
                    stocking_cities=stocking_cities_map.get(code, []),
                    co_occurrence_cities=[],
                )
            )

        # Rank by hybrid score descending
        scored_candidates.sort(key=lambda c: c.hybrid_score, reverse=True)
        return scored_candidates[:top_k]

    def search_all_entities_with_co_occurrence(
        self, query_entities: List[str]
    ) -> List[EntitySearchResult]:
        """Perform hybrid search for each entity and calculate cross-entity co-occurrence cities."""
        if not query_entities:
            return []

        # 1. Search top candidates for each entity
        results: List[EntitySearchResult] = []
        for entity in query_entities:
            candidates = self.search_candidates_for_entity(entity, top_k=3)
            results.append(EntitySearchResult(query_entity=entity, candidates=candidates))

        # 2. Compute co-occurrence across candidate sets if multiple entities exist
        if len(results) > 1:
            for i, res_i in enumerate(results):
                for candidate_i in res_i.candidates:
                    shared_cities = set()
                    cities_i = set(candidate_i.stocking_cities)

                    # Compare against candidates of all other entities
                    for j, res_j in enumerate(results):
                        if i == j:
                            continue
                        for candidate_j in res_j.candidates:
                            cities_j = set(candidate_j.stocking_cities)
                            intersection = cities_i & cities_j
                            shared_cities.update(intersection)

                    candidate_i.co_occurrence_cities = sorted(list(shared_cities))

        return results
