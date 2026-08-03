from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint


class Registrations(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("membership_number", name="uq_registrations_membership_number"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    business_name = Column(String, nullable=False)
    merchant_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    governorate = Column(String, nullable=False)
    area = Column(String, nullable=False)
    business_type = Column(String, nullable=False)
    image_key = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    # JSON object: { field_id: { "label": "...", "value": "..." } }
    extra_fields = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    membership_number = Column(String, nullable=True, unique=True)
    request_number = Column(String, nullable=True, unique=True)
    membership_status = Column(String, nullable=True)
    approved_at = Column(String, nullable=True)
    whatsapp_registration_sent = Column(Boolean, nullable=True)
    whatsapp_approval_sent = Column(Boolean, nullable=True)
    whatsapp_last_attempt = Column(String, nullable=True)
    whatsapp_status = Column(String, nullable=True)
    user_id = Column(String, index=True, nullable=False)
    last_modified_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)