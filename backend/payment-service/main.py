"""
Payment Service - Payment Processing & Management
Port: 8003
Database: payments_db
"""

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator
import logging
from dotenv import load_dotenv
import httpx
from enum import Enum
import uuid
import tenacity
from decimal import Decimal

# SQLAlchemy imports
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, DateTime, Numeric, select
from sqlalchemy.dialects.postgresql import UUID

load_dotenv()

# ============= CONFIGURATION =============
app = FastAPI(title="Payment Service", version="1.0.0")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "azerty5027")
DB_NAME = os.getenv("DB_NAME_PAYMENTS", "payments_db")

LOGGING_SERVICE_URL = os.getenv("LOGGING_SERVICE_URL", "http://localhost:8005")
APPOINTMENT_SERVICE_URL = os.getenv("APPOINTMENT_SERVICE_URL", "http://localhost:8002")

# SQLAlchemy Database URL
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= ENUMS & MODELS =============
class PaymentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REFUNDED = "refunded"

class PaymentRequest(BaseModel):
    appointment_id: str
    amount: float
    payment_type: str = "reservation"  # reservation or inspection_fee
    
    @validator("amount")
    def amount_valid(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        if v > 10000:
            raise ValueError("Amount exceeds maximum limit")
        return round(v, 2)
    
    @validator("payment_type")
    def payment_type_valid(cls, v):
        if v not in ["reservation", "inspection_fee"]:
            raise ValueError("payment_type must be 'reservation' or 'inspection_fee'")
        return v

class PaymentResponse(BaseModel):
    id: str
    appointment_id: str
    user_id: str
    amount: float
    status: str
    created_at: str

class PaymentConfirm(BaseModel):
    payment_id: str
    status: str = "confirmed"
    transaction_id: Optional[str] = None

# ============= DATABASE MODELS & CONNECTION =============
Base = declarative_base()

class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    payment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="reservation", index=True)  # reservation or inspection_fee
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)  # For facturation
    transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        raise

# ============= HELPERS =============
async def log_event(service: str, event: str, level: str, message: str):
    """Send log to Logging Service (async, non-blocking)"""
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

