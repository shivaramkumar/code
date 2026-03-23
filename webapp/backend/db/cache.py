import chromadb
import os

# Initialize ChromaDB client (persistent path)
CHROMA_PATH = os.path.join(os.getcwd(), "chroma_data")
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

# Collections
semantic_cache = chroma_client.get_or_create_collection(name="semantic_cache")
context_collection = chroma_client.get_or_create_collection(name="uploaded_context")

def cache_response(prompt: str, response: str):
    # Store response for a given prompt in semantic cache
    # Id can be hash of prompt or sequential
    import hashlib
    doc_id = hashlib.md5(prompt.encode()).hexdigest()
    semantic_cache.upsert(
        documents=[prompt],
        metadatas=[{"response": response}],
        ids=[doc_id]
    )

def check_cache(prompt: str, threshold: float = 0.9):
    # Perform a similarity search on the prompt
    # Since chromadb uses L2 distance by default, lower is better. 
    # But usually distances < 0.3 mean high similarity. We can check if any result is close.
    results = semantic_cache.query(
        query_texts=[prompt],
        n_results=1
    )
    if results["distances"] and len(results["distances"][0]) > 0:
        distance = results["distances"][0][0]
        if distance < (1.0 - threshold): # Rough heuristic
            return results["metadatas"][0][0].get("response")
    return None

def store_context(text: str, filename: str):
    import uuid
    doc_id = str(uuid.uuid4())
    context_collection.add(
        documents=[text],
        metadatas=[{"filename": filename}],
        ids=[doc_id]
    )

def retrieve_context(query: str, n_results: int = 3):
    results = context_collection.query(
        query_texts=[query],
        n_results=n_results
    )
    if results["documents"] and len(results["documents"][0]) > 0:
         return results["documents"][0]
    return []
