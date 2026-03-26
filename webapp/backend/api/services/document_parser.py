import os
import io
import csv
import aiofiles
from fastapi import UploadFile, HTTPException
from typing import Optional

# For PDF processing
try:
    import pypdf
except ImportError:
    pypdf = None

# For Image processing
from .image_analyzer import analyze_image

async def _extract_text(content: bytes) -> str:
    """Extract standard UTF-8 text."""
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError("Failed to decode as UTF-8 text.")

async def _extract_csv(content: bytes) -> str:
    """Extract structured data from CSV."""
    text_content = content.decode('utf-8', errors='ignore')
    reader = csv.reader(io.StringIO(text_content))
    extracted = []
    for row in reader:
        extracted.append(" | ".join(row))
    return "\n".join(extracted)

async def _extract_pdf(content: bytes) -> str:
    """Extract text from PDF pages."""
    if not pypdf:
        raise HTTPException(status_code=500, detail="PDF parser 'pypdf' is not installed.")
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")

async def _extract_image(file: UploadFile, content: bytes) -> str:
    """Extract text from image using Vision models."""
    temp_path = f"/tmp/{file.filename}"
    try:
        # Write to temp file for image_analyzer
        async with aiofiles.open(temp_path, 'wb') as out_file:
            await out_file.write(content)
            
        result = await analyze_image(temp_path)
        desc = result.get("visual_description", "No visual description provided.")
        text = result.get("extracted_text", "")
        return f"Description: {desc}\nExtracted Text: {text}"
    except Exception as e:
        raise ValueError(f"Failed to parse Image: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

async def extract_from_upload(file: UploadFile) -> str:
    """Identify the document type and extract text using the appropriate method."""
    content = await file.read()
    filename = file.filename.lower()
    
    try:
        header = f"[Document Content ({file.filename}) - Type: {file.filename.split('.')[-1].upper()}]\n"
        if filename.endswith(".pdf"):
            body = await _extract_pdf(content)
        elif filename.endswith(".csv"):
            body = await _extract_csv(content)
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            body = await _extract_image(file, content)
            header = f"[Image Description/Text ({file.filename})]\n"
        else:
            # Fallback to standard Text extraction (md, txt, json, etc)
            body = await _extract_text(content)
        
        return f"{header}{body}"
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during extraction: {str(e)}")
