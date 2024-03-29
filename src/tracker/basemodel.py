import re
from typing import Annotated, Iterable, Self

from sqlalchemy import Identity, Integer, MetaData, Text
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


def _split_camel(s: str) -> Iterable[str]:
    """Yield substrings at transitions from non-uppercase ASCII to uppercase ASCII."""
    prev = 0
    for m in re.finditer(r"[^A-Z][A-Z]", s):
        e = m.span()[1] - 1
        yield s[prev:e]
        prev = e
    yield s[prev:]
