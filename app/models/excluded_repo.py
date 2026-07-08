from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from dbwarden.schema._auto_schema import auto_schema
from dbwarden import CHTableMeta, ChEngineSpec

from app.core.databases import Base

@auto_schema
class ExcludedRepo(Base):
    __tablename__ = "excluded_repos"

    full_name : Mapped[str] = mapped_column(String, primary_key=True, nullable=False)

    class Meta(CHTableMeta):
        ch_engine = ChEngineSpec("ReplacingMergeTree")
        ch_order_by = ["full_name"]
        ch_primary_key = "full_name"
        comment = "Repos excluded from sync"
