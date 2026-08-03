"""App settings model (brand + registration form JSON)."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from core.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False, default="{}")
    updated_by = Column(String(200), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