def verify_token(token: str) -> dict:
    """Verify JWT token"""
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    stop=tenacity.stop_after_attempt(3),
    reraise=True
)
async def update_appointment_status(appointment_id: str, payment_id: str, token: str):
    """Update appointment status in Appointment Service with retry"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.put(
            f"{APPOINTMENT_SERVICE_URL}/appointments/{appointment_id}/confirm",
            json={"payment_id": payment_id},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to confirm appointment")
        
        return response.json()

# ============= EVENTS =============
@app.on_event("startup")
async def startup():
    logger.info("Starting Payment Service...")
    await init_db()
    logger.info("✓ Payment Service started successfully")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down Payment Service...")
    await engine.dispose()
    logger.info("✓ Database connections closed")

# ============= ENDPOINTS =============
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "payment-service"}

@app.post("/payment", response_model=PaymentResponse)
async def create_payment(
    request: PaymentRequest,
    authorization: str = Header(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """Initiate payment for appointment"""
    try:
        user = verify_token(authorization)
        user_id = user.get("user_id")
        
        # Generate invoice number for inspection fees
        invoice_number = None
        if request.payment_type == "inspection_fee":
            invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        # Create payment record
        new_payment = Payment(
            appointment_id=uuid.UUID(request.appointment_id),
            user_id=uuid.UUID(user_id),
            amount=Decimal(str(request.amount)),
            status=PaymentStatus.PENDING.value,
            payment_type=request.payment_type,
            invoice_number=invoice_number
        )
        db.add(new_payment)
        await db.flush()
        await db.refresh(new_payment)
        
        payment_desc = "reservation" if request.payment_type == "reservation" else "inspection fee"
        await log_event("PaymentService", "payment.created", "INFO",
                      f"User {user.get('email')} initiated {payment_desc} payment {new_payment.id} of ${request.amount} for appointment {request.appointment_id} at {datetime.utcnow().isoformat()}")
        
        return PaymentResponse(
            id=str(new_payment.id),
            appointment_id=str(new_payment.appointment_id),
            user_id=str(new_payment.user_id),
            amount=float(new_payment.amount),
            status=new_payment.status,
            created_at=new_payment.created_at.isoformat()
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create payment error: {e}")
        await log_event("PaymentService", "payment.create_error", "ERROR", str(e))
        raise HTTPException(status_code=500, detail="Failed to create payment")

@app.post("/payment/confirm")
async def confirm_payment(
    payment_data: PaymentConfirm,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Confirm payment (webhook/callback from payment gateway)"""
    try:
        # Get payment record
        result = await db.execute(
            select(Payment).where(Payment.id == uuid.UUID(payment_data.payment_id))
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        # Update payment status
        payment.status = payment_data.status
        payment.transaction_id = payment_data.transaction_id
        payment.updated_at = datetime.utcnow()
        await db.flush()
        
        # Asynchronously confirm appointment (don't block payment confirmation)
        if payment_data.status == "confirmed":
            background_tasks.add_task(
                confirm_appointment_async,
                str(payment.appointment_id),
                payment_data.payment_id,
                user_id=str(payment.user_id)
            )
        
        await log_event("PaymentService", "payment.confirmed", "INFO",
                      f"Payment {payment_data.payment_id} confirmed with transaction {payment_data.transaction_id}")
        
        return {
            "message": "Payment confirmed",
            "payment_id": payment_data.payment_id,
            "status": payment.status
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Confirm payment error: {e}")
        await log_event("PaymentService", "payment.confirm_error", "ERROR", str(e))
        raise HTTPException(status_code=500, detail="Failed to confirm payment")

async def confirm_appointment_async(appointment_id: str, payment_id: str, user_id: str):
    """Background task to confirm appointment"""
    try:
        # Generate service token (in production, use service-to-service auth)
        service_token = jwt.encode(
            {
                "sub": "payment-service",
                "exp": datetime.utcnow() + timedelta(hours=1)
            },
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM
        )
        
        await update_appointment_status(appointment_id, payment_id, service_token)
        logger.info(f"✓ Appointment {appointment_id} confirmed")
        
    except Exception as e:
        logger.error(f"Failed to confirm appointment: {e}")
        await log_event("PaymentService", "appointment.confirm_failed", "ERROR",
                      f"Failed to confirm appointment {appointment_id}: {str(e)}")

@app.get("/payment/status/{payment_id}")
async def get_payment_status(
    payment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Check payment status"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Payment).where(Payment.id == uuid.UUID(payment_id))
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        return PaymentResponse(
            id=str(payment.id),
            appointment_id=str(payment.appointment_id),
            user_id=str(payment.user_id),
            amount=float(payment.amount),
            status=payment.status,
            created_at=payment.created_at.isoformat()
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get payment status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve payment status")

@app.get("/payment/{payment_id}")
async def get_payment(
    payment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get complete payment information by ID"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Payment).where(Payment.id == uuid.UUID(payment_id))
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        return {
            "id": str(payment.id),
            "appointment_id": str(payment.appointment_id),
            "user_id": str(payment.user_id),
            "amount": float(payment.amount),
            "status": payment.status,
            "payment_type": payment.payment_type,
            "invoice_number": payment.invoice_number,
            "transaction_id": payment.transaction_id,
            "created_at": payment.created_at.isoformat(),
            "updated_at": payment.updated_at.isoformat()
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get payment error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve payment")

@app.post("/payment/{payment_id}/confirm-simulated")
async def confirm_payment_simulated(
    payment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Confirm payment (SIMULATED for educational purposes - not real payment)"""
    try:
        user = verify_token(authorization)
        
        # Find payment
        result = await db.execute(
            select(Payment).where(Payment.id == uuid.UUID(payment_id))
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        # Verify ownership
        if str(payment.user_id) != user.get("user_id"):
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        if payment.status == PaymentStatus.CONFIRMED.value:
            return {
                "message": "Payment already confirmed",
                "payment_id": str(payment.id),
                "status": payment.status
            }
        
        # SIMULATED PAYMENT PROCESSING
        # In real app, this would integrate with Stripe/PayPal/etc.
        payment.status = PaymentStatus.CONFIRMED.value
        await db.flush()
        
        await log_event("PaymentService", "payment.confirmed", "INFO",
                      f"User {user.get('email')} confirmed payment {payment_id} (SIMULATED) at {datetime.utcnow().isoformat()}")
        
        # Confirm appointment automatically
        try:
            # Generate service token for inter-service communication
            service_token = jwt.encode(
                {
                    "sub": "payment-service",
                    "user_id": str(payment.user_id),
                    "role": "service",
                    "exp": datetime.utcnow() + timedelta(hours=1)
                },
                JWT_SECRET_KEY,
                algorithm=JWT_ALGORITHM
            )
            
            await update_appointment_status(
                str(payment.appointment_id),
                str(payment.id),
                service_token
            )
            await log_event("PaymentService", "appointment.auto_confirmed", "INFO",
                          f"Appointment {payment.appointment_id} auto-confirmed after payment {payment_id}")
        except Exception as e:
            logger.error(f"Failed to confirm appointment: {e}")
            await log_event("PaymentService", "appointment.confirm_failed", "ERROR",
                          f"Failed to confirm appointment {payment.appointment_id}: {str(e)}")
        
        return {
            "message": "Payment confirmed successfully (SIMULATED)",
            "payment_id": str(payment.id),
            "appointment_id": str(payment.appointment_id),
            "amount": float(payment.amount),
            "status": payment.status,
            "note": "This is a simulated payment for educational purposes only"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Confirm payment error: {e}")
        raise HTTPException(status_code=500, detail="Failed to confirm payment")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)