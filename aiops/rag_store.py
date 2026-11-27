import os
from functools import lru_cache
from pathlib import Path

import chromadb
from google import genai
from google.genai import types
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
COLLECTION_NAME = "aiops_knowledge_gemini"


@lru_cache(maxsize=1)
def _embedding_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=30000),
    )


@lru_cache(maxsize=1)
def _collection():
    database_path = Path(
        os.getenv("RAG_DB_PATH", str(PROJECT_ROOT / "data" / "chroma"))
    )
    database_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(database_path))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
    )


def _embed(text: str, task_type: str) -> list[float]:
    result = _embedding_client().models.embed_content(
        model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        contents=text,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    if not result.embeddings or not result.embeddings[0].values:
        raise RuntimeError("Gemini returned an empty embedding")
    return result.embeddings[0].values


def ingest_file(file_path: str | Path) -> int:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Runbook does not exist: {path}")

    content = path.read_text(encoding="utf-8")
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
    ).split_text(content)

    for index, chunk in enumerate(chunks):
        _collection().upsert(
            ids=[f"{path.resolve()}-{index}"],
            documents=[chunk],
            embeddings=[_embed(chunk, "RETRIEVAL_DOCUMENT")],
            metadatas=[{"source": str(path.resolve())}],
        )
    return len(chunks)


def search_knowledge(query: str, top_k: int = 3) -> str:
    collection = _collection()
    count = collection.count()
    if count == 0:
        return ""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    results = collection.query(
        query_embeddings=[_embed(query, "RETRIEVAL_QUERY")],
        n_results=min(top_k, count),
    )
    documents = results.get("documents", [[]])[0]
    return "\n\n".join(documents)


if __name__ == "__main__":
    runbook = Path(
        os.getenv(
            "KNOWLEDGE_FILE",
            str(PROJECT_ROOT / "knowledge" / "nginx_runbook.md"),
        )
    )
    print(f"Ingested {ingest_file(runbook)} runbook chunks from {runbook}")
