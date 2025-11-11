# File Upload Service - Vehicle Photos
# Handles photo uploads for inspections with compression and storage

import os
import uuid
import shutil
from datetime import datetime
from typing import Optional, List
from pathlib import Path
import base64

from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import String, DateTime, Integer, select, UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= CONFIGURATION =============
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ============= DATABASE SETUP =============
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "azerty5027")
DB_NAME = os.getenv("DB_NAME_FILES", "files_db")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class FileUpload(Base):
    __tablename__ = "file_uploads"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Related entities
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    photo_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # before, after, damage, defect
    
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# Database dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# ============= FASTAPI APP =============
app = FastAPI(title="File Upload Service")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= STARTUP/SHUTDOWN =============
@app.on_event("startup")
async def startup():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ File upload database initialized successfully")
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        raise

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    logger.info("✓ Database connections closed")

# ============= HELPER FUNCTIONS =============
def validate_file(file: UploadFile) -> bool:
    """Validate file extension and size"""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    return True

def get_file_category(appointment_id: Optional[str], inspection_id: Optional[str]) -> str:
    """Determine file storage category"""
    if inspection_id:
        return "inspections"
    elif appointment_id:
        return "appointments"
    return "general"

# ============= ENDPOINTS =============
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "file-service"}

@app.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    uploaded_by: str = Form(...),
    appointment_id: Optional[str] = Form(None),
    inspection_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo_type: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Upload a file (photo)"""
    try:
        # Validate file
        validate_file(file)
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB"
            )
        
        # Generate unique filename
        file_id = uuid.uuid4()
        ext = Path(file.filename).suffix.lower()
        category = get_file_category(appointment_id, inspection_id)
        
        # Create category directory
        category_dir = UPLOAD_DIR / category
        category_dir.mkdir(exist_ok=True)
        
        # Save file
        filename = f"{file_id}{ext}"
        file_path = category_dir / filename
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Create database record
        file_record = FileUpload(
            id=file_id,
            filename=filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_size=file_size,
            content_type=file.content_type,
            appointment_id=uuid.UUID(appointment_id) if appointment_id else None,
            inspection_id=uuid.UUID(inspection_id) if inspection_id else None,
            uploaded_by=uuid.UUID(uploaded_by),
            description=description,
            photo_type=photo_type
        )
        
        db.add(file_record)
        await db.commit()
        await db.refresh(file_record)
        
        logger.info(f"📷 File uploaded: {file.filename} ({file_size} bytes) by user {uploaded_by}")
        
        return {
            "success": True,
            "file_id": str(file_record.id),
            "filename": file_record.filename,
            "file_size": file_record.file_size,
            "url": f"/files/{file_record.id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.get("/files/{file_id}")
async def get_file(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get file by ID"""
    try:
        result = await db.execute(
            select(FileUpload).where(FileUpload.id == uuid.UUID(file_id))
        )
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path = Path(file_record.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        return FileResponse(
            path=file_path,
            media_type=file_record.content_type,
            filename=file_record.original_filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/appointment/{appointment_id}")
async def get_appointment_files(
    appointment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all files for an appointment"""
    try:
        result = await db.execute(
            select(FileUpload).where(
                FileUpload.appointment_id == uuid.UUID(appointment_id)
            ).order_by(FileUpload.uploaded_at.desc())
        )
        files = result.scalars().all()
        
        return {
            "appointment_id": appointment_id,
            "total_files": len(files),
            "files": [
                {
                    "id": str(f.id),
                    "filename": f.original_filename,
                    "description": f.description,
                    "photo_type": f.photo_type,
                    "file_size": f.file_size,
                    "uploaded_at": f.uploaded_at.isoformat(),
                    "url": f"/files/{f.id}"
                }
                for f in files
            ]
        }
        
    except Exception as e:
        logger.error(f"Error fetching appointment files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/inspection/{inspection_id}")
async def get_inspection_files(
    inspection_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all files for an inspection"""
    try:
        result = await db.execute(
            select(FileUpload).where(
                FileUpload.inspection_id == uuid.UUID(inspection_id)
            ).order_by(FileUpload.uploaded_at.desc())
        )
        files = result.scalars().all()
        
        return {
            "inspection_id": inspection_id,
            "total_files": len(files),
            "files": [
                {
                    "id": str(f.id),
                    "filename": f.original_filename,
                    "description": f.description,
                    "photo_type": f.photo_type,
                    "file_size": f.file_size,
                    "uploaded_at": f.uploaded_at.isoformat(),
                    "url": f"/files/{f.id}"
                }
                for f in files
            ]
        }
        
    except Exception as e:
        logger.error(f"Error fetching inspection files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a file"""
    try:
        result = await db.execute(
            select(FileUpload).where(FileUpload.id == uuid.UUID(file_id))
        )
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Delete physical file
        file_path = Path(file_record.file_path)
        if file_path.exists():
            file_path.unlink()
        
        # Delete database record
        await db.delete(file_record)
        await db.commit()
        
        logger.info(f"🗑️ File deleted: {file_record.filename}")
        
        return {"success": True, "message": "File deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get file upload statistics"""
    try:
        from sqlalchemy import func
        
        # Total files
        total_result = await db.execute(select(func.count()).select_from(FileUpload))
        total_files = total_result.scalar()
        
        # Total size
        size_result = await db.execute(select(func.sum(FileUpload.file_size)).select_from(FileUpload))
        total_size = size_result.scalar() or 0
        
        # By type
        type_result = await db.execute(
            select(FileUpload.photo_type, func.count()).group_by(FileUpload.photo_type)
        )
        by_type = {row[0] or "unspecified": row[1] for row in type_result}
        
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "by_type": by_type
        }
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
