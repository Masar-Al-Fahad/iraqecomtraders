"""Password-reset OTP model for panel users."""
from datetime import datetime

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class PasswordResetOtp(Base):
    __tablename__ = "password_reset_otps"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False, index=True)
    channel = Column(String(20), nullable=False)  # email | phone
    destination_masked = Column(String(120), nullable=False, default="")
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    request_ip = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    is_consumed = Column(Boolean, nullable=False, default=False)
