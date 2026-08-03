"""Audit log router for admin operations tracking."""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, Base
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/audit-log", tags=["audit-log"])


def verify_admin(current_user: UserResponse):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")


# Audit log model - create table on first use
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    action = Column(String, nullable=False)  # login, logout, approve, reject, add_member, delete, update_membership, export
    actor_email = Column(String, nullable=False)
    target_id = Column(Integer, nullable=True)  # registration id if applicable
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)


class AuditLogResponse(BaseModel):
    id: int
    action: str
    actor_email: str
    target_id: Optional[int] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int


@router.get("", response_model=AuditLogListResponse)
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get audit logs - admin only."""
    verify_admin(current_user)

    try:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
        count_stmt = select(func.count(AuditLog.id))

        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)

        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        items = result.scalars().all()

        return AuditLogListResponse(
            items=[
                AuditLogResponse(
                    id=item.id,
                    action=item.action,
                    actor_email=item.actor_email,
                    target_id=item.target_id,
                    details=item.details,
                    ip_address=item.ip_address,
                    created_at=str(item.created_at) if item.created_at else None,
                )
                for item in items
            ],
            total=total,
        )
    except Exception as e:
        logger.error(f"Error fetching audit logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في جلب سجل العمليات")


async def log_action(
    db: AsyncSession,
    action: str,
    actor_email: str,
    target_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    """Helper to create an audit log entry."""
    try:
        entry = AuditLog(
            action=action,
            actor_email=actor_email,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
        db.add(entry)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {str(e)}")
        # Don't fail the main operation if audit logging fails
        try:
            await db.rollback()
        except Exception:
            pass