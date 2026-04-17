"""RAG retrieval service backed by Supabase pgvector."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("core.knowledge_retriever")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")


class KnowledgeRetriever:
    """Retrieve relevant Math knowledge chunks via vector similarity."""

    def __init__(self, supabase_client: Any | None = None):
        self._supabase = supabase_client
        self._embed_client: Any | None = None
        self._vertex_initialized = False

    async def _ensure_embed_client(self) -> None:
        if self._embed_client is not None:
            return

        def _init_client() -> Any:
            import vertexai
            from vertexai.language_models import TextEmbeddingModel

            project = os.getenv("GCP_PROJECT_ID", "").strip()
            location = os.getenv("GCP_LOCATION", "us-central1")
            if project:
                vertexai.init(project=project, location=location)
            return TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)

        self._embed_client = await asyncio.to_thread(_init_client)
        self._vertex_initialized = True

    async def _get_embedding(self, text: str) -> list[float]:
        await self._ensure_embed_client()

        def _embed() -> list[float]:
            embeddings = self._embed_client.get_embeddings([text])
            return list(embeddings[0].values)

        return await asyncio.to_thread(_embed)

    async def search(
        self,
        query: str,
        top_k: int = 3,
        source_filter: Optional[str] = None,
        chapter_filter: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self._supabase:
            return {
                "chunks": [],
                "count": 0,
                "interpretation": "Knowledge database is unavailable.",
                "error": "missing_supabase_client",
            }

        try:
            embedding = await self._get_embedding(query)

            params: dict[str, Any] = {
                "query_embedding": embedding,
                "match_count": max(1, int(top_k)),
            }
            if source_filter:
                params["source_filter"] = source_filter
            if chapter_filter:
                params["chapter_filter"] = chapter_filter

            response = await asyncio.to_thread(
                lambda: self._supabase.rpc("match_knowledge_chunks", params).execute()
            )
            rows = getattr(response, "data", None) or []

            chunks = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                chunks.append(
                    {
                        "content": str(row.get("content", "")),
                        "source": str(row.get("source", "")),
                        "chapter": str(row.get("chapter", "")),
                        "similarity": round(float(row.get("similarity", 0.0) or 0.0), 3),
                    }
                )

            return {
                "chunks": chunks,
                "count": len(chunks),
                "interpretation": self._summarize_chunks(chunks, query),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Knowledge retrieval failed: %s", exc)
            return {
                "chunks": [],
                "count": 0,
                "interpretation": "Knowledge retrieval failed.",
                "error": str(exc),
            }

    async def get_relevant_for_hypothesis(self, hypothesis: str) -> dict[str, Any]:
        query_by_hypothesis = {
            "H01_Trig": "dao ham luong giac sin cos tan cot cong thuc",
            "H02_ExpLog": "dao ham ham mu logarit e^x ln(x) a^x",
            "H03_Chain": "quy tac chain rule dao ham ham hop f(g(x))",
            "H04_Rules": "quy tac tong hieu tich thuong dao ham co ban",
        }
        query = query_by_hypothesis.get(hypothesis, hypothesis)
        return await self.search(query=query, top_k=3, chapter_filter="dao_ham")

    def _summarize_chunks(self, chunks: list[dict[str, Any]], query: str) -> str:
        if not chunks:
            return f"No knowledge found for query: {query}"

        sources = sorted({str(item.get("source", "")) for item in chunks if item.get("source")})
        if not sources:
            return f"Found {len(chunks)} relevant chunks"

        return f"Found {len(chunks)} relevant chunks from: {', '.join(sources)}"
