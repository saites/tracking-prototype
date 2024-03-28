import re
import uuid
from typing import Annotated, Iterable, Self

from sqlalchemy import (
    Engine,
    Identity,
    Integer,
    MetaData,
    StaticPool,
    Text,
    create_engine,
    engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    declared_attr,
    mapped_column,
)

DbID = Annotated[int, mapped_column()]
"""A database Identifier."""

VersionStr = Annotated[str, mapped_column(Text)]
"""A version string."""

CentiCelcius = Annotated[int, mapped_column(Integer)]
"""1/100 of a degree Celcius."""

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class BaseModel(MappedAsDataclass, DeclarativeBase):
    metadata = metadata

    @declared_attr.directive
    def __tablename__(cls: Self) -> str:
        """Use snake_case names for tables."""
        return "_".join(p.lower() for p in _split_camel(cls.__name__))


class AutoID(MappedAsDataclass):
    """Mixin to add a primary key column named 'id'."""

    id: Mapped[DbID] = mapped_column(Identity(always=True), primary_key=True, init=False)


def get_sqlite_engine(db_name: str | None = None) -> Engine:
    """Return an in-memory SQLite database engine, configured with sensible defaults."""

    # Use an in-memory database, potentially shared among multiple threads.
    # This requires a recent version of SQLite, but this project targets Python 3.11 anyway.
    db_url = engine.URL.create(
        drivername="sqlite",
        database=db_name or f"file:{uuid.uuid4().int:x}",
        query={"mode": "memory", "check_same_thread": "false", "uri": "true"},
    )

    db_engine = create_engine(db_url, poolclass=StaticPool)

    # Fix transactional support in the default sqlite driver:
    # - disable BEGIN on connect; emit it at the proper point
    # - disable COMMIT before DDL
    # - enable foreign key support
    # See: https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#pysqlite-serializable
    @event.listens_for(Engine, "connect")
    def on_connect(dbapi_connection, connection_record):  # type: ignore
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(Engine, "begin")
    def on_begin(conn):  # type: ignore
        conn.exec_driver_sql("BEGIN")

    metadata.create_all(db_engine)

    return db_engine


def _split_camel(s: str) -> Iterable[str]:
    """Yield substrings at transitions from non-uppercase ASCII to uppercase ASCII."""
    prev = 0
    for m in re.finditer(r"[^A-Z][A-Z]", s):
        e = m.span()[1] - 1
        yield s[prev:e]
        prev = e
    yield s[prev:]
