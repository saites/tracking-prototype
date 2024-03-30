"""
This module defines the types used by this service and the relationships among them.
"""

from __future__ import annotations

import re
import typing
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Iterable, Protocol, Self

import sqlalchemy
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Text,
    case,
)
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    column_property,
    declared_attr,
    mapped_column,
    relationship,
)

DbID = Annotated[int, mapped_column()]
"""A database Identifier."""

VersionStr = Annotated[str, mapped_column(Text)]
"""A version string."""

CentiCelsius = Annotated[int, mapped_column(Integer)]
"""1/100 of a degree Celsius."""


class BaseModel(MappedAsDataclass, DeclarativeBase):
    """Base class used to map between Python classes and database tables."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )

    @declared_attr.directive
    def __tablename__(cls: Self) -> str:
        """Use snake_case names for tables."""
        return "_".join(p.lower() for p in _split_camel(cls.__name__))


def _split_camel(s: str) -> Iterable[str]:
    """Yield substrings at transitions from non-uppercase ASCII to uppercase ASCII."""

    prev = 0
    for m in re.finditer(r"[^A-Z][A-Z]", s):
        e = m.span()[1] - 1
        yield s[prev:e]
        prev = e
    yield s[prev:]


class AutoID(MappedAsDataclass):
    """Adds a primary key column named 'id' to a table when mixed-in."""

    id: Mapped[DbID] = mapped_column(Identity(always=True), primary_key=True, init=False)


class DeviceKind(Enum):
    """Device kinds; used as discriminator in common-properties table."""

    Unknown = "unknown"
    Switch = "switch"
    Dimmer = "dimmer"
    Lock = "lock"
    Thermostat = "thermostat"


class OccupancyState(Enum):
    """States of a Dwelling's occupancy."""

    Vacant = "vacant"
    Occupied = "occupied"


class SwitchState(Enum):
    """States for a switch."""

    On = "on"
    Off = "off"


class LockState(Enum):
    """States of a door lock."""

    Locked = "locked"
    Unlocked = "unlocked"


class ThermoDisplay(Enum):
    """Thermostat display format."""

    Celcius = "c"
    Fahrenheit = "f"


class ThermoMode(Enum):
    """Thermostat modes: whether to heat, cool, both, or neither."""

    Off = "off"
    Heat = "heat"
    Cool = "cool"
    HeatCool = "heatcool"


class ThermoOperation(Enum):
    """Heating/Cooling command sent by a Thermostat to the heat pump it controls."""

    Off = "off"
    Heating = "heating"
    Cooling = "cooling"


class Dwelling(AutoID, BaseModel):
    """A living space where hubs and devices can be installed."""

    name: Mapped[str] = mapped_column(unique=True, index=True)
    occupancy: Mapped[OccupancyState] = mapped_column(default=OccupancyState.Vacant)
    hubs: Mapped[list[Hub]] = relationship(default_factory=list, back_populates="dwelling")
    devices: Mapped[list[Device]] = relationship(
        default_factory=list, secondary="hub", viewonly=True
    )


class Hardware(MappedAsDataclass):
    """A mixin class that adds columns for common hardware properties."""

    hardware_version: Mapped[VersionStr] = mapped_column(default="0.0.0", kw_only=True)
    firmware_version: Mapped[VersionStr] = mapped_column(default="0.0.0", kw_only=True)
    firmware_updated: Mapped[datetime] = mapped_column(
        default_factory=datetime.now, kw_only=True
    )
    created_at: Mapped[datetime] = mapped_column(default_factory=datetime.now, kw_only=True)
    updated_at: Mapped[datetime] = mapped_column(default_factory=datetime.now, kw_only=True)


class Hub(AutoID, Hardware, BaseModel):
    """A Hub manages a collection of Devices."""

    name: Mapped[str] = mapped_column(unique=True, index=True)

    # A Hub is associated with a Dwelling.
    dwelling_id: Mapped[DbID | None] = mapped_column(
        ForeignKey("dwelling.id"), nullable=True, init=False
    )
    dwelling: Mapped[Dwelling | None] = relationship(
        lambda: Dwelling, back_populates="hubs", default=None
    )

    # Devices are associated with a Hub.
    devices: Mapped[list[Device]] = relationship(
        lambda: Device,
        default_factory=list,
        back_populates="hub",
        order_by=lambda: Device.created_at.desc(),
    )


class NamedClass(Protocol):
    """This is used to help the type-checker in the next mixin."""

    @property
    def __name__(self) -> str: ...


