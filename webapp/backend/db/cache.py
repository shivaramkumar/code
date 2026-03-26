import os
import chromadb

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Initialize ChromaDB client (persistent path)
CHROMA_PATH = os.path.join(os.getcwd(), "chroma_data")
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

# Collections
semantic_cache = chroma_client.get_or_create_collection(name="semantic_cache")
context_collection = chroma_client.get_or_create_collection(name="uploaded_context")

def cache_response(prompt: str, response: str, user_id: str):
    # Store response for a given prompt in semantic cache
    # Id can be hash of prompt or sequential combined with user_id
    import hashlib
    doc_id = hashlib.md5((prompt + user_id).encode()).hexdigest()
    semantic_cache.upsert(
        documents=[prompt],
        metadatas=[{"response": response, "user_id": user_id}],
        ids=[doc_id]
    )

def check_cache(prompt: str, user_id: str, threshold: float = 0.9):
    # Perform a similarity search strictly within the user's partition
    results = semantic_cache.query(
        query_texts=[prompt],
        n_results=1,
        where={"user_id": {"$eq": user_id}}
    )
    if results["distances"] and len(results["distances"][0]) > 0:
        distance = results["distances"][0][0]
        if distance < (1.0 - threshold): 
            return results["metadatas"][0][0].get("response")
    return None

def store_context(text: str, filename: str, user_id: str, tool_id: str):
    import uuid
    doc_id = str(uuid.uuid4())
    context_collection.add(
        documents=[text],
        metadatas=[{"filename": filename, "user_id": user_id, "tool_id": tool_id}],
        ids=[doc_id]
    )

def retrieve_context(query: str, user_id: str, tool_id: str, n_results: int = 3):
    # Enforce vector db indexing on user profile and tool index
    try:
        results = context_collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"$and": [
                {"user_id": {"$eq": user_id}}, 
                {"tool_id": {"$eq": tool_id}}
            ]}
        )
        if results["documents"] and len(results["documents"][0]) > 0:
             return results["documents"][0]
    except Exception as e:
        # Fails gracefully if no documents exist for this strict partition yet
        pass
    return []
