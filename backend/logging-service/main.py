"""
Logging Service - Centralized Logging & Event Management
Port: 8005
Database: logs_db
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, List, AsyncGenerator
import logging
from dotenv import load_dotenv
from enum import Enum
import uuid

# SQLAlchemy imports
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, DateTime, Text, select
from sqlalchemy.dialects.postgresql import UUID

load_dotenv()

# ============= CONFIGURATION =============
app = FastAPI(title="Logging Service", version="1.0.0")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "azerty5027")
DB_NAME = os.getenv("DB_NAME_LOGS", "logs_db")

# SQLAlchemy Database URL
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "*"],  # Wider CORS for logging
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= ENUMS & MODELS =============
class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class LogRequest(BaseModel):
    service: str
    event: str
    level: str
    message: str
    timestamp: Optional[str] = None

class LogResponse(BaseModel):
    id: str
    service: str
    event: str
    level: str
    message: str
    timestamp: str
    color: Optional[str] = None  # For frontend display

# ============= DATABASE MODELS & CONNECTION =============
Base = declarative_base()

class Log(Base):
    __tablename__ = "logs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

# SQLAlchemy Engine and Session
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Initialize database tables"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ Database tables initialized successfully")
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        raise

# ============= HELPERS =============
def get_log_color(level: str) -> str:
    """Get color code for log level for admin UI"""
    colors = {
        "DEBUG": "#6B7280",      # Gray
        "INFO": "#3B82F6",       # Blue
        "WARNING": "#F59E0B",    # Amber/Orange
        "ERROR": "#EF4444",      # Red
        "CRITICAL": "#DC2626"    # Dark Red
    }
    return colors.get(level, "#6B7280")

def verify_admin_token(token: str) -> dict:
    """Verify JWT token and check for admin role"""
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============= EVENTS =============
@app.on_event("startup")
async def startup():
    logger.info("Starting Logging Service...")
    await init_db()
    logger.info("✓ Logging Service started successfully")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down Logging Service...")
    await engine.dispose()
    logger.info("✓ Database connections closed")

# ============= ENDPOINTS =============
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "logging-service"}

@app.post("/log", response_model=LogResponse)
async def create_log(log_data: LogRequest, db: AsyncSession = Depends(get_db)):
    """Log event from any service (internal endpoint)"""
    try:
        # Parse timestamp
        if log_data.timestamp:
            ts = datetime.fromisoformat(log_data.timestamp.replace('Z', '+00:00'))
        else:
            ts = datetime.utcnow()
        
        new_log = Log(
            service=log_data.service,
            event=log_data.event,
            level=log_data.level,
            message=log_data.message,
            timestamp=ts
        )
        db.add(new_log)
        await db.flush()
        await db.refresh(new_log)
        
        # Also log to stdout for monitoring
        log_func = {
            "DEBUG": logger.debug,
            "INFO": logger.info,
            "WARNING": logger.warning,
            "ERROR": logger.error,
            "CRITICAL": logger.critical
        }.get(log_data.level, logger.info)
        
        log_func(f"[{log_data.service}] {log_data.event}: {log_data.message}")
        
        return LogResponse(
            id=str(new_log.id),
            service=new_log.service,
            event=new_log.event,
            level=new_log.level,
            message=new_log.message,
            timestamp=new_log.timestamp.isoformat()
        )
            
    except Exception as e:
        logger.error(f"Failed to create log: {e}")
        # Don't raise exception - logging service should never fail the system
        return {"id": "error", "service": "logging", "event": "error", 
                "level": "ERROR", "message": str(e), "timestamp": datetime.utcnow().isoformat()}

@app.get("/log/all", response_model=List[LogResponse])
async def get_all_logs(
    authorization: str = Header(...),
    service: Optional[str] = None,
    level: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all logs (admin only)"""
    try:
        verify_admin_token(authorization)
        
        # Build query dynamically
        query = select(Log).order_by(Log.timestamp.desc())
        
        if service:
            query = query.where(Log.service == service)
        
        if level:
            query = query.where(Log.level == level)
        
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return [
            LogResponse(
                id=str(log.id),
                service=log.service,
                event=log.event,
                level=log.level,
                message=log.message,
                timestamp=log.timestamp.isoformat(),
                color=get_log_color(log.level)
            )
            for log in logs
        ]
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get logs error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve logs")

@app.get("/log/stats")
async def get_log_statistics(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get logging statistics (admin only)"""
    try:
        verify_admin_token(authorization)
        
        # Get all logs for stats
        result = await db.execute(select(Log))
        all_logs = result.scalars().all()
        
        # Calculate stats
        by_service = {}
        by_level = {}
        
        for log in all_logs:
            # By service
            key = f"{log.service}_{log.level}"
            by_service[key] = by_service.get(key, 0) + 1
            
            # By level
            by_level[log.level] = by_level.get(log.level, 0) + 1
        
        # Get recent errors
        error_result = await db.execute(
            select(Log)
            .where(Log.level.in_(["ERROR", "CRITICAL"]))
            .order_by(Log.timestamp.desc())
            .limit(10)
        )
        recent_errors = error_result.scalars().all()
        
        return {
            "total_logs": len(all_logs),
            "by_level": [
                {"level": level, "count": count, "color": get_log_color(level)}
                for level, count in sorted(by_level.items(), key=lambda x: x[1], reverse=True)
            ],
            "recent_errors": [
                {
                    "id": str(log.id),
                    "service": log.service,
                    "event": log.event,
                    "level": log.level,
                    "message": log.message,
                    "timestamp": log.timestamp.isoformat(),
                    "color": get_log_color(log.level)
                }
                for log in recent_errors
            ]
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")

@app.delete("/log/cleanup")
async def cleanup_old_logs(
    authorization: str = Header(...),
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """Delete logs older than specified days (admin only)"""
    try:
        verify_admin_token(authorization)
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get logs to delete
        result = await db.execute(
            select(Log).where(Log.timestamp < cutoff_date)
        )
        logs_to_delete = result.scalars().all()
        
        # Delete them
        for log in logs_to_delete:
            await db.delete(log)
        
        await db.flush()
        
        deleted_count = len(logs_to_delete)
        logger.info(f"Cleaned up {deleted_count} logs older than {days} days")
        
        return {
            "message": f"Deleted logs older than {days} days",
            "deleted_count": deleted_count
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup logs")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)