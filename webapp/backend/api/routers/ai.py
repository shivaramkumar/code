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
    user_id: str = "default_user"
    tool_id: str = "retrieve_context"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

import json

def get_config_value(key, default):
    config_path = os.path.join(os.path.dirname(__file__), "../../../config.json")
    try:
        with open(config_path, "r") as f:
            c = json.load(f)
            return c.get(key, default)
    except:
        return default

@router.post("/chat")
async def chat_with_ai(request: ChatRequest):
    req_start_time = time.time()
    learning_events = []
    
    def log_event(layer, action, desc):
        logger.info(f"[{layer}] {action}: {desc}")
        learning_events.append({"layer": layer, "action": action, "description": desc})
        
    log_event("Frontend", "Message Received", f"Received user prompt: '{request.message[:50]}...'")
    
    # 1. Semantic Caching Check (Isolated by User Index)
    log_event("Semantic Cache", "Querying ChromaDB", f"Checking if prompt exists in vector cache explicitly for user '{request.user_id}'.")
    cached_reply = check_cache(request.message, user_id=request.user_id, threshold=0.1) 
    if cached_reply:
         process_time = time.time() - req_start_time
         log_event("Semantic Cache", "Cache HIT", f"Found matching response in {process_time:.4f}s. Bypassing LLM.")
         return {"response": cached_reply, "source": "semantic_cache", "events": learning_events}
    
    log_event("Semantic Cache", "Cache MISS", "No match found. Proceeding to LLM generation.")
    
    # 2. Add Context if requested (Isolated by User + Context Tool Index)
    prompt = request.message
    if request.use_context:
         log_event("MCP Tools", f"Executing {request.tool_id}", f"Fetching relevant chunks from ChromaDB uploaded context for '{request.user_id}'.")
         contexts = retrieve_context(request.message, user_id=request.user_id, tool_id=request.tool_id)
         if contexts:
             context_text = "\n".join(contexts)
             prompt = f"Context:\n{context_text}\n\nUser: {request.message}"
             log_event("MCP Tools", "Context Appended", f"Appended {len(contexts)} document context chunks to prompt.")

    # 3. Call LLM (Ollama or Azure) with Streaming to measure TTFT
    model_name = get_config_value("model_name", "llama3.2:3b")
    
    async with httpx.AsyncClient() as client:
        try:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True 
            }
            
            log_event("LLM Provider", "Sending Request", f"Streaming request to model '{model_name}' via locally hosted Ollama.")
            
            # Using async streaming
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload, timeout=30.0) as res:
                res.raise_for_status()
                
                ttft = None
                response_text = ""
                
                async for chunk in res.aiter_lines():
                    if chunk:
                        if ttft is None:
                            ttft = time.time() - req_start_time
                            log_event("LLM Provider", "First Token Received", f"TTFT (Time To First Token): {ttft:.4f}s")
                            
                        data = json.loads(chunk)
                        response_text += data.get("message", {}).get("content", "")
                
                total_time = time.time() - req_start_time
                log_event("LLM Provider", "Stream Complete", f"Total processing time: {total_time:.4f}s")
            
            # 4. Save to Semantic Cache
            cache_start = time.time()
            cache_response(request.message, response_text, user_id=request.user_id)
            log_event("Semantic Cache", "Cache Write", f"Response embedded and saved to user vector store in {time.time() - cache_start:.4f}s")
            
            return {"response": response_text, "source": model_name, "used_context": request.use_context, "events": learning_events}
        except Exception as e:
            logger.error(f"Error during AI generation: {str(e)}")
            log_event("LLM Provider", "Error", f"Failed: {str(e)}")
            return {"error": str(e), "note": "Make sure Ollama is running.", "events": learning_events}
