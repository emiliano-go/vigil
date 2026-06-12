from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean
from dbwarden.schema import auto_schema
from dbwarden import ChEngineSpec

from app.core.databases import Base

@auto_schema
class Repo(Base):
    __tablename__ = "repos"

    name : Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    owner : Mapped[str] = mapped_column(String, nullable=False)
    is_org : Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_branch : Mapped[str] = mapped_column(String, nullable=False)

    class Meta:
        ch_engine = ChEngineSpec("ReplacingMergeTree")
        ch_order_by = ["name"]
        ch_primary_key = "name"
        comment = "Repo store"