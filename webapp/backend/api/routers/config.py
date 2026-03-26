from fastapi import APIRouter
import json
import os

router = APIRouter()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../../config.json")

@router.get("")
async def get_config():
    """
    [EDUCATIONAL NOTE]
    This endpoint serves the configuration stored in /config.json directly to our Vanilla JS frontend.
    This demonstrates how frontends can dynamically initialize their State based on Backend data.
    """
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        return {"error": "config.json not found"}
    except Exception as e:
        return {"error": str(e)}
