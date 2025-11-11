"""
Authorization Service - Authentication & Token Management
Port: 8001
Database: auth_db
"""

from fastapi import FastAPI, HTTPException, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, field_validator
import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
import bcrypt
import logging
from dotenv import load_dotenv
import httpx

# SQLAlchemy imports
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Boolean, DateTime, select, func, text
from sqlalchemy.dialects.postgresql import UUID
import uuid

load_dotenv()

# ============= CONFIGURATION =============

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# Session timeout in minutes (default: 15 minutes, configurable by admin)
DEFAULT_SESSION_TIMEOUT_MINUTES = int(os.getenv("DEFAULT_SESSION_TIMEOUT_MINUTES", "15"))
MAX_SESSION_TIMEOUT_MINUTES = int(os.getenv("MAX_SESSION_TIMEOUT_MINUTES", "1440"))  # 24 hours max

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "azerty5027")
DB_NAME = os.getenv("DB_NAME_AUTH", "auth_db")

# For local development, use localhost instead of service names
LOGGING_SERVICE_URL = os.getenv("LOGGING_SERVICE_URL", "http://localhost:8005")

# SQLAlchemy Database URL
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# CORS Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= DATA MODELS =============
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: str = "customer"
    first_name: Optional[str] = "User"
    last_name: Optional[str] = "Account"
    birthdate: Optional[str] = "1990-01-01"  # Format: YYYY-MM-DD
    country: Optional[str] = "Unknown"
    state: Optional[str] = None
    id_number: Optional[str] = None  # National ID or passport number
    
    @field_validator("password")
    @classmethod
    def password_valid(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
    
    @field_validator("role")
    @classmethod
    def role_valid(cls, v):
        valid_roles = ["customer", "technician", "admin"]
        if v not in valid_roles:
            raise ValueError(f"Role must be one of {valid_roles}")
        return v
    
    @field_validator("first_name", "last_name")
    @classmethod
    def name_valid(cls, v):
        if v and len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip() if v else v
    
    @field_validator("birthdate")
    @classmethod
    def birthdate_valid(cls, v):
        if not v or v == "1990-01-01":
            return v
        try:
            date_obj = datetime.strptime(v, "%Y-%m-%d")
            # Check if user is at least 18 years old
            age = (datetime.now() - date_obj).days // 365
            if age < 18:
                raise ValueError("You must be at least 18 years old")
            return v
        except ValueError as e:
            if "at least 18" in str(e):
                raise e
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
    
    @field_validator("id_number")
    @classmethod
    def id_valid(cls, v):
        if v and len(v) < 5:
            raise ValueError("ID number must be at least 5 characters")
        return v.strip() if v else v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    created_at: str

# ============= DATABASE MODELS & CONNECTION =============
Base = declarative_base()

class Account(Base):
    __tablename__ = "accounts"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="customer")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="User")
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="Account")
    birthdate: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="1990-01-01")  # YYYY-MM-DD
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="Unknown")
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    id_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True, index=True)
    session_timeout_minutes: Mapped[str] = mapped_column(String(10), nullable=True, default=str(DEFAULT_SESSION_TIMEOUT_MINUTES))  # Configurable session timeout
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        
        # Try to add new columns if they don't exist (for backward compatibility)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("""
                    DO $$ 
                    BEGIN
                        -- Add first_name if it doesn't exist
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='accounts' AND column_name='first_name') THEN
                            ALTER TABLE accounts ADD COLUMN first_name VARCHAR(100) DEFAULT 'User';
                        END IF;
                        
                        -- Add last_name if it doesn't exist
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='accounts' AND column_name='last_name') THEN
                            ALTER TABLE accounts ADD COLUMN last_name VARCHAR(100) DEFAULT 'Account';
                        END IF;
                        
                        -- Add birthdate if it doesn't exist
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='accounts' AND column_name='birthdate') THEN
                            ALTER TABLE accounts ADD COLUMN birthdate VARCHAR(10) DEFAULT '1990-01-01';
                        END IF;
                        
                        -- Add country if it doesn't exist
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='accounts' AND column_name='country') THEN
                            ALTER TABLE accounts ADD COLUMN country VARCHAR(100) DEFAULT 'Unknown';
                        END IF;
                        
                        -- Add state if it doesn't exist
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='accounts' AND column_name='state') THEN
                            ALTER TABLE accounts ADD COLUMN state VARCHAR(100);
                        END IF;
                        
                        -- Add id_number if it doesn't exist
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='accounts' AND column_name='id_number') THEN
                            ALTER TABLE accounts ADD COLUMN id_number VARCHAR(100) UNIQUE;
                            CREATE INDEX IF NOT EXISTS idx_accounts_id_number ON accounts(id_number);
                        END IF;
                        
                        -- Add session_timeout_minutes if it doesn't exist
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='accounts' AND column_name='session_timeout_minutes') THEN
                            ALTER TABLE accounts ADD COLUMN session_timeout_minutes VARCHAR(10) DEFAULT '15';
                        END IF;
                    END $$;
                """))
            logger.info("✓ Database schema migration completed successfully")
        except Exception as migration_error:
            logger.warning(f"⚠ Database migration warning (may be normal if columns exist): {migration_error}")
            
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        raise

# ============= HELPER FUNCTIONS =============
async def log_event(service: str, event: str, level: str, message: str):
    """Send log to Logging Service (non-blocking)"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{LOGGING_SERVICE_URL}/log",
                json={
                    "service": service,
                    "event": event,
                    "level": level,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
    except Exception as e:
        logger.warning(f"Failed to log event: {e}")

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_access_token(email: str, role: str, user_id: str, session_timeout_minutes: int = DEFAULT_SESSION_TIMEOUT_MINUTES) -> str:
    """Create JWT token with configurable session timeout"""
    payload = {
        "email": email,
        "role": role,
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=session_timeout_minutes),
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token

def verify_token(token: str) -> dict:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============= LIFESPAN & APP =============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    logger.info("Starting Authorization Service...")
    await init_db()
    logger.info("[OK] Authorization Service started successfully")
    yield
    # Shutdown
    logger.info("Shutting down Authorization Service...")
    await engine.dispose()
    logger.info("[OK] Database connections closed")

# Create FastAPI app with lifespan
app = FastAPI(title="Authorization Service", version="1.0.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= ENDPOINTS =============
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "auth-service", "timestamp": datetime.utcnow().isoformat()}

@app.get("/verify")
async def verify_token_endpoint(authorization: str = Header(...)):
    """Verify if a token is valid"""
    try:
        token = authorization.replace("Bearer ", "")
        payload = verify_token(token)
        return {"valid": True, "user": payload}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.post("/register", response_model=UserResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register new user (customers only - technicians must be created by admin)"""
    try:
        # Prevent direct technician or admin registration
        if request.role in ["technician", "admin"]:
            await log_event("AuthService", "register.blocked", "WARNING",
                          f"Attempted to register as {request.role} from public endpoint")
            raise HTTPException(
                status_code=403,
                detail="Cannot register as technician or admin. Please contact an administrator."
            )
        
        # Check if user already exists
        result = await db.execute(
            select(Account).where(Account.email == request.email)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            await log_event("AuthService", "register.failed", "WARNING", 
                          f"User {request.email} already exists")
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password
        password_hash = hash_password(request.password)
        
        # Force role to customer for public registration
        new_user = Account(
            email=request.email,
            password_hash=password_hash,
            role="customer",
            first_name=request.first_name,
            last_name=request.last_name,
            birthdate=request.birthdate,
            country=request.country,
            state=request.state,
            id_number=request.id_number
        )
        db.add(new_user)
        await db.flush()
        await db.refresh(new_user)
        
        await log_event("AuthService", "user.registered", "INFO",
                      f"User {request.email} registered as customer at {datetime.utcnow().isoformat()}")
        
        return UserResponse(
            id=str(new_user.id),
            email=new_user.email,
            role=new_user.role,
            created_at=new_user.created_at.isoformat()
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await log_event("AuthService", "register.error", "ERROR", str(e))
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token"""
    try:
        # Find user
        result = await db.execute(
            select(Account).where(Account.email == request.email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await log_event("AuthService", "login.failed", "WARNING",
                          f"Login attempt for non-existent user: {request.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        if not verify_password(request.password, user.password_hash):
            await log_event("AuthService", "login.failed", "WARNING",
                          f"Failed password for user: {request.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create token with user's session timeout setting
        session_timeout = int(user.session_timeout_minutes) if user.session_timeout_minutes else DEFAULT_SESSION_TIMEOUT_MINUTES
        token = create_access_token(
            email=user.email,
            role=user.role,
            user_id=str(user.id),
            session_timeout_minutes=session_timeout
        )
        
        await log_event("AuthService", "login.success", "INFO",
                      f"User {request.email} (role: {user.role}) logged in at {datetime.utcnow().isoformat()}")
        
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user={
                "id": str(user.id),
                "email": user.email,
                "role": user.role
            }
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        await log_event("AuthService", "login.error", "ERROR", str(e))
        raise HTTPException(status_code=500, detail="Login failed")

@app.post("/verify")
async def verify_email(email: EmailStr, code: str, db: AsyncSession = Depends(get_db)):
    """Verify email (optional feature)"""
    try:
        # TODO: Check verification code (implement email service)
        result = await db.execute(
            select(Account).where(Account.email == email)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.is_verified = True
            await db.flush()
            
            await log_event("AuthService", "email.verified", "INFO",
                          f"Email verified for {email}")
            
            return {"message": "Email verified successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verification error: {e}")
        raise HTTPException(status_code=500, detail="Verification failed")

@app.get("/public_key")
async def get_public_key():
    """Get public key for token verification"""
    # For HS256, this is just the algorithm info
    return {
        "algorithm": JWT_ALGORITHM,
        "key_type": "symmetric"
    }

@app.post("/validate-token")
async def validate_token(token: str = Header(..., alias="Authorization")):
    """Validate JWT token (used by other services)"""
    try:
        # Remove "Bearer " prefix
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = verify_token(token)
        return {"valid": True, "payload": payload}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============= ADMIN ENDPOINTS =============
@app.get("/admin/users")
async def get_all_users(
    authorization: str = Header(...),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all users (admin only)"""
    try:
        user = verify_token(authorization.replace("Bearer ", ""))
        
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        result = await db.execute(
            select(Account)
            .order_by(Account.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        users = result.scalars().all()
        
        await log_event("AuthService", "admin.view_users", "INFO",
                      f"Admin {user.get('email')} viewed user list at {datetime.utcnow().isoformat()}")
        
        return [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "is_verified": u.is_verified,
                "created_at": u.created_at.isoformat()
            }
            for u in users
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get users error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve users")

@app.post("/admin/users/create-technician")
async def create_technician(
    request: RegisterRequest,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Create technician account (admin only)"""
    try:
        user = verify_token(authorization.replace("Bearer ", ""))
        
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Check if user already exists
        result = await db.execute(
            select(Account).where(Account.email == request.email)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password
        password_hash = hash_password(request.password)
        
        # Create technician with required fields
        new_technician = Account(
            email=request.email,
            password_hash=password_hash,
            role="technician",
            first_name=request.first_name,
            last_name=request.last_name,
            birthdate=request.birthdate,
            country=request.country,
            state=request.state,
            id_number=request.id_number
        )
        db.add(new_technician)
        await db.flush()
        await db.refresh(new_technician)
        
        await log_event("AuthService", "admin.create_technician", "INFO",
                      f"Admin {user.get('email')} created technician account {request.email} at {datetime.utcnow().isoformat()}")
        
        return {
            "id": str(new_technician.id),
            "email": new_technician.email,
            "role": new_technician.role,
            "created_at": new_technician.created_at.isoformat()
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create technician error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create technician")

@app.put("/admin/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    new_role: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Change user role (admin only)"""
    try:
        admin_user = verify_token(authorization.replace("Bearer ", ""))
        
        if admin_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Validate role
        if new_role not in ["customer", "technician", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        
        # Find user
        result = await db.execute(
            select(Account).where(Account.id == uuid.UUID(user_id))
        )
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        old_role = target_user.role
        target_user.role = new_role
        await db.flush()
        
        await log_event("AuthService", "admin.change_role", "INFO",
                      f"Admin {admin_user.get('email')} changed {target_user.email} role from {old_role} to {new_role} at {datetime.utcnow().isoformat()}")
        
        return {
            "id": str(target_user.id),
            "email": target_user.email,
            "old_role": old_role,
            "new_role": new_role,
            "updated_at": datetime.utcnow().isoformat()
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change role error: {e}")
        raise HTTPException(status_code=500, detail="Failed to change user role")

@app.put("/admin/users/{user_id}/session-timeout")
async def update_session_timeout(
    user_id: str,
    timeout_minutes: int,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Update user's session timeout (admin only)"""
    try:
        admin_user = verify_token(authorization.replace("Bearer ", ""))
        
        if admin_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Validate timeout
        if timeout_minutes < 5:
            raise HTTPException(status_code=400, detail="Session timeout must be at least 5 minutes")
        if timeout_minutes > MAX_SESSION_TIMEOUT_MINUTES:
            raise HTTPException(status_code=400, detail=f"Session timeout cannot exceed {MAX_SESSION_TIMEOUT_MINUTES} minutes (24 hours)")
        
        # Find user
        result = await db.execute(
            select(Account).where(Account.id == uuid.UUID(user_id))
        )
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        old_timeout = target_user.session_timeout_minutes
        target_user.session_timeout_minutes = str(timeout_minutes)
        await db.flush()
        
        await log_event("AuthService", "admin.update_session_timeout", "INFO",
                      f"Admin {admin_user.get('email')} changed {target_user.email} session timeout from {old_timeout} to {timeout_minutes} minutes at {datetime.utcnow().isoformat()}")
        
        return {
            "id": str(target_user.id),
            "email": target_user.email,
            "old_timeout_minutes": old_timeout,
            "new_timeout_minutes": timeout_minutes,
            "updated_at": datetime.utcnow().isoformat()
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update session timeout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session timeout")

@app.get("/admin/session-config")
async def get_session_config(
    authorization: str = Header(...)
):
    """Get session configuration (admin only)"""
    try:
        admin_user = verify_token(authorization.replace("Bearer ", ""))
        
        if admin_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        return {
            "default_timeout_minutes": DEFAULT_SESSION_TIMEOUT_MINUTES,
            "max_timeout_minutes": MAX_SESSION_TIMEOUT_MINUTES,
            "min_timeout_minutes": 5
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session config error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve session configuration")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)