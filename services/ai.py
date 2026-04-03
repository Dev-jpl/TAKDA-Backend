import os
from database import supabase
from services.embeddings import embed_query

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")  # gemini | ollama | groq | openrouter | anthropic

# --- Per-provider model defaults (override any via .env) ---
MODELS = {
    "gemini":      os.getenv("GEMINI_MODEL",      "gemini-1.5-flash"),
    "ollama":      os.getenv("OLLAMA_MODEL",      "llama3.2"),
    "groq":        os.getenv("GROQ_MODEL",         "llama-3.1-8b-instant"),
    "openrouter":  os.getenv("OPENROUTER_MODEL",   "meta-llama/llama-3.2-3b-instruct:free"),
    "anthropic":   os.getenv("ANTHROPIC_MODEL",    "claude-haiku-4-5-20251001"),
}


def get_ai_response(system: str, user: str) -> str:
    provider = AI_PROVIDER

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel(MODELS["gemini"])
        response = model.generate_content(f"{system}\n\n{user}")
        return response.text

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=MODELS["anthropic"],
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    # All OpenAI-compatible providers (ollama, groq, openrouter)
    from openai import OpenAI

    if provider == "ollama":
        client = OpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"),
            api_key="ollama",
        )
    elif provider == "groq":
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
    elif provider == "openrouter":
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown AI_PROVIDER: '{provider}'. Choose ollama, groq, openrouter, or anthropic.")

    response = client.chat.completions.create(
        model=MODELS[provider],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1024,
    )
    return response.choices[0].message.content


async def get_ai_response_async(system: str, user: str) -> str:
    provider = AI_PROVIDER

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel(MODELS["gemini"])
        # Standard async generate_content
        response = await model.generate_content_async(f"{system}\n\n{user}")
        return response.text

    if provider == "anthropic":
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = await client.messages.create(
            model=MODELS["anthropic"],
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    from openai import AsyncOpenAI
    if provider == "ollama":
        client = AsyncOpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"),
            api_key="ollama",
        )
    elif provider == "groq":
        client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
    elif provider == "openrouter":
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown AI_PROVIDER: '{provider}'.")

    response = await client.chat.completions.create(
        model=MODELS[provider],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1024,
    )
    return response.choices[0].message.content


async def search_chunks(
    query: str,
    user_id: str,
    space_id: str = None,
    hub_id: str = None,
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
        chunks = result.data or []
    except Exception as e:
        print(f"Vector search failed: {e}")
        query_obj = supabase.table("document_chunks") \
            .select("content, document_id, chunk_index") \
            .limit(limit)
        if document_ids:
            query_obj = query_obj.in_("document_id", document_ids)
        result = query_obj.execute()
        chunks = result.data or []

    return chunks


async def chat_with_documents(
    query: str,
    user_id: str,
    space_id: str = None,
    hub_id: str = None,
    document_ids: list[str] = None,
) -> dict:
    chunks = await search_chunks(query, user_id, space_id, hub_id, document_ids)

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

    user_prompt = f"""Documents:
{context}

Question: {query}

Answer with citations:"""

    answer = get_ai_response(system, user_prompt)
    return {"answer": answer, "citations": citations}


async def get_streaming_ai_response(system: str, user: str):
    provider = os.getenv("AI_PROVIDER", "gemini")

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel(
            model_name=MODELS["gemini"],
            system_instruction=system
        )
        response = await model.generate_content_async(user, stream=True)
        async for chunk in response:
            if chunk.text:
                yield chunk.text
        return

    if provider == "anthropic":
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        async with client.messages.stream(
            model=MODELS["anthropic"],
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    yield event.delta.text
        return

    # OpenAI-compatible (ollama, groq, openrouter)
    from openai import AsyncOpenAI

    if provider == "ollama":
        client = AsyncOpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"),
            api_key="ollama",
        )
    elif provider == "groq":
        client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
    elif provider == "openrouter":
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown AI_PROVIDER: '{provider}' for streaming.")

    stream = await client.chat.completions.create(
        model=MODELS[provider],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1024,
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
