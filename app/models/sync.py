from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, ForeignKey
from datetime import datetime
from dbwarden.schema._auto_schema import auto_schema
from dbwarden import CHTableMeta, ChEngineSpec

from app.core.databases import Base

@auto_schema
class SyncState(Base):
    __tablename__ = "sync_state"

    repo : Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    last_synced_sha : Mapped[str] = mapped_column(String, nullable=False)
    last_synced_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_status : Mapped[str] = mapped_column(String, nullable=False)
    last_run_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    class Meta(CHTableMeta):
        ch_engine = ChEngineSpec("ReplacingMergeTree")
        ch_order_by = ["repo"]
        ch_primary_key = "repo"
        comment = "Sync State"
