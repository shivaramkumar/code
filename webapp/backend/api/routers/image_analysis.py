from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List

from db.models import get_db, ProcessedImage
from api.services.directory_watcher import watcher

import asyncio

router = APIRouter()

class WatchRequest(BaseModel):
    directory_path: str

class ImageResponse(BaseModel):
    id: int
    filename: str
    filepath: str
    extracted_text: str | None
    is_complete_meaning: int
    
    class Config:
        from_attributes = True

@router.post("/watch", response_model=dict)
async def start_watching(req: WatchRequest):
    """Start watching the specified directory for new images."""
    try:
        # Pass the current event loop explicitly
        loop = asyncio.get_running_loop()
        
        # We need to hack the watcher loop dynamically just in case
        from api.services.directory_watcher import ImageEventHandler, Observer
        
        watcher.stop()
        
        if not watcher.observer:
            import os
            import logging
            from watchdog.observers import Observer
            
            logger = logging.getLogger(__name__)
            path = req.directory_path
            
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                
            watcher.watching_path = path
            logger.info(f"Starting directory watcher on: {path}")
            
            event_handler = ImageEventHandler(loop)
            watcher.observer = Observer()
            watcher.observer.schedule(event_handler, path, recursive=False)
            watcher.observer.start()
            
        return {"status": "success", "message": f"Started watching {req.directory_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/watch", response_model=dict)
def stop_watching():
    """Stop the directory watcher."""
    watcher.stop()
    return {"status": "success", "message": "Stopped watching directory"}

@router.get("/status", response_model=dict)
def get_watch_status():
    """Get the current running watcher status."""
    return {"watching": watcher.observer is not None, "path": getattr(watcher, 'watching_path', None)}

@router.get("/results", response_model=List[ImageResponse])
def get_processed_images(db: Session = Depends(get_db)):
    """Retrieve all processed images and their extraction results."""
    return db.query(ProcessedImage).order_by(ProcessedImage.processed_at.desc()).all()
