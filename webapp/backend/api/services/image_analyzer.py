import os
import json
import base64
import httpx
from openai import AsyncAzureOpenAI
import logging

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

def get_config():
    config_path = os.path.join(os.path.dirname(__file__), "../../../config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except:
        return {}

def encode_image_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.png']: return 'image/png'
    elif ext in ['.webp']: return 'image/webp'
    return 'image/jpeg'

async def analyze_image(file_path: str) -> dict:
    """Analyze the image using configured LLM (Local or Azure)."""
    base64_image = encode_image_to_base64(file_path)
    mime_type = get_mime_type(file_path)
    config = get_config()
    
    provider = config.get("model_provider", "Ollama (Local)")
    model_name = config.get("model_name", "llama3.2-vision")
    
    prompt = (
        "Analyze this image in detail. "
        "1. Provide a concise 'visual_description' of what is in the image (objects, people, scene). "
        "2. Extract any 'extracted_text' you strictly see inside the frame. "
        "3. Classify if the text has 'complete meaning' or 'missing characters' (is_complete). "
        "Return STRICTLY a JSON object with these keys: 'visual_description', 'extracted_text', 'is_complete'."
    )
    
    try:
        if provider == "Azure OpenAI":
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
            
            if not endpoint or not api_key:
                logger.error("Azure OpenAI credentials missing in environment.")
                return {"extracted_text": "", "is_complete": False}
                
            client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version
            )
            
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            json_str = response.choices[0].message.content
            return json.loads(json_str)
            
        else: # Default to Ollama
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [base64_image]
                    }
                ],
                "format": "json",
                "stream": False
            }
            
            async with httpx.AsyncClient() as client:
                res = await client.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60.0)
                res.raise_for_status()
                data = res.json()
                
                content = data.get("message", {}).get("content", "{}")
                return json.loads(content)
                
    except Exception as e:
        logger.error(f"Image analysis failed: {str(e)}")
        return {"extracted_text": f"Error: {str(e)}", "is_complete": False}
