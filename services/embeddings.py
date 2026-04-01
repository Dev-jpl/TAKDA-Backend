import os
import voyageai
from database import supabase

vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

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
    result = vo.embed(
        [text],
        model="voyage-3",
        input_type="document",
    )
    return result.embeddings[0]


def embed_query(text: str) -> list[float]:
    result = vo.embed(
        [text],
        model="voyage-3",
        input_type="query",
    )
    return result.embeddings[0]


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
        query_embedding = embed_query(query)  # use query type

        result = supabase.rpc("match_chunks", {
            "query_embedding": query_embedding,
            "user_id": user_id,
            "match_count": limit,
            "document_ids": document_ids or [],
        }).execute()

        return result.data or []

    except Exception as e:
        print(f"Vector search failed: {e}")
        query_obj = supabase.table("document_chunks") \
            .select("content, document_id, chunk_index") \
            .limit(limit)

        if document_ids:
            query_obj = query_obj.in_("document_id", document_ids)

        result = query_obj.execute()
        return result.data or []