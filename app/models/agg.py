from datetime import date

from dbwarden import CHTableMeta
from dbwarden.databases import summing_merge_tree
from dbwarden.schema._auto_schema import auto_schema
from sqlalchemy import BigInteger, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.databases import Base


@auto_schema
class CommitsPerDay(Base):
    __tablename__ = "commits_per_day"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    day: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False)

    class Meta(CHTableMeta):
        ch_engine = summing_merge_tree("total")
        ch_order_by = ["repo", "day"]
        ch_primary_key = ["repo", "day"]
        comment = "Daily commit counts per repo"


@auto_schema
class CommitsPerDayMV(Base):
    __tablename__ = "commits_per_day_mv"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    day: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    class Meta(CHTableMeta):
        ch_object_type = "materialized_view"
        ch_to_table = "commits_per_day"
        ch_select_statement = (
            "SELECT repo, toDate(committed_at) AS day, count() AS total "
            "FROM commits GROUP BY repo, day"
        )
        comment = "Materialized view for commits per day"


@auto_schema
class CommitsPerMonth(Base):
    __tablename__ = "commits_per_month"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    month: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False)

    class Meta(CHTableMeta):
        ch_engine = summing_merge_tree("total")
        ch_order_by = ["repo", "month"]
        ch_primary_key = ["repo", "month"]
        comment = "Monthly commit counts per repo"


@auto_schema
class CommitsPerMonthMV(Base):
    __tablename__ = "commits_per_month_mv"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    month: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    class Meta(CHTableMeta):
        ch_object_type = "materialized_view"
        ch_to_table = "commits_per_month"
        ch_select_statement = (
            "SELECT repo, toStartOfMonth(committed_at) AS month, count() AS total "
            "FROM commits GROUP BY repo, month"
        )
        comment = "Materialized view for commits per month"


@auto_schema
class AuthorCommitCounts(Base):
    __tablename__ = "author_commit_counts"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    author_login: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False)

    class Meta(CHTableMeta):
        ch_engine = summing_merge_tree("total")
        ch_order_by = ["repo", "author_login"]
        ch_primary_key = ["repo", "author_login"]
        comment = "Commit counts per repo and author"


@auto_schema
class AuthorCommitCountsMV(Base):
    __tablename__ = "author_commit_counts_mv"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    author_login: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    class Meta(CHTableMeta):
        ch_object_type = "materialized_view"
        ch_to_table = "author_commit_counts"
        ch_select_statement = (
            "SELECT repo, author_login, count() AS total "
            "FROM commits GROUP BY repo, author_login"
        )
        comment = "Materialized view for author commit counts"


@auto_schema
class HourlyActivity(Base):
    __tablename__ = "hourly_activity"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False)

    class Meta(CHTableMeta):
        ch_engine = summing_merge_tree("total")
        ch_order_by = ["repo", "hour"]
        ch_primary_key = ["repo", "hour"]
        comment = "Commit counts by hour of day per repo"


@auto_schema
class HourlyActivityMV(Base):
    __tablename__ = "hourly_activity_mv"

    repo: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    class Meta(CHTableMeta):
        ch_object_type = "materialized_view"
        ch_to_table = "hourly_activity"
        ch_select_statement = (
            "SELECT repo, toHour(committed_at) AS hour, count() AS total "
            "FROM commits GROUP BY repo, hour"
        )
        comment = "Materialized view for hourly activity"
