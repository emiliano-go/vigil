from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean
from dbwarden.schema import auto_schema
from dbwarden.seed import Seed
from dbwarden import CHTableMeta, ChEngineSpec

from app.core.databases import Base

@auto_schema
class Repo(Base):
    __tablename__ = "repos"

    name : Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    owner : Mapped[str] = mapped_column(String, nullable=False)
    is_org : Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_branch : Mapped[str] = mapped_column(String, nullable=False)

    class Meta(CHTableMeta):
        ch_engine = ChEngineSpec("ReplacingMergeTree")
        ch_order_by = ["name"]
        ch_primary_key = "name"
        comment = "Repo store"

class RepoSeed(Seed):
    __seed_database__ = "clickhouse"
    __seed_description__ = "Tracked Repos"
    __seed_on_conflict__ = "update"

    model = Repo
    rows = [
        Repo(name="dbwarden", owner="emiliano-go", is_org=False, default_branch="main"),
        Repo(name="schemap", owner="emiliano-go", is_org=False, default_branch="master"),
        Repo(name="crxml", owner="emiliano-go", is_org=False, default_branch="master"),
        Repo(name="detrack", owner="emiliano-go", is_org=False, default_branch="master"),
        Repo(name="seoslug", owner="emiliano-go", is_org=False, default_branch="master"),
        Repo(name="acrresolv", owner="emiliano-go", is_org=False, default_branch="master"),
        Repo(name="emiliano-go", owner="emiliano-go", is_org=False, default_branch="main"),
        Repo(name="equinox", owner="emiliano-go", is_org=False, default_branch="main"),
        Repo(name="ArgosUY", owner="LibreCourseUY", is_org=True, default_branch="main"),
        Repo(name="UruAPI", owner="LibreCourseUY", is_org=True, default_branch="main"),
        Repo(name="web", owner="LibreCourseUY", is_org=True, default_branch="main"),
    ]