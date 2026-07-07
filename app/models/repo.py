from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean
from dbwarden.schema._auto_schema import auto_schema
from dbwarden import CHTableMeta, ChEngineSpec

from app.core.databases import Base

@auto_schema
class Repo(Base):
    __tablename__ = "repos"

    full_name : Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    name : Mapped[str] = mapped_column(String, nullable=False)
    owner : Mapped[str] = mapped_column(String, nullable=False)
    is_org : Mapped[bool] = mapped_column(Boolean, nullable=False)
    private : Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_branch : Mapped[str] = mapped_column(String, nullable=False)

    class Meta(CHTableMeta):
        ch_engine = ChEngineSpec("ReplacingMergeTree")
        ch_order_by = ["full_name"]
        ch_primary_key = "full_name"
        comment = "Repo store"
