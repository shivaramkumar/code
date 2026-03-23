from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from db.models import get_db, DocumentCache
from db.cache import store_context

router = APIRouter()

@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Read the content
    content = await file.read()
    text = content.decode('utf-8')
    
    # Store in metadata DB
    doc = DocumentCache(filename=file.filename, content=text)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # Store in ChromaDB vector cache
    store_context(text, file.filename)
    
    return {"message": "Context uploaded and initialized for semantic retrieval", "id": doc.id}

@router.get("/documents")
def get_documents(db: Session = Depends(get_db)):
    docs = db.query(DocumentCache).all()
    return [{"id": d.id, "filename": d.filename, "uploaded_at": d.uploaded_at} for d in docs]
