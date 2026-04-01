import os
from openai import OpenAI
from database import supabase
from services.embeddings import embed_query

AI_PROVIDER = os.getenv("AI_PROVIDER", "openrouter")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")


def get_ai_client():
    if AI_PROVIDER == "openrouter":
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    elif AI_PROVIDER == "anthropic":
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    else:
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )


def get_model():
    if AI_PROVIDER == "anthropic":
        return "anthropic/claude-sonnet-4-5"
    return OPENROUTER_MODEL


def get_ai_response(system: str, user: str) -> str:
    client = get_ai_client()
    model = get_model()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1024,
        extra_headers={
            "HTTP-Referer": "https://takda.app",
            "X-Title": "TAKDA",
        },
    )
    return response.choices[0].message.content


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
        query_obj = supabase.table("document_chunks") \
            .select("content, document_id, chunk_index") \
            .limit(limit)

        if document_ids:
            query_obj = query_obj.in_("document_id", document_ids)

        result = query_obj.execute()
        return result.data or []


async def chat_with_documents(
    query: str,
    user_id: str,
    document_ids: list[str] = None,
) -> dict:
    chunks = await search_chunks(query, user_id, document_ids)

    if not chunks:
        return {
            "answer": "No relevant documents found. Try uploading some documents first.",
            "citations": [],
        }

    context = ""
    citations = []

    for i, chunk in enumerate(chunks):
        context += f"\n[{i+1}] {chunk['content']}\n"
        citations.append({
            "index": i + 1,
            "document_id": chunk.get("document_id"),
            "chunk_index": chunk.get("chunk_index"),
            "excerpt": chunk["content"][:120] + "...",
        })

    system = """You are TAKDA's knowledge assistant. Answer questions based strictly 
on the provided document chunks. Always cite your sources using [1], [2], etc. 
Be concise and direct. If the answer is not in the documents say so clearly."""

    user = f"""Documents:
{context}

Question: {query}

Answer with citations:"""

    answer = get_ai_response(system, user)

    return {
        "answer": answer,
        "citations": citations,
    }