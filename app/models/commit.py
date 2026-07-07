from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Boolean, DateTime, String
from datetime import datetime
from dbwarden.schema import auto_schema
from dbwarden import CHTableMeta, ChEngineSpec

from app.core.databases import Base

@auto_schema
class Commit(Base):
    __tablename__ = "commits"

    repo : Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    sha : Mapped[str] = mapped_column(String, nullable=False)
    author_login : Mapped[str] = mapped_column(String, nullable=False)
    author_name : Mapped[str] = mapped_column(String, nullable=False)
    author_email : Mapped[str] = mapped_column(String, nullable=False)
    message : Mapped[str] = mapped_column(String, nullable=True)
    is_merge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    class Meta(CHTableMeta):
        ch_engine = ChEngineSpec("MergeTree")
        ch_order_by = ["repo", "committed_at"]
        ch_primary_key = "repo"
        comment = "Commit event store"