class DeviceID:
    """Generates ID column to relate tables with device-type-specific properties
    to the "device" table, which holds properties common to all devices.
    """

    @declared_attr.cascading  # type: ignore
    def id(cls: NamedClass) -> Mapped[DbID]:
        if cls.__name__ == "Device":
            return mapped_column(Integer, Identity(always=True), primary_key=True, init=False)
        else:
            return mapped_column(
                Integer, ForeignKey("device.id"), primary_key=True, init=False
            )

    @declared_attr.directive
    def __mapper_args__(cls: NamedClass) -> dict[str, Any]:
        if cls.__name__ == "Device":
            return {
                "polymorphic_identity": DeviceKind.Unknown,
                "polymorphic_on": "kind",
            }

        try:
            return {"polymorphic_identity": DeviceKind(cls.__name__.lower())}
        except ValueError:
            raise TypeError(f"Device {cls.__name__.lower()} is not a declared DeviceKind")


class Device(DeviceID, Hardware, BaseModel):
    """A Device is an IoT entity which reports reading, has state, and/or can be controlled."""

    kind: Mapped[DeviceKind] = mapped_column(init=False)
    name: Mapped[str] = mapped_column()
    hub_id: Mapped[DbID | None] = mapped_column(
        ForeignKey("hub.id"), nullable=True, init=False
    )
    hub: Mapped[Hub | None] = relationship(Hub, back_populates="devices", default=None)

    __table_args__ = (Index("ix_kind_name", kind, name, unique=True),)


class Switch(Device):
    """A device that can be turned on or off."""

    state: Mapped[SwitchState] = mapped_column(default=SwitchState.Off)


class Dimmer(Device):
    """A device that provides variable lighting."""

    value: Mapped[int] = mapped_column(default=0)
    min_value: Mapped[int] = mapped_column(default=0)
    max_value: Mapped[int] = mapped_column(default=100)
    scale: Mapped[int] = mapped_column(default=1)

    display_value: Mapped[float] = column_property(value / scale)


DimmerTable = typing.cast(sqlalchemy.Table, Dimmer.__table__)
DimmerTable.append_constraint(
    CheckConstraint("min_value <= max_value", name="range_is_valid"),
)
DimmerTable.append_constraint(
    CheckConstraint("min_value <= value AND value <= max_value", name="value_in_range"),
)
DimmerTable.append_constraint(CheckConstraint("scale != 0", name="scale_not_zero"))


class Lock(Device):
    """A device that can be open/shut and has PIN codes for entry."""

    state: Mapped[LockState] = mapped_column(default=LockState.Unlocked)

    # lock_pins tells the ORM the direct relationship between Lock and LockPin,
    # but pin_codes gives a more Pythonic interface to the underlying code.
    lock_pins: Mapped[list["LockPin"]] = relationship(
        lambda: LockPin,
        default_factory=list,
        back_populates="lock",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    pin_codes: AssociationProxy[list[str]] = association_proxy(
        "lock_pins", "pin", default_factory=list
    )


class LockPin(BaseModel):
    """A PIN that can be used to unlock a door."""

    lock_id: Mapped[DbID] = mapped_column(
        ForeignKey("lock.id", ondelete="CASCADE"), init=False, primary_key=True
    )
    pin: Mapped[str] = mapped_column(primary_key=True)
    lock: Mapped[Lock] = relationship(Lock, back_populates="lock_pins", init=False)

    __table_args__ = (
        CheckConstraint("pin REGEXP '^[0-9]{4,}$'", name="pin_is_four_or_more_digits"),
    )


class Thermostat(Device):
    """A device for controlling heat/cool levels in a dwelling."""

    mode: Mapped[ThermoMode] = mapped_column(default=ThermoMode.Off)
    state: Mapped[ThermoOperation] = mapped_column(default=ThermoOperation.Off)
    display: Mapped[ThermoDisplay] = mapped_column(default=ThermoDisplay.Celcius)
    low_centi_c: Mapped[CentiCelsius] = mapped_column(default=2220)
    high_centi_c: Mapped[CentiCelsius] = mapped_column(default=2220)
    current_centi_c: Mapped[CentiCelsius] = mapped_column(default=2220)
    target_centi_c: Mapped[CentiCelsius] = mapped_column(default=2220)

    display_low: Mapped[float] = column_property(
        case(
            (display == ThermoDisplay.Celcius.name, low_centi_c / 100.0),
            else_=(9 * low_centi_c / 500.0 + 32.0),  # C to F: (temp/100.0) * (9/5) + 32.0
        )
    )
    display_high: Mapped[float] = column_property(
        case(
            (display == ThermoDisplay.Celcius.name, high_centi_c / 100.0),
            else_=(9 * high_centi_c / 500.0 + 32.0),
        )
    )
    display_current: Mapped[float] = column_property(
        case(
            (display == ThermoDisplay.Celcius.name, current_centi_c / 100.0),
            else_=(9 * current_centi_c / 500.0 + 32.0),
        )
    )


ThermoTable = typing.cast(sqlalchemy.Table, Thermostat.__table__)
ThermoTable.append_constraint(
    CheckConstraint("low_centi_c <= high_centi_c", name="high_temp_above_low")
)
