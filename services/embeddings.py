import os
from fastembed import TextEmbedding
from database import supabase

# Initialize FastEmbed (Optimized for CPU)
# This will download the BGE-Small model (384-dims) on first run (~133MB)
model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def chunk_text(text: str) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + CHUNK_SIZE])
        chunks.append(chunk)
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


def embed_text(text: str) -> list[float]:
    """Generates an embedding for a document chunk using the local OS model."""
    # FastEmbed's embed() returns a generator of numpy arrays
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


def embed_query(text: str) -> list[float]:
    """Generates an embedding for a search query. Same model used for documents."""
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


async def process_document(document_id: str, text: str):
    chunks = chunk_text(text)

    print(f"Processing {len(chunks)} chunks for document {document_id}")

    for index, chunk in enumerate(chunks):
        try:
            embedding = embed_text(chunk)

            supabase.table("document_chunks").insert({
                "document_id": document_id,
                "content": chunk,
                "chunk_index": index,
                "embedding": embedding,
            }).execute()

            print(f"Chunk {index + 1}/{len(chunks)} embedded")

        except Exception as e:
            print(f"Chunk {index} failed: {e}")
            # If embedding fails, still insert the chunk without the vector
            # (less ideal, but prevents total failure)
            supabase.table("document_chunks").insert({
                "document_id": document_id,
                "content": chunk,
                "chunk_index": index,
            }).execute()


async def search_chunks(
    query: str,
    user_id: str,
    document_ids: list[str] = None,
    limit: int = 8,
) -> list[dict]:
    try:
        query_embedding = embed_query(query)

        result = supabase.rpc("match_chunks", {
            "query_embedding": query_embedding,
            "user_id": user_id,
            "match_count": limit,
            "document_ids": document_ids or [],
        }).execute()

        return result.data or []

    except Exception as e:
        print(f"Vector search failed: {e}")
        # Fallback to key-word style or simple select if vector search is broken
        query_obj = supabase.table("document_chunks") \
            .select("content, document_id, chunk_index") \
            .limit(limit)

        if document_ids:
            query_obj = query_obj.in_("document_id", document_ids)

        result = query_obj.execute()
        return result.data or []