"""
Appointment Management Service - Appointment CRUD & Management
Port: 8002
Database: appointments_db
"""

from fastapi import FastAPI, HTTPException, Header, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
import jwt
import os
from datetime import datetime, timedelta, date
from typing import Optional, List, AsyncGenerator
import logging
from dotenv import load_dotenv
import httpx
from enum import Enum
import uuid
import io
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfgen import canvas

# SQLAlchemy imports
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, DateTime, select, JSON
from sqlalchemy.dialects.postgresql import UUID

load_dotenv()

# ============= CONFIGURATION =============
app = FastAPI(title="Appointment Management Service", version="1.0.0")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "azerty5027")
DB_NAME = os.getenv("DB_NAME_APPOINTMENTS", "appointments_db")

LOGGING_SERVICE_URL = os.getenv("LOGGING_SERVICE_URL", "http://localhost:8005")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8003")
INSPECTION_SERVICE_URL = os.getenv("INSPECTION_SERVICE_URL", "http://localhost:8004")

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
class AppointmentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class AppointmentRequest(BaseModel):
    vehicle_type: str
    vehicle_registration: str
    vehicle_brand: str
    vehicle_model: str
    appointment_date: Optional[str] = None
    
    @validator("vehicle_type")
    def validate_vehicle_type(cls, v):
        valid_types = ["car", "motorcycle", "truck", "van"]
        if v not in valid_types:
            raise ValueError(f"Vehicle type must be one of {valid_types}")
        return v.lower()
    
    @validator("vehicle_registration")
    def validate_registration(cls, v):
        if len(v) < 4:
            raise ValueError("Invalid registration")
        return v.upper()

class AppointmentResponse(BaseModel):
    id: str
    user_id: str
    vehicle_info: dict
    status: str
    payment_id: Optional[str]
    created_at: str
    appointment_date: Optional[str]

class AppointmentUpdate(BaseModel):
    payment_id: str
    status: str = "confirmed"

# ============= DATABASE MODELS & CONNECTION =============
Base = declarative_base()

class Appointment(Base):
    __tablename__ = "appointments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    vehicle_info: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    appointment_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    inspection_status: Mapped[str] = mapped_column(String(50), nullable=False, default="not_checked", index=True)  # not_checked, in_progress, passed, failed, passed_with_minor_issues
    inspection_payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)  # Separate payment for inspection invoice
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)

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
        except Exception as e:
            logger.error(f"Database session error: {e}", exc_info=True)
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
    """Send log to Logging Service"""
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
        logger.warning(f"Failed to log: {e}")

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

# ============= EVENTS =============
@app.on_event("startup")
async def startup():
    logger.info("Starting Appointment Service...")
    await init_db()
    logger.info("✓ Appointment Service started successfully")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down Appointment Service...")
    await engine.dispose()
    logger.info("✓ Database connections closed")

# ============= ENDPOINTS =============
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "appointment-service"}

@app.get("/test/db")
async def test_database(db: AsyncSession = Depends(get_db)):
    """Test database connectivity and SQLAlchemy ORM"""
    try:
        # Test 1: Simple count
        count_result = await db.execute(select(Appointment))
        all_appointments = count_result.scalars().all()
        
        # Test 2: Check UUID serialization
        corrupted = []
        sample_data = []
        for i, apt in enumerate(all_appointments[:3]):  # Only check first 3
            try:
                data = {
                    "id": str(apt.id),
                    "user_id": str(apt.user_id),
                    "payment_id": str(apt.payment_id) if apt.payment_id else None,
                    "status": apt.status
                }
                sample_data.append(data)
            except Exception as e:
                corrupted.append({"index": i, "error": str(e)})
        
        # Test 3: Try the exact query used in weekly_schedule
        from datetime import date
        test_date = date(2025, 10, 13)
        start_of_day = datetime.combine(test_date, datetime.min.time())
        end_of_day = datetime.combine(test_date, datetime.max.time())
        
        try:
            schedule_query = select(Appointment.appointment_date).where(
                Appointment.appointment_date >= start_of_day,
                Appointment.appointment_date <= end_of_day,
                Appointment.status.in_(["pending", "confirmed"])
            )
            schedule_result = await db.execute(schedule_query)
            schedule_appointments = [row[0] for row in schedule_result.all()]
            schedule_test = f"Found {len(schedule_appointments)} appointments for 2025-10-13"
        except Exception as schedule_error:
            schedule_test = f"ERROR: {str(schedule_error)}"
        
        return {
            "status": "ok",
            "message": "Database connected",
            "appointment_count": len(all_appointments),
            "corrupted_records": corrupted if corrupted else "None",
            "sample_data": sample_data,
            "schedule_query_test": schedule_test
        }
    except Exception as e:
        logger.error(f"Database test failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "error_type": type(e).__name__
        }

