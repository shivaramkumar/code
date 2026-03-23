from fastapi import APIRouter, Depends
import httpx
import os
from pydantic import BaseModel
from db.cache import check_cache, cache_response, retrieve_context

import time
import logging

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)
logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    use_context: bool = True

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

@router.post("/chat")
async def chat_with_ai(request: ChatRequest):
    req_start_time = time.time()
    logger.info(f"Received input: {request.message[:100]}...")
    
    # 1. Semantic Caching Check
    cached_reply = check_cache(request.message, threshold=0.1) # low threshold for test
    if cached_reply:
         process_time = time.time() - req_start_time
         logger.info(f"Cache Hit! Processing time: {process_time:.4f}s")
         return {"response": cached_reply, "source": "semantic_cache"}
    
    logger.info("Cache Miss. Proceeding to LLM generation.")
    
    # 2. Add Context if requested
    prompt = request.message
    if request.use_context:
         contexts = retrieve_context(request.message)
         if contexts:
             context_text = "\n".join(contexts)
             prompt = f"Context:\n{context_text}\n\nUser: {request.message}"

    # 3. Call LLM (Ollama or Azure) with Streaming to measure TTFT
    async with httpx.AsyncClient() as client:
        try:
            payload = {
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": True # Stream is True to intercept first token
            }
            
            logger.info("Sending request to LLM...")
            
            # Using async streaming
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload, timeout=30.0) as res:
                res.raise_for_status()
                
                ttft: float = None
                response_text = ""
                
                async for chunk in res.aiter_lines():
                    if chunk:
                        # Record TTFT on first valid chunk
                        if ttft is None:
                            ttft = time.time() - req_start_time
                            logger.info(f"TTFT (Time To First Token): {ttft:.4f}s")
                            
                        import json
                        data = json.loads(chunk)
                        response_text += data.get("message", {}).get("content", "")
                
                total_time = time.time() - req_start_time
                logger.info(f"LLM Generation completed. Total processing time: {total_time:.4f}s")
            
            # 4. Save to Semantic Cache
            cache_start = time.time()
            cache_response(request.message, response_text)
            logger.info(f"Response cached. Cache write time: {time.time() - cache_start:.4f}s")
            
            return {"response": response_text, "source": "ollama (local)", "used_context": request.use_context}
        except Exception as e:
            logger.error(f"Error during AI generation: {str(e)}")
            return {"error": str(e), "note": "Make sure Ollama is running locally or Azure Foundry is configured."}
