"""Embed and upload knowledge chunks into Supabase for RAG retrieval.

Usage:
    python -m scripts.embed_knowledge --source sgk_toan_12
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from supabase import create_client

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50


def chunk_markdown(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    if not text.strip():
        return []

    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current and current_len + para_len > chunk_size * 4:
            chunks.append("\n\n".join(current).strip())

            if overlap > 0 and chunks[-1]:
                tail = chunks[-1][-overlap * 4 :]
                current = [tail, para]
                current_len = len(tail) + para_len
            else:
                current = [para]
                current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def infer_chapter_from_path(path: Path) -> str:
    lowered = path.stem.lower()
    if "dao_ham" in lowered or "derivative" in lowered:
        return "dao_ham"
    if "tich_phan" in lowered or "integral" in lowered:
        return "tich_phan"
    if "luong_giac" in lowered or "trig" in lowered:
        return "luong_giac"
    if "mu" in lowered or "log" in lowered:
        return "mu_logarit"
    return "general"


def load_source_chunks(source_root: Path, source: str, chapter: str | None) -> list[dict[str, Any]]:
    if not source_root.exists():
        raise FileNotFoundError(f"Source folder not found: {source_root}")

    chunks: list[dict[str, Any]] = []

    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue

        file_chapter = infer_chapter_from_path(path)
        if chapter and file_chapter != chapter:
            continue

        if path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8")
            for idx, chunk in enumerate(chunk_markdown(text), start=1):
                chunks.append(
                    {
                        "source": source,
                        "chapter": file_chapter,
                        "section": path.stem,
                        "content": chunk,
                        "metadata": {"path": str(path), "chunk_index": idx},
                    }
                )
            continue

        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                for idx, item in enumerate(payload, start=1):
                    if not isinstance(item, dict):
                        continue
                    content = str(item.get("content") or item.get("text") or "").strip()
                    if not content:
                        continue
                    chunks.append(
                        {
                            "source": source,
                            "chapter": str(item.get("chapter") or file_chapter),
                            "section": str(item.get("section") or path.stem),
                            "content": content,
                            "metadata": {
                                "path": str(path),
                                "chunk_index": idx,
                                **{k: v for k, v in item.items() if k not in {"content", "text"}},
                            },
                        }
                    )

    return chunks


async def build_embedding_client():
    import vertexai
    from vertexai.language_models import TextEmbeddingModel

    project = os.getenv("GCP_PROJECT_ID", "").strip()
    location = os.getenv("GCP_LOCATION", "us-central1")
    model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-004")

    if project:
        await asyncio.to_thread(vertexai.init, project=project, location=location)

    return await asyncio.to_thread(TextEmbeddingModel.from_pretrained, model_name)


async def embed_and_insert(
    chunks: list[dict[str, Any]],
    *,
    supabase,
    embedding_model,
    dry_run: bool,
) -> None:
    if not chunks:
        print("No chunks found.")
        return

    print(f"Prepared {len(chunks)} chunks")
    if dry_run:
        print("Dry run mode enabled. No database writes were performed.")
        preview = chunks[: min(3, len(chunks))]
        for idx, item in enumerate(preview, start=1):
            content_preview = str(item.get("content", "")).replace("\n", " ")[:120]
            print(f"  [{idx}] source={item.get('source')} chapter={item.get('chapter')} preview={content_preview}")
        return

    if supabase is None or embedding_model is None:
        raise RuntimeError("supabase and embedding_model are required when dry_run is false")

    for idx, chunk in enumerate(chunks, start=1):
        embeddings = await asyncio.to_thread(embedding_model.get_embeddings, [chunk["content"]])
        vector = list(embeddings[0].values)

        payload = {
            "source": chunk["source"],
            "chapter": chunk.get("chapter"),
            "section": chunk.get("section"),
            "content": chunk["content"],
            "embedding": vector,
            "metadata": chunk.get("metadata", {}),
        }

        await asyncio.to_thread(lambda: supabase.table("knowledge_chunks").insert(payload).execute())
        if idx % 10 == 0 or idx == len(chunks):
            print(f"Inserted {idx}/{len(chunks)} chunks")


async def main_async(args: argparse.Namespace) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    source_root = backend_root / "data" / "knowledge" / args.source

    chunks = load_source_chunks(source_root=source_root, source=args.source, chapter=args.chapter)

    if args.dry_run:
        await embed_and_insert(
            chunks,
            supabase=None,
            embedding_model=None,
            dry_run=True,
        )
        return

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_KEY", "").strip()
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")

    supabase = create_client(supabase_url, supabase_key)
    embedding_model = await build_embedding_client()

    await embed_and_insert(
        chunks,
        supabase=supabase,
        embedding_model=embedding_model,
        dry_run=args.dry_run,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed and upload knowledge data")
    parser.add_argument("--source", required=True, help="Knowledge source folder")
    parser.add_argument("--chapter", help="Optional chapter filter")
    parser.add_argument("--dry-run", action="store_true", help="Preview without insert")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
