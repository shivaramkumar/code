import os
import time
import asyncio
import logging
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from sqlalchemy.orm import Session
from db.models import SessionLocal, ProcessedImage
from .image_analyzer import analyze_image

logger = logging.getLogger(__name__)

class ImageEventHandler(FileSystemEventHandler):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        
    def process(self, event):
        if event.is_directory:
            return
            
        filepath = event.src_path
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
            return
            
        # Give the file a moment to finish writing
        time.sleep(1)
        
        db: Session = SessionLocal()
        try:
            # Check if already processed
            existing = db.query(ProcessedImage).filter(ProcessedImage.filepath == filepath).first()
            if existing:
                logger.info(f"Image already processed: {filepath}")
                return
                
            logger.info(f"New image detected: {filepath}. Starting analysis...")
            
            # Submitting async work to the main event loop
            future = asyncio.run_coroutine_threadsafe(analyze_image(filepath), self.loop)
            
            try:
                result = future.result(timeout=60) # Wait up to 60s for analysis
                
                # Save to DB
                new_image = ProcessedImage(
                    filename=os.path.basename(filepath),
                    filepath=filepath,
                    extracted_text=result.get("extracted_text", ""),
                    is_complete_meaning=int(result.get("is_complete", False))
                )
                db.add(new_image)
                db.commit()
                logger.info(f"Successfully processed and saved image: {filepath}")
            except Exception as e:
                logger.error(f"Error analyzing image {filepath}: {e}")
                
        finally:
            db.close()

    def on_created(self, event):
        self.process(event)
        
    def on_modified(self, event):
        # Depending on how files are copied, they might trigger modified instead of created
        self.process(event)

class DirectoryWatcher:
    def __init__(self):
        self.observer = None
        self.thread = None
        self.watching_path = None
        
    def start(self, path: str):
        if self.observer:
            self.stop()
            
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            
        self.watching_path = path
        logger.info(f"Starting directory watcher on: {path}")
        
        loop = asyncio.get_event_loop()
        event_handler = ImageEventHandler(loop)
        
        self.observer = Observer()
        self.observer.schedule(event_handler, path, recursive=False)
        self.observer.start()
        
    def stop(self):
        if self.observer:
            logger.info("Stopping directory watcher...")
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.watching_path = None

# Global watcher instance
watcher = DirectoryWatcher()