@app.post("/appointments", response_model=AppointmentResponse)
async def create_appointment(
    request: AppointmentRequest,
    authorization: str = Header(...),
    idempotency_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """Create new appointment"""
    try:
        user = verify_token(authorization)
        user_id = user.get("user_id")
        
        # Check for duplicate using idempotency key
        if idempotency_key:
            result = await db.execute(
                select(Appointment).where(Appointment.idempotency_key == idempotency_key)
            )
            existing = result.scalar_one_or_none()
            if existing:
                await log_event("AppointmentService", "appointment.idempotent_duplicate",
                              "INFO", f"Idempotent request with key {idempotency_key}")
                return AppointmentResponse(
                    id=str(existing.id),
                    user_id=str(existing.user_id),
                    vehicle_info=existing.vehicle_info,
                    status=existing.status,
                    payment_id=str(existing.payment_id) if existing.payment_id else None,
                    created_at=existing.created_at.isoformat(),
                    appointment_date=existing.appointment_date.isoformat() if existing.appointment_date else None
                )
        
        # Check for time slot conflicts (prevent double-booking)
        if request.appointment_date:
            requested_time = datetime.fromisoformat(request.appointment_date)
            
            # Check if this time slot is already taken
            conflict_check = await db.execute(
                select(Appointment)
                .where(
                    Appointment.appointment_date == requested_time,
                    Appointment.status.in_(["pending", "confirmed"])
                )
            )
            existing_appointment = conflict_check.scalar_one_or_none()
            
            if existing_appointment:
                await log_event("AppointmentService", "appointment.conflict", "WARNING",
                              f"Time slot {request.appointment_date} already booked")
                raise HTTPException(
                    status_code=409,
                    detail=f"Time slot {request.appointment_date} is already booked. Please choose another time."
                )
        
        # Create appointment
        vehicle_info = {
            "type": request.vehicle_type,
            "registration": request.vehicle_registration,
            "brand": request.vehicle_brand,
            "model": request.vehicle_model
        }
        
        new_appointment = Appointment(
            user_id=uuid.UUID(user_id),
            vehicle_info=vehicle_info,
            idempotency_key=idempotency_key,
            appointment_date=datetime.fromisoformat(request.appointment_date) if request.appointment_date else None
        )
        db.add(new_appointment)
        await db.flush()
        await db.refresh(new_appointment)
        
        await log_event("AppointmentService", "appointment.created", "INFO",
                      f"User {user.get('email')} created appointment {new_appointment.id} for vehicle {request.vehicle_registration} at {request.appointment_date} on {datetime.utcnow().isoformat()}")
        
        return AppointmentResponse(
            id=str(new_appointment.id),
            user_id=str(new_appointment.user_id),
            vehicle_info=new_appointment.vehicle_info,
            status=new_appointment.status,
            payment_id=None,
            created_at=new_appointment.created_at.isoformat(),
            appointment_date=new_appointment.appointment_date.isoformat() if new_appointment.appointment_date else None
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create appointment error: {e}", exc_info=True)
        try:
            await log_event("AppointmentService", "appointment.create_error", "ERROR", str(e))
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to create appointment: {str(e)}")

# NOTE: Specific routes MUST come before parameterized routes to avoid routing conflicts
# Order matters: /appointments/all, /appointments/weekly-schedule BEFORE /appointments/{user_id}

@app.get("/appointments/all")
async def get_all_appointments(
    authorization: str = Header(...),
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all appointments (admin/technician only) with optional status filter"""
    try:
        user = verify_token(authorization)
        logger.info(f"User accessing /appointments/all: {user.get('email')}, role: {user.get('role')}")
        
        # Only admin and technician can see all appointments
        if user.get("role") not in ["admin", "technician"]:
            logger.warning(f"Unauthorized access attempt by {user.get('email')} with role {user.get('role')}")
            raise HTTPException(status_code=403, detail=f"Unauthorized - role '{user.get('role')}' cannot access all appointments")
        
        query = select(Appointment).order_by(Appointment.created_at.desc())
        
        if status:
            query = query.where(Appointment.status == status)
        
        query = query.offset(skip).limit(limit)
        
        logger.info("Executing database query...")
        try:
            result = await db.execute(query)
            logger.info("Query executed, fetching results...")
            appointments = result.scalars().all()
            logger.info(f"Fetched {len(appointments)} appointments")
        except Exception as query_error:
            logger.error(f"Database query failed: {query_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database query failed: {str(query_error)}")
        
        logger.info("Serializing appointments...")
        try:
            return [
                {
                    "id": str(a.id),
                    "user_id": str(a.user_id),
                    "vehicle_info": a.vehicle_info,
                    "status": a.status,
                    "payment_id": str(a.payment_id) if a.payment_id else None,
                    "created_at": a.created_at.isoformat(),
                    "appointment_date": a.appointment_date.isoformat() if a.appointment_date else None
                }
                for a in appointments
            ]
        except Exception as serialize_error:
            logger.error(f"Serialization failed: {serialize_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Serialization failed: {str(serialize_error)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get all appointments error: {e}", exc_info=True)
        try:
            await log_event("AppointmentService", "appointments.all.error", "ERROR", f"Failed to get all appointments: {str(e)}")
        except:
            pass  # Don't let logging errors mask the real error
        raise HTTPException(status_code=500, detail=f"Failed to retrieve appointments: {str(e)}")

@app.get("/appointments/weekly-schedule")
async def get_weekly_schedule(
    start_date: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get weekly schedule view with 45-minute time slots for the week"""
    try:
        user = verify_token(authorization)
        
        # Parse start date
        try:
            week_start = datetime.fromisoformat(start_date).date()
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid date format: {start_date}, error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid date format: {start_date}. Expected: YYYY-MM-DD")
        
        # Generate 7 days
        weekly_data = []
        
        for day_offset in range(7):
            current_date = week_start + timedelta(days=day_offset)
            date_str = current_date.isoformat()
            
            # Get slots for this day
            time_slots = []
            start_hour = 9
            end_hour = 17
            
            current_time = datetime.combine(current_date, datetime.min.time().replace(hour=start_hour))
            end_time = datetime.combine(current_date, datetime.min.time().replace(hour=end_hour))
            
            while current_time < end_time:
                time_slots.append(current_time)
                current_time += timedelta(minutes=45)
            
            # Get booked appointments for this day
            start_of_day = datetime.combine(current_date, datetime.min.time())
            end_of_day = datetime.combine(current_date, datetime.max.time())
            
            try:
                result = await db.execute(
                    select(Appointment.appointment_date)
                    .where(
                        Appointment.appointment_date >= start_of_day,
                        Appointment.appointment_date <= end_of_day,
                        Appointment.status.in_(["pending", "confirmed"])
                    )
                )
                booked_appointments = [row[0] for row in result.all()]
            except Exception as db_error:
                logger.error(f"Database query error for date {current_date}: {db_error}", exc_info=True)
                booked_appointments = []
            
            # Build slots for this day
            day_slots = []
            for slot_time in time_slots:
                is_available = True
                for booked in booked_appointments:
                    if booked:
                        time_diff = abs((slot_time - booked).total_seconds() / 60)
                        if time_diff < 45:
                            is_available = False
                            break
                
                day_slots.append({
                    "time": slot_time.isoformat(),
                    "display": slot_time.strftime("%H:%M"),
                    "available": is_available
                })
            
            weekly_data.append({
                "date": date_str,
                "day_name": current_date.strftime("%A"),
                "slots": day_slots,
                "available_count": len([s for s in day_slots if s["available"]])
            })
        
        return {
            "week_start": start_date,
            "days": weekly_data,
            "slot_duration_minutes": 45,
            "working_hours": "09:00 - 17:00"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get weekly schedule error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve weekly schedule: {str(e)}")

@app.get("/appointments/my-vehicles")
async def get_my_vehicles(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get customer's vehicles with inspection status and payment info"""
    try:
        user = verify_token(authorization)
        user_id = user.get("user_id")
        
        # Get all appointments for this user
        result = await db.execute(
            select(Appointment)
            .where(Appointment.user_id == uuid.UUID(user_id))
            .order_by(Appointment.created_at.desc())
        )
        appointments = result.scalars().all()
        
        vehicles_data = []
        for apt in appointments:
            # Get payment info for reservation
            payment_info = None
            if apt.payment_id:
                async with httpx.AsyncClient(timeout=10) as client:
                    try:
                        payment_resp = await client.get(
                            f"{PAYMENT_SERVICE_URL}/payment/{str(apt.payment_id)}",
                            headers={"Authorization": f"Bearer {authorization.replace('Bearer ', '')}"}
                        )
                        if payment_resp.status_code == 200:
                            payment_info = payment_resp.json()
                    except:
                        pass
            
            # Get inspection payment info
            inspection_payment_info = None
            if apt.inspection_payment_id:
                async with httpx.AsyncClient(timeout=10) as client:
                    try:
                        insp_pay_resp = await client.get(
                            f"{PAYMENT_SERVICE_URL}/payment/{str(apt.inspection_payment_id)}",
                            headers={"Authorization": f"Bearer {authorization.replace('Bearer ', '')}"}
                        )
                        if insp_pay_resp.status_code == 200:
                            inspection_payment_info = insp_pay_resp.json()
                    except:
                        pass
            
            # Check if inspection report exists
            has_report = False
            if apt.inspection_status in ["passed", "failed", "passed_with_minor_issues"]:
                async with httpx.AsyncClient(timeout=10) as client:
                    try:
                        insp_resp = await client.get(
                            f"{INSPECTION_SERVICE_URL}/inspection/by-appointment/{str(apt.id)}",
                            headers={"Authorization": f"Bearer {authorization.replace('Bearer ', '')}"}
                        )
                        if insp_resp.status_code == 200:
                            has_report = True
                    except:
                        pass
            
            vehicles_data.append({
                "id": str(apt.id),
                "vehicle_info": apt.vehicle_info,
                "status": apt.status,
                "inspection_status": apt.inspection_status,
                "appointment_date": apt.appointment_date.isoformat() if apt.appointment_date else None,
                "created_at": apt.created_at.isoformat(),
                "reservation_paid": apt.payment_id is not None,
                "inspection_paid": apt.inspection_payment_id is not None,
                "payment_info": payment_info,
                "inspection_payment_info": inspection_payment_info,
                "has_report": has_report,
                "can_generate_report": apt.inspection_status in ["passed", "failed", "passed_with_minor_issues"] and apt.inspection_payment_id is not None
            })
        
        return {
            "total_count": len(vehicles_data),
            "vehicles": vehicles_data
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get my vehicles error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve vehicles: {str(e)}")

@app.get("/appointments/my-vehicle/{appointment_id}/report")
async def generate_vehicle_report(
    appointment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Generate PDF inspection report for a vehicle"""
    try:
        user = verify_token(authorization)
        user_id = user.get("user_id")
        
        # Get appointment
        result = await db.execute(
            select(Appointment).where(Appointment.id == uuid.UUID(appointment_id))
        )
        appointment = result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        
        # Verify ownership
        if str(appointment.user_id) != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this report")
        
        # Check if inspection is paid
        if not appointment.inspection_payment_id:
            raise HTTPException(
                status_code=402,
                detail="Inspection fee not paid. Please pay the inspection fee to generate report."
            )
        
        # Check if inspection is complete
        if appointment.inspection_status not in ["passed", "failed", "passed_with_minor_issues"]:
            raise HTTPException(
                status_code=400,
                detail=f"Inspection not complete. Current status: {appointment.inspection_status}"
            )
        
        # Get inspection details
        async with httpx.AsyncClient(timeout=10) as client:
            insp_resp = await client.get(
                f"{INSPECTION_SERVICE_URL}/inspection/by-appointment/{appointment_id}",
                headers={"Authorization": f"Bearer {authorization.replace('Bearer ', '')}"}
            )
            if insp_resp.status_code != 200:
                raise HTTPException(status_code=404, detail="Inspection report not found")
            
            inspection = insp_resp.json()
        
        # Generate PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=30,
            alignment=1  # Center
        )
        elements.append(Paragraph("VEHICLE INSPECTION REPORT", title_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Vehicle Information
        vehicle_data = [
            ['Vehicle Information', ''],
            ['Registration Number', appointment.vehicle_info.get('registration', 'N/A')],
            ['Brand', appointment.vehicle_info.get('brand', 'N/A')],
            ['Model', appointment.vehicle_info.get('model', 'N/A')],
            ['Type', appointment.vehicle_info.get('type', 'N/A')],
            ['Inspection Date', appointment.appointment_date.strftime('%Y-%m-%d %H:%M') if appointment.appointment_date else 'N/A'],
        ]
        
        vehicle_table = Table(vehicle_data, colWidths=[2.5*inch, 3.5*inch])
        vehicle_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ]))
        elements.append(vehicle_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Inspection Results
        results_data = [['Inspection Results', '']]
        results = inspection.get('results', {})
        
        for key, value in results.items():
            result_color = colors.green if value == 'PASS' else colors.red
            results_data.append([key.upper(), value])
        
        results_table = Table(results_data, colWidths=[2.5*inch, 3.5*inch])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ]))
        elements.append(results_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Final Status
        status_color = colors.green if appointment.inspection_status == 'passed' else (colors.orange if 'minor' in appointment.inspection_status else colors.red)
        status_data = [
            ['FINAL STATUS', appointment.inspection_status.upper().replace('_', ' ')]
        ]
        status_table = Table(status_data, colWidths=[2.5*inch, 3.5*inch])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), status_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 16),
            ('PADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(status_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Notes
        if inspection.get('notes'):
            notes_style = ParagraphStyle(
                'Notes',
                parent=styles['BodyText'],
                fontSize=10,
                leading=14,
            )
            elements.append(Paragraph("<b>Technician Notes:</b>", styles['Heading3']))
            elements.append(Paragraph(inspection['notes'], notes_style))
            elements.append(Spacer(1, 0.2*inch))
        
        # Footer
        footer_text = f"Report generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}<br/>Report ID: {inspection['id']}"
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph(footer_text, styles['Normal']))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        # Log the report generation
        await log_event("AppointmentService", "report.generated", "INFO",
                      f"User {user.get('email')} generated inspection report for vehicle {appointment.vehicle_info.get('registration')} - Appointment {appointment_id}")
        
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=inspection_report_{appointment.vehicle_info.get('registration', appointment_id)}.pdf"
            }
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate report error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@app.get("/appointments/admin/all-vehicles")
async def get_all_vehicles_admin(
    authorization: str = Header(...),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Admin endpoint to see ALL vehicles, not just inspected ones"""
    try:
        user = verify_token(authorization)
        
        # Only admin can access
        if user.get("role") not in ["admin"]:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get all appointments with pagination
        result = await db.execute(
            select(Appointment)
            .order_by(Appointment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        appointments = result.scalars().all()
        
        vehicles_data = []
        for apt in appointments:
            vehicles_data.append({
                "id": str(apt.id),
                "user_id": str(apt.user_id),
                "vehicle_info": apt.vehicle_info,
                "status": apt.status,
                "inspection_status": apt.inspection_status,
                "appointment_date": apt.appointment_date.isoformat() if apt.appointment_date else None,
                "created_at": apt.created_at.isoformat(),
                "reservation_paid": apt.payment_id is not None,
                "inspection_paid": apt.inspection_payment_id is not None,
                "payment_id": str(apt.payment_id) if apt.payment_id else None,
                "inspection_payment_id": str(apt.inspection_payment_id) if apt.inspection_payment_id else None
            })
        
        return {
            "total_count": len(vehicles_data),
            "vehicles": vehicles_data,
            "pagination": {
                "skip": skip,
                "limit": limit
            }
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get all vehicles admin error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve vehicles: {str(e)}")

@app.get("/appointments/{user_id}", response_model=List[AppointmentResponse])
async def get_appointments(
    user_id: str,
    authorization: str = Header(...),
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """Get appointments for user"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Appointment)
            .where(Appointment.user_id == uuid.UUID(user_id))
            .order_by(Appointment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        appointments = result.scalars().all()
        
        return [
            AppointmentResponse(
                id=str(a.id),
                user_id=str(a.user_id),
                vehicle_info=a.vehicle_info,
                status=a.status,
                payment_id=str(a.payment_id) if a.payment_id else None,
                created_at=a.created_at.isoformat(),
                appointment_date=a.appointment_date.isoformat() if a.appointment_date else None
            )
            for a in appointments
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get appointments error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve appointments: {str(e)}")

@app.put("/appointments/{appointment_id}/confirm")
async def confirm_appointment(
    appointment_id: str,
    update: AppointmentUpdate,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Confirm appointment after payment"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Appointment).where(Appointment.id == uuid.UUID(appointment_id))
        )
        appointment = result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        
        # Update appointment
        appointment.status = AppointmentStatus.CONFIRMED.value
        appointment.payment_id = uuid.UUID(update.payment_id)
        appointment.updated_at = datetime.utcnow()
        await db.flush()
        
        await log_event("AppointmentService", "appointment.confirmed", "INFO",
                      f"Appointment {appointment_id} confirmed with payment {update.payment_id}")
        
        return {"message": "Appointment confirmed", "status": appointment.status}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Confirm appointment error: {e}", exc_info=True)
        try:
            await log_event("AppointmentService", "appointment.confirm_error", "ERROR", str(e))
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to confirm appointment: {str(e)}")

@app.put("/appointments/{appointment_id}/inspection-status")
async def update_inspection_status(
    appointment_id: str,
    status_update: dict,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Update inspection status for appointment (called by inspection service)"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Appointment).where(Appointment.id == uuid.UUID(appointment_id))
        )
        appointment = result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        
        # Update inspection status
        new_status = status_update.get("inspection_status")
        if new_status not in ["not_checked", "in_progress", "passed", "failed", "passed_with_minor_issues"]:
            raise HTTPException(status_code=400, detail="Invalid inspection status")
        
        appointment.inspection_status = new_status
        appointment.updated_at = datetime.utcnow()
        await db.flush()
        
        await log_event("AppointmentService", "appointment.inspection_status_updated", "INFO",
                      f"Appointment {appointment_id} inspection status updated to {new_status}")
        
        return {
            "message": "Inspection status updated",
            "appointment_id": appointment_id,
            "inspection_status": new_status
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update inspection status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update inspection status: {str(e)}")

@app.delete("/appointments/{appointment_id}")
async def cancel_appointment(
    appointment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Cancel appointment"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Appointment).where(Appointment.id == uuid.UUID(appointment_id))
        )
        appointment = result.scalar_one_or_none()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        
        if appointment.status == AppointmentStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="Cannot cancel completed appointment")
        
        appointment.status = AppointmentStatus.CANCELLED.value
        appointment.updated_at = datetime.utcnow()
        await db.flush()
        
        await log_event("AppointmentService", "appointment.cancelled", "INFO",
                      f"Appointment {appointment_id} cancelled")
        
        return {"message": "Appointment cancelled"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel appointment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel appointment: {str(e)}")

# Specific routes moved to top (after line 350) to avoid routing conflicts

@app.get("/appointments/available-slots/{date}")
async def get_available_slots(
    date: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get available time slots for a specific date (45-minute inspections)"""
    try:
        verify_token(authorization)
        
        # Parse the date
        target_date = datetime.fromisoformat(date).date()
        
        # Define working hours with 45-minute slots (9 AM to 5 PM)
        # Each inspection takes 45 minutes
        time_slots = []
        start_hour = 9
        end_hour = 17  # 5 PM
        
        current_time = datetime.combine(target_date, datetime.min.time().replace(hour=start_hour))
        end_time = datetime.combine(target_date, datetime.min.time().replace(hour=end_hour))
        
        while current_time < end_time:
            time_slots.append(current_time)
            current_time += timedelta(minutes=45)
        
        # Get all booked appointments for this date
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        result = await db.execute(
            select(Appointment.appointment_date)
            .where(
                Appointment.appointment_date >= start_of_day,
                Appointment.appointment_date <= end_of_day,
                Appointment.status.in_(["pending", "confirmed"])
            )
        )
        booked_appointments = [row[0] for row in result.all()]
        
        # Calculate available slots
        available_slots = []
        for slot_time in time_slots:
            # Check if this slot or within 45 minutes is booked
            is_available = True
            for booked in booked_appointments:
                if booked:
                    # Check if booked time conflicts (within 45 minutes)
                    time_diff = abs((slot_time - booked).total_seconds() / 60)
                    if time_diff < 45:
                        is_available = False
                        break
            
            available_slots.append({
                "time": slot_time.isoformat(),
                "display": slot_time.strftime("%H:%M"),
                "available": is_available
            })
        
        return {
            "date": date,
            "slots": available_slots,
            "total_slots": len(time_slots),
            "available_count": len([s for s in available_slots if s["available"]]),
            "slot_duration_minutes": 45
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get available slots error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve available slots: {str(e)}")

# weekly-schedule endpoint moved to line 413 (before parameterized routes)
# my-vehicles, my-vehicle/{id}/report, and admin/all-vehicles moved to line 515-828 (before parameterized routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)