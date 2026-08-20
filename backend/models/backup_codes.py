"""Panel user one-time backup/recovery codes (hashed)."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from core.database import Base


class PanelUserBackupCode(Base):
    __tablename__ = "panel_user_backup_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("panel_users.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(36), nullable=False, index=True)
    code_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used_at = Column(DateTime)
    revoked_at = Column(DateTime)
    created_by = Column(String(120))
