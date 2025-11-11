"""
Inspection Service - Vehicle Inspection Results Management
Port: 8004
Database: inspections_db
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, AsyncGenerator
import logging
from dotenv import load_dotenv
import httpx
from enum import Enum
import uuid

# SQLAlchemy imports
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, DateTime, Text, JSON, select
from sqlalchemy.dialects.postgresql import UUID

load_dotenv()

# ============= CONFIGURATION =============
app = FastAPI(title="Inspection Service", version="1.0.0")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "azerty5027")
DB_NAME = os.getenv("DB_NAME_INSPECTIONS", "inspections_db")

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
class InspectionStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    PASSED_WITH_MINOR_ISSUES = "passed_with_minor_issues"

class InspectionResult(BaseModel):
    brakes: str
    lights: str
    tires: str
    emissions: str
    windscreen: str = "PASS"
    seatbelts: str = "PASS"
    horn: str = "PASS"
    wipers: str = "PASS"
    
    @validator("brakes", "lights", "tires", "emissions", "windscreen", "seatbelts", "horn", "wipers")
    def validate_status(cls, v):
        valid = ["PASS", "FAIL"]
        if v not in valid:
            raise ValueError(f"Status must be PASS or FAIL")
        return v

class InspectionSubmit(BaseModel):
    appointment_id: str
    results: InspectionResult
    final_status: str
    notes: Optional[str] = None
    
    @validator("final_status")
    def validate_final_status(cls, v):
        valid = ["not_checked", "in_progress", "passed", "failed", "passed_with_minor_issues"]
        if v not in valid:
            raise ValueError(f"Status must be one of {valid}")
        return v

class InspectionResponse(BaseModel):
    id: str
    appointment_id: str
    technician_id: str
    results: Dict[str, Any]
    final_status: str
    notes: Optional[str]
    created_at: str

# ============= DATABASE MODELS & CONNECTION =============
Base = declarative_base()

class Inspection(Base):
    __tablename__ = "inspections"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    technician_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    results: Mapped[dict] = mapped_column(JSON, nullable=False)
    final_status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

def verify_technician(payload: dict):
    """Verify user is a technician"""
    role = payload.get("role")
    if role != "technician":
        raise HTTPException(status_code=403, detail="Only technicians can perform inspections")
    return True

# ============= EVENTS =============
@app.on_event("startup")
async def startup():
    logger.info("Starting Inspection Service...")
    await init_db()
    logger.info("✓ Inspection Service started successfully")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down Inspection Service...")
    await engine.dispose()
    logger.info("✓ Database connections closed")

# ============= ENDPOINTS =============
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "inspection-service"}

@app.get("/inspections/vehicles-for-inspection")
async def get_vehicles_for_inspection(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed list of all vehicles available for inspection with full details"""
    try:
        user = verify_token(authorization)
        
        # Allow both technicians and admins
        if user.get("role") not in ["technician", "admin"]:
            raise HTTPException(status_code=403, detail="Only technicians and admins can view vehicles for inspection")
        
        await log_event("InspectionService", "user.view_vehicles", "INFO",
                      f"User {user.get('email')} (role: {user.get('role')}) viewed vehicle list at {datetime.utcnow().isoformat()}")
        
        # Fetch ALL appointments from Appointment Service (both paid and unpaid)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{APPOINTMENT_SERVICE_URL}/appointments/all",
                    headers={"Authorization": authorization},
                    # No status filter - get ALL appointments
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    appointments = response.json()
                    logger.info(f"Fetched {len(appointments)} appointments from appointment service")
                    
                    # Build comprehensive vehicle list
                    vehicles = []
                    for apt in appointments:
                        try:
                            # Check if inspection exists for this appointment
                            result = await db.execute(
                                select(Inspection)
                                .where(Inspection.appointment_id == uuid.UUID(apt["id"]))
                            )
                            inspection = result.scalar_one_or_none()
                            
                            # Parse appointment date safely
                            apt_datetime = None
                            if apt.get("appointment_date"):
                                try:
                                    apt_datetime = datetime.fromisoformat(apt.get("appointment_date"))
                                except:
                                    logger.warning(f"Could not parse date for appointment {apt['id']}")
                            
                            vehicle_data = {
                                "appointment_id": apt["id"],
                                "vehicle_info": {
                                    "type": apt["vehicle_info"].get("type"),
                                    "registration": apt["vehicle_info"].get("registration"),
                                    "brand": apt["vehicle_info"].get("brand"),
                                    "model": apt["vehicle_info"].get("model")
                                },
                                "appointment_date": apt.get("appointment_date"),
                                "appointment_time": apt_datetime.strftime("%Y-%m-%d %H:%M") if apt_datetime else "Not scheduled",
                                "user_id": apt["user_id"],
                                "payment_status": apt.get("status", "pending"),  # Show if paid (confirmed) or unpaid (pending)
                                "payment_status_display": "Paid" if apt.get("status") == "confirmed" else "Not Paid"
                            }
                            
                            if not inspection:
                                # No inspection yet
                                vehicle_data.update({
                                    "inspection_id": None,
                                    "status": "not_checked",
                                    "status_display": "Not Checked Yet",
                                    "can_start": True,
                                    "results": None,
                                    "notes": None
                                })
                            else:
                                # Inspection exists
                                vehicle_data.update({
                                    "inspection_id": str(inspection.id),
                                    "status": inspection.final_status,
                                    "status_display": {
                                        "not_checked": "Not Checked Yet",
                                        "in_progress": "In Progress",
                                        "passed": "Passed",
                                        "failed": "Failed",
                                        "passed_with_minor_issues": "Passed with Minor Issues"
                                    }.get(inspection.final_status, inspection.final_status),
                                    "can_continue": inspection.final_status == "in_progress",
                                    "results": inspection.results,
                                    "notes": inspection.notes,
                                    "inspected_at": inspection.created_at.isoformat()
                                })
                            
                            vehicles.append(vehicle_data)
                            logger.info(f"Added vehicle: {vehicle_data['vehicle_info']['registration']}")
                        except Exception as vehicle_error:
                            logger.error(f"Error processing appointment {apt.get('id')}: {vehicle_error}", exc_info=True)
                            # Continue with next appointment instead of failing completely
                            continue
                    
                    # Sort by appointment time
                    vehicles.sort(key=lambda x: x.get("appointment_date") or "")
                    
                    logger.info(f"Returning {len(vehicles)} vehicles to technician")
                    
                    result = {
                        "vehicles": vehicles,
                        "total_count": len(vehicles),
                        "by_status": {
                            "not_checked": len([v for v in vehicles if v.get("status") == "not_checked"]),
                            "in_progress": len([v for v in vehicles if v.get("status") == "in_progress"]),
                            "passed": len([v for v in vehicles if v.get("status") == "passed"]),
                            "failed": len([v for v in vehicles if v.get("status") == "failed"]),
                            "passed_with_minor_issues": len([v for v in vehicles if v.get("status") == "passed_with_minor_issues"])
                        }
                    }
                    
                    logger.info(f"Result summary: {result['total_count']} total, {result['by_status']['not_checked']} not checked")
                    return result
                else:
                    logger.warning(f"Appointment service returned status {response.status_code}")
                    return {
                        "vehicles": [], 
                        "total_count": 0, 
                        "by_status": {"not_checked": 0, "in_progress": 0, "passed": 0, "failed": 0, "passed_with_minor_issues": 0},
                        "error": f"Appointment service error: {response.status_code}"
                    }
        except httpx.TimeoutException:
            logger.error("Timeout fetching appointments from appointment service")
            return {
                "vehicles": [], 
                "total_count": 0, 
                "by_status": {"not_checked": 0, "in_progress": 0, "passed": 0, "failed": 0, "passed_with_minor_issues": 0},
                "error": "Appointment service timeout"
            }
        except Exception as e:
            logger.error(f"Error fetching appointments: {e}", exc_info=True)
            return {
                "vehicles": [], 
                "total_count": 0, 
                "by_status": {"not_checked": 0, "in_progress": 0, "passed": 0, "failed": 0, "passed_with_minor_issues": 0},
                "error": str(e)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get vehicles for inspection error: {e}", exc_info=True)
        await log_event("InspectionService", "vehicles.error", "ERROR", f"Failed to retrieve vehicles: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve vehicles: {str(e)}")

@app.get("/inspections/assigned/{technician_id}", response_model=List[Dict[str, Any]])
async def get_assigned_vehicles(
    technician_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get vehicles assigned to technician (completed inspections)"""
    try:
        user = verify_token(authorization)
        verify_technician(user)
        
        # Verify technician ID matches (technicians can only see their own)
        if user.get("user_id") != technician_id:
            raise HTTPException(status_code=403, detail="Unauthorized - can only view your own inspections")
        
        result = await db.execute(
            select(Inspection)
            .where(Inspection.technician_id == uuid.UUID(technician_id))
            .order_by(Inspection.created_at.desc())
            .limit(50)
        )
        inspections = result.scalars().all()
        
        return [
            {
                "id": str(i.id),
                "appointment_id": str(i.appointment_id),
                "technician_id": str(i.technician_id),
                "results": i.results,
                "final_status": i.final_status,
                "created_at": i.created_at.isoformat()
            }
            for i in inspections
        ]
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get assigned vehicles error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve assigned vehicles")

@app.post("/inspections/submit", response_model=InspectionResponse)
async def submit_inspection(
    data: InspectionSubmit,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Submit inspection results"""
    try:
        user = verify_token(authorization)
        verify_technician(user)
        technician_id = user.get("user_id")
        
        results = data.results.dict()
        
        # Get vehicle info from appointment for better logging
        vehicle_registration = "Unknown"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                auth_header = authorization.replace("Bearer ", "")
                apt_resp = await client.get(
                    f"{APPOINTMENT_SERVICE_URL}/appointments/admin/all-vehicles?limit=1000",
                    headers={"Authorization": f"Bearer {auth_header}"}
                )
                if apt_resp.status_code == 200:
                    apt_data = apt_resp.json()
                    for vehicle in apt_data.get("vehicles", []):
                        if vehicle["id"] == data.appointment_id:
                            vehicle_registration = vehicle.get("vehicle_info", {}).get("registration", "Unknown")
                            break
        except:
            pass
        
        new_inspection = Inspection(
            appointment_id=uuid.UUID(data.appointment_id),
            technician_id=uuid.UUID(technician_id),
            results=results,
            final_status=data.final_status,
            notes=data.notes
        )
        db.add(new_inspection)
        await db.flush()
        await db.refresh(new_inspection)
        
        # Update appointment inspection_status
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                auth_header = authorization.replace("Bearer ", "")
                update_resp = await client.put(
                    f"{APPOINTMENT_SERVICE_URL}/appointments/{data.appointment_id}/inspection-status",
                    json={"inspection_status": data.final_status},
                    headers={"Authorization": f"Bearer {auth_header}"}
                )
                if update_resp.status_code != 200:
                    logger.warning(f"Failed to update appointment inspection status: {update_resp.status_code}")
        except Exception as e:
            logger.error(f"Error updating appointment inspection status: {e}")
        
        await log_event("InspectionService", "inspection.submitted", "INFO",
                      f"Technician {user.get('email')} submitted inspection for vehicle {vehicle_registration} (Appointment {data.appointment_id}) with status {data.final_status} at {datetime.utcnow().isoformat()}")
        
        return InspectionResponse(
            id=str(new_inspection.id),
            appointment_id=str(new_inspection.appointment_id),
            technician_id=str(new_inspection.technician_id),
            results=new_inspection.results,
            final_status=new_inspection.final_status,
            notes=new_inspection.notes,
            created_at=new_inspection.created_at.isoformat()
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Submit inspection error: {e}")
        await log_event("InspectionService", "inspection.submit_error", "ERROR", str(e))
        raise HTTPException(status_code=500, detail="Failed to submit inspection")

@app.get("/inspection/by-appointment/{appointment_id}", response_model=InspectionResponse)
async def get_inspection_by_appointment(
    appointment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get inspection by appointment ID (for report generation)"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Inspection).where(Inspection.appointment_id == uuid.UUID(appointment_id))
        )
        inspection = result.scalar_one_or_none()
        
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")
        
        return InspectionResponse(
            id=str(inspection.id),
            appointment_id=str(inspection.appointment_id),
            technician_id=str(inspection.technician_id),
            results=inspection.results,
            final_status=inspection.final_status,
            notes=inspection.notes,
            created_at=inspection.created_at.isoformat()
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get inspection by appointment error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inspection")

@app.get("/inspections/result/{appointment_id}", response_model=InspectionResponse)
async def get_inspection_result(
    appointment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve inspection report"""
    try:
        verify_token(authorization)
        
        result = await db.execute(
            select(Inspection).where(Inspection.appointment_id == uuid.UUID(appointment_id))
        )
        inspection = result.scalar_one_or_none()
        
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")
        
        return InspectionResponse(
            id=str(inspection.id),
            appointment_id=str(inspection.appointment_id),
            technician_id=str(inspection.technician_id),
            results=inspection.results,
            final_status=inspection.final_status,
            notes=inspection.notes,
            created_at=inspection.created_at.isoformat()
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get inspection result error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inspection result")

@app.get("/inspections/{inspection_id}")
async def get_inspection_by_id(
    inspection_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get single inspection by ID with full details"""
    try:
        user = verify_token(authorization)
        
        result = await db.execute(
            select(Inspection).where(Inspection.id == uuid.UUID(inspection_id))
        )
        inspection = result.scalar_one_or_none()
        
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")
        
        return {
            "id": str(inspection.id),
            "appointment_id": str(inspection.appointment_id),
            "technician_id": str(inspection.technician_id),
            "results": inspection.results or {},
            "final_status": inspection.final_status,
            "notes": inspection.notes,
            "created_at": inspection.created_at.isoformat(),
            "updated_at": inspection.updated_at.isoformat() if inspection.updated_at else None
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get inspection by ID error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inspection")

@app.get("/inspections/appointment/{appointment_id}")
async def get_inspection_by_appointment_id(
    appointment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get inspection by appointment ID with full details"""
    try:
        user = verify_token(authorization)
        
        result = await db.execute(
            select(Inspection).where(Inspection.appointment_id == uuid.UUID(appointment_id))
        )
        inspection = result.scalar_one_or_none()
        
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found for this appointment")
        
        return {
            "id": str(inspection.id),
            "appointment_id": str(inspection.appointment_id),
            "technician_id": str(inspection.technician_id),
            "results": inspection.results or {},
            "final_status": inspection.final_status,
            "notes": inspection.notes,
            "created_at": inspection.created_at.isoformat(),
            "updated_at": inspection.updated_at.isoformat() if inspection.updated_at else None
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get inspection by appointment ID error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inspection")

# ============= ADMIN ENDPOINTS =============
@app.get("/admin/inspections/all")
async def get_all_inspections_admin(
    authorization: str = Header(...),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all inspections with full details (admin only, read-only)"""
    try:
        user = verify_token(authorization)
        
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        await log_event("InspectionService", "admin.view_inspections", "INFO",
                      f"Admin {user.get('email')} viewed inspection list at {datetime.utcnow().isoformat()}")
        
        query = select(Inspection).order_by(Inspection.created_at.desc())
        
        if status:
            query = query.where(Inspection.final_status == status)
        
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        inspections = result.scalars().all()
        
        return {
            "inspections": [
                {
                    "id": str(i.id),
                    "appointment_id": str(i.appointment_id),
                    "technician_id": str(i.technician_id),
                    "results": i.results,
                    "final_status": i.final_status,
                    "status_display": {
                        "not_checked": "Not Checked Yet",
                        "in_progress": "In Progress",
                        "passed": "Passed",
                        "failed": "Failed",
                        "passed_with_minor_issues": "Passed with Minor Issues"
                    }.get(i.final_status, i.final_status),
                    "notes": i.notes,
                    "created_at": i.created_at.isoformat()
                }
                for i in inspections
            ],
            "total": len(inspections),
            "message": "Read-only view - Admin cannot edit inspections"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin get inspections error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inspections")

@app.get("/admin/inspections/stats")
async def get_inspection_stats_admin(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Get inspection statistics (admin only)"""
    try:
        user = verify_token(authorization)
        
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Count by status
        result = await db.execute(select(Inspection))
        all_inspections = result.scalars().all()
        
        stats = {
            "total_inspections": len(all_inspections),
            "by_status": {
                "not_checked": len([i for i in all_inspections if i.final_status == "not_checked"]),
                "in_progress": len([i for i in all_inspections if i.final_status == "in_progress"]),
                "passed": len([i for i in all_inspections if i.final_status == "passed"]),
                "failed": len([i for i in all_inspections if i.final_status == "failed"]),
                "passed_with_minor_issues": len([i for i in all_inspections if i.final_status == "passed_with_minor_issues"])
            }
        }
        
        await log_event("InspectionService", "admin.view_stats", "INFO",
                      f"Admin {user.get('email')} viewed inspection statistics at {datetime.utcnow().isoformat()}")
        
        return stats
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin get stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")

@app.get("/inspections/certificate/{appointment_id}")
async def generate_inspection_certificate(
    appointment_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Generate PDF certificate for inspection"""
    try:
        user = verify_token(authorization)
        
        # Get inspection by appointment ID
        result = await db.execute(
            select(Inspection).where(Inspection.appointment_id == uuid.UUID(appointment_id))
        )
        inspection = result.scalar_one_or_none()
        
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")
        
        # Fetch appointment details to get vehicle info
        async with httpx.AsyncClient() as client:
            apt_response = await client.get(
                f"http://localhost:8002/appointments/details/{appointment_id}",
                headers={"Authorization": authorization}
            )
            
            if apt_response.status_code != 200:
                raise HTTPException(status_code=404, detail="Appointment not found")
            
            appointment = apt_response.json()
        
        # Generate PDF content (simple text-based PDF using reportlab)
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from io import BytesIO
            
            # Create PDF in memory
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            elements = []
            styles = getSampleStyleSheet()
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#1abc9c'),
                spaceAfter=30,
                alignment=TA_CENTER
            )
            elements.append(Paragraph("VEHICLE INSPECTION CERTIFICATE", title_style))
            elements.append(Spacer(1, 0.3*inch))
            
            # Status banner
            status_text = inspection.final_status.replace('_', ' ').upper()
            status_color = {
                'passed': colors.HexColor('#4caf50'),
                'failed': colors.HexColor('#f44336'),
                'passed_with_minor_issues': colors.HexColor('#ff9800'),
                'in_progress': colors.HexColor('#ffa500'),
                'not_checked': colors.HexColor('#999999')
            }.get(inspection.final_status, colors.grey)
            
            status_style = ParagraphStyle(
                'Status',
                parent=styles['Normal'],
                fontSize=18,
                textColor=colors.white,
                backColor=status_color,
                alignment=TA_CENTER,
                spaceAfter=20
            )
            elements.append(Paragraph(f"<b>STATUS: {status_text}</b>", status_style))
            elements.append(Spacer(1, 0.3*inch))
            
            # Vehicle Information
            vehicle_info = appointment.get('vehicle_info', {})
            info_data = [
                ['Vehicle Information', ''],
                ['Registration Number:', vehicle_info.get('registration', 'N/A')],
                ['Brand:', vehicle_info.get('brand', 'N/A')],
                ['Model:', vehicle_info.get('model', 'N/A')],
                ['Type:', vehicle_info.get('type', 'N/A')],
                ['Year:', str(vehicle_info.get('year', 'N/A'))],
                ['', ''],
                ['Inspection Details', ''],
                ['Inspection ID:', str(inspection.id)[:8] + '...'],
                ['Appointment ID:', str(inspection.appointment_id)[:8] + '...'],
                ['Inspection Date:', inspection.created_at.strftime('%Y-%m-%d %H:%M')],
            ]
            
            info_table = Table(info_data, colWidths=[2.5*inch, 3*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1abc9c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#1abc9c')),
                ('TEXTCOLOR', (0, 7), (-1, 7), colors.white),
                ('FONTNAME', (0, 7), (-1, 7), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(info_table)
            elements.append(Spacer(1, 0.3*inch))
            
            # Inspection Items
            results = inspection.results or {}
            items_data = [['Inspection Item', 'Result']]
            for key, value in results.items():
                items_data.append([key.replace('_', ' ').title(), str(value).upper()])
            
            items_table = Table(items_data, colWidths=[3*inch, 2.5*inch])
            items_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1abc9c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(items_table)
            elements.append(Spacer(1, 0.3*inch))
            
            # Notes
            if inspection.notes:
                notes_style = ParagraphStyle(
                    'Notes',
                    parent=styles['Normal'],
                    fontSize=10,
                    spaceAfter=12
                )
                elements.append(Paragraph("<b>Inspector Notes:</b>", styles['Heading3']))
                elements.append(Paragraph(inspection.notes, notes_style))
                elements.append(Spacer(1, 0.2*inch))
            
            # Footer
            footer_text = f"This certificate was generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
            elements.append(Spacer(1, 0.5*inch))
            elements.append(Paragraph(footer_text, footer_style))
            
            # Build PDF
            doc.build(elements)
            buffer.seek(0)
            
            return StreamingResponse(
                buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=inspection_certificate_{appointment_id}.pdf"}
            )
            
        except ImportError:
            # Fallback: Generate simple text-based response if reportlab not available
            logger.warning("reportlab not installed, generating simple text certificate")
            
            text_content = f"""
VEHICLE INSPECTION CERTIFICATE
==============================

STATUS: {inspection.final_status.replace('_', ' ').upper()}

VEHICLE INFORMATION
-------------------
Registration: {vehicle_info.get('registration', 'N/A')}
Brand: {vehicle_info.get('brand', 'N/A')}
Model: {vehicle_info.get('model', 'N/A')}
Type: {vehicle_info.get('type', 'N/A')}
Year: {vehicle_info.get('year', 'N/A')}

INSPECTION DETAILS
------------------
Inspection ID: {inspection.id}
Appointment ID: {inspection.appointment_id}
Inspection Date: {inspection.created_at.strftime('%Y-%m-%d %H:%M')}

INSPECTION ITEMS
----------------
{chr(10).join([f"{k.replace('_', ' ').title()}: {v}" for k, v in (inspection.results or {}).items()])}

NOTES
-----
{inspection.notes or 'No notes provided'}

Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
            
            from io import BytesIO
            buffer = BytesIO(text_content.encode('utf-8'))
            
            return StreamingResponse(
                buffer,
                media_type="text/plain",
                headers={"Content-Disposition": f"attachment; filename=inspection_certificate_{appointment_id}.txt"}
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate certificate: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)