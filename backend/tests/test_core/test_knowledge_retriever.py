from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.knowledge_retriever import KnowledgeRetriever


class _RPCBuilder:
    def __init__(self, rows):
        self._rows = rows

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _SupabaseStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def rpc(self, name: str, params: dict):
        self.calls.append((name, params))
        return _RPCBuilder(self.rows)


@pytest.mark.asyncio
async def test_search_returns_unavailable_without_supabase() -> None:
    retriever = KnowledgeRetriever(supabase_client=None)

    result = await retriever.search(query="chain rule")

    assert result["count"] == 0
    assert result["error"] == "missing_supabase_client"


@pytest.mark.asyncio
async def test_search_success_with_mocked_embedding() -> None:
    supabase = _SupabaseStub(
        rows=[
            {
                "content": "Chain rule content",
                "source": "sgk_toan_12",
                "chapter": "dao_ham",
                "similarity": 0.9123,
            }
        ]
    )
    retriever = KnowledgeRetriever(supabase_client=supabase)
    retriever._get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])

    result = await retriever.search(
        query="dao ham ham hop",
        top_k=2,
        source_filter="sgk_toan_12",
        chapter_filter="dao_ham",
    )

    assert result["count"] == 1
    assert result["chunks"][0]["similarity"] == 0.912
    assert "sgk_toan_12" in result["interpretation"]

    assert len(supabase.calls) == 1
    rpc_name, params = supabase.calls[0]
    assert rpc_name == "match_knowledge_chunks"
    assert params["match_count"] == 2
    assert params["source_filter"] == "sgk_toan_12"
    assert params["chapter_filter"] == "dao_ham"


@pytest.mark.asyncio
async def test_search_returns_error_payload_on_exception() -> None:
    supabase = _SupabaseStub(rows=[])
    retriever = KnowledgeRetriever(supabase_client=supabase)
    retriever._get_embedding = AsyncMock(side_effect=RuntimeError("embedding failed"))

    result = await retriever.search(query="x")

    assert result["count"] == 0
    assert "embedding failed" in result["error"]


@pytest.mark.asyncio
async def test_get_relevant_for_hypothesis_maps_query() -> None:
    retriever = KnowledgeRetriever(supabase_client=_SupabaseStub(rows=[]))
    retriever.search = AsyncMock(return_value={"count": 0, "chunks": []})

    await retriever.get_relevant_for_hypothesis("H03_Chain")

    retriever.search.assert_awaited_once_with(
        query="quy tac chain rule dao ham ham hop f(g(x))",
        top_k=3,
        chapter_filter="dao_ham",
    )


def test_summarize_chunks_no_results() -> None:
    retriever = KnowledgeRetriever(supabase_client=None)

    summary = retriever._summarize_chunks([], "dao ham")

    assert summary == "No knowledge found for query: dao ham"
