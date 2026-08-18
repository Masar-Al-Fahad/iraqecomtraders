"""Local panel users for admin user management (username/password + permissions)."""
from datetime import datetime

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


class PanelUser(Base):
    __tablename__ = "panel_users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    username = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(512), nullable=False)
    # JSON string of permissions: view, add, edit, delete, export, manage_users
    permissions = Column(Text, nullable=False, default="{}")
    is_active = Column(Boolean, nullable=False, default=True)
    is_super_admin = Column(Boolean, nullable=False, default=False)
    # Recovery contact for forgot-password OTP (optional until configured by admin)
    email = Column(String(255), nullable=True)
    phone = Column(String(40), nullable=True)
    recovery_preferred = Column(String(20), nullable=True)  # email | phone | auto
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
