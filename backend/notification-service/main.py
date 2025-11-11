# Notification Service - Simulated Email/SMS
# This service logs notifications to database instead of sending real emails/SMS
# Users can view their notifications in the app

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import String, Boolean, DateTime, Text, select, UUID, JSON
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= DATABASE SETUP =============
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "azerty5027")
DB_NAME = os.getenv("DB_NAME_NOTIFICATIONS", "notifications_db")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Notification(Base):
    __tablename__ = "notifications"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, sms, in-app
    channel: Mapped[str] = mapped_column(String(50), nullable=False)  # appointment, payment, inspection, auth
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Extra data (renamed from metadata)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

# Database dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# ============= FASTAPI APP =============
app = FastAPI(title="Notification Service (Simulated)")

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
        logger.info("✓ Notification database initialized successfully")
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        raise

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    logger.info("✓ Database connections closed")

# ============= MODELS =============
class SendNotificationRequest(BaseModel):
    user_id: str
    user_email: EmailStr
    notification_type: str  # email, sms, in-app
    channel: str  # appointment, payment, inspection, auth
    subject: str
    message: str
    extra_data: Optional[Dict[str, Any]] = None

class NotificationResponse(BaseModel):
    id: str
    user_id: str
    notification_type: str
    channel: str
    subject: str
    message: str
    is_read: bool
    sent_at: str

# ============= HELPER FUNCTIONS =============
def format_notification(notif: Notification) -> dict:
    return {
        "id": str(notif.id),
        "user_id": str(notif.user_id),
        "user_email": notif.user_email,
        "notification_type": notif.notification_type,
        "channel": notif.channel,
        "subject": notif.subject,
        "message": notif.message,
        "extra_data": notif.extra_data,
        "is_read": notif.is_read,
        "sent_at": notif.sent_at.isoformat(),
        "read_at": notif.read_at.isoformat() if notif.read_at else None
    }

# ============= ENDPOINTS =============
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "notification-service"}

@app.post("/notifications/send")
async def send_notification(
    request: SendNotificationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Send a notification (simulated - stores in database instead of real email/SMS)
    """
    try:
        # Create notification record
        notification = Notification(
            user_id=uuid.UUID(request.user_id),
            user_email=request.user_email,
            notification_type=request.notification_type,
            channel=request.channel,
            subject=request.subject,
            message=request.message,
            extra_data=request.extra_data or {}
        )
        
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        
        logger.info(f"📧 Simulated {request.notification_type} sent to {request.user_email}: {request.subject}")
        
        return {
            "success": True,
            "notification_id": str(notification.id),
            "message": f"Notification logged (simulated {request.notification_type})",
            "notification": format_notification(notification)
        }
    except Exception as e:
        logger.error(f"Error sending notification: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {str(e)}")

@app.get("/notifications/user/{user_id}")
async def get_user_notifications(
    user_id: str,
    unread_only: bool = False,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Get all notifications for a user"""
    try:
        query = select(Notification).where(
            Notification.user_id == uuid.UUID(user_id)
        ).order_by(Notification.sent_at.desc()).limit(limit)
        
        if unread_only:
            query = query.where(Notification.is_read == False)
        
        result = await db.execute(query)
        notifications = result.scalars().all()
        
        return {
            "total": len(notifications),
            "unread_count": sum(1 for n in notifications if not n.is_read),
            "notifications": [format_notification(n) for n in notifications]
        }
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Mark a notification as read"""
    try:
        result = await db.execute(
            select(Notification).where(Notification.id == uuid.UUID(notification_id))
        )
        notification = result.scalar_one_or_none()
        
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await db.commit()
        
        return {"success": True, "message": "Notification marked as read"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/notifications/mark-all-read/{user_id}")
async def mark_all_read(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications for a user as read"""
    try:
        result = await db.execute(
            select(Notification).where(
                Notification.user_id == uuid.UUID(user_id),
                Notification.is_read == False
            )
        )
        notifications = result.scalars().all()
        
        for notif in notifications:
            notif.is_read = True
            notif.read_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Marked {len(notifications)} notifications as read"
        }
    except Exception as e:
        logger.error(f"Error marking all as read: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a notification"""
    try:
        result = await db.execute(
            select(Notification).where(Notification.id == uuid.UUID(notification_id))
        )
        notification = result.scalar_one_or_none()
        
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        await db.delete(notification)
        await db.commit()
        
        return {"success": True, "message": "Notification deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ============= NOTIFICATION TEMPLATES =============
class NotificationTemplates:
    """Pre-defined notification templates"""
    
    @staticmethod
    def appointment_confirmation(appointment_id: str, vehicle_reg: str, date: str) -> Dict[str, str]:
        return {
            "subject": "Appointment Confirmed - Vehicle Inspection",
            "message": f"""
Your vehicle inspection appointment has been confirmed!

Appointment ID: {appointment_id}
Vehicle: {vehicle_reg}
Date: {date}

Please arrive 10 minutes early. Bring your vehicle registration documents.

Thank you for choosing our service!
            """.strip()
        }
    
    @staticmethod
    def payment_confirmation(appointment_id: str, amount: float) -> Dict[str, str]:
        return {
            "subject": "Payment Received - Thank You!",
            "message": f"""
Your payment has been successfully processed!

Appointment ID: {appointment_id}
Amount Paid: €{amount:.2f}

Your appointment is now confirmed. We look forward to seeing you!
            """.strip()
        }
    
    @staticmethod
    def inspection_completed(appointment_id: str, vehicle_reg: str, result: str) -> Dict[str, str]:
        return {
            "subject": f"Inspection Complete - {result}",
            "message": f"""
Your vehicle inspection has been completed!

Vehicle: {vehicle_reg}
Appointment ID: {appointment_id}
Result: {result}

Your inspection certificate is ready for download in your dashboard.

Thank you for using our service!
            """.strip()
        }
    
    @staticmethod
    def appointment_reminder(appointment_id: str, vehicle_reg: str, date: str) -> Dict[str, str]:
        return {
            "subject": "Reminder: Upcoming Vehicle Inspection Tomorrow",
            "message": f"""
This is a friendly reminder about your upcoming appointment!

Vehicle: {vehicle_reg}
Date: {date}
Appointment ID: {appointment_id}

See you tomorrow! Don't forget your vehicle documents.
            """.strip()
        }

@app.post("/notifications/templates/appointment-confirmation")
async def send_appointment_confirmation(
    user_id: str,
    user_email: EmailStr,
    appointment_id: str,
    vehicle_reg: str,
    date: str,
    db: AsyncSession = Depends(get_db)
):
    """Send appointment confirmation notification"""
    template = NotificationTemplates.appointment_confirmation(appointment_id, vehicle_reg, date)
    
    request = SendNotificationRequest(
        user_id=user_id,
        user_email=user_email,
        notification_type="email",
        channel="appointment",
        subject=template["subject"],
        message=template["message"],
        extra_data={"appointment_id": appointment_id, "vehicle_reg": vehicle_reg}
    )
    
    return await send_notification(request, db)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
