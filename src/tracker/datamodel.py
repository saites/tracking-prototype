import re
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Self, TypeVar

import sqlalchemy
from sqlalchemy import CheckConstraint, ForeignKey, Index, case, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import (
    Mapped,
    MappedAsDataclass,
    Session,
    column_property,
    declared_attr,
    mapped_column,
    relationship,
)

from . import errors
from .basemodel import AutoID, BaseModel, CentiCelcius, DbID, VersionStr


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
    """Thermostat diplay format."""

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
    dwelling: Mapped[Optional["Dwelling"]] = relationship(
        lambda: Dwelling, back_populates="hubs", default=None
    )

    # Devices are associated with a Hub.
    devices: Mapped[list["Device"]] = relationship(
        lambda: Device,
        default_factory=list,
        back_populates="hub",
        order_by=lambda: Device.created_at.desc(),
    )


class Device(AutoID, Hardware, BaseModel):
    """A Device is an IoT entity which reports reading, has state, and/or can be controlled."""

    kind: Mapped[DeviceKind] = mapped_column(init=False)
    name: Mapped[str] = mapped_column()
    hub_id: Mapped[DbID | None] = mapped_column(
        ForeignKey("hub.id"), nullable=True, init=False
    )
    hub: Mapped[Hub | None] = relationship(Hub, back_populates="devices", default=None)

    __mapper_args__ = {
        "polymorphic_identity": DeviceKind.Unknown,
        "polymorphic_on": "kind",
    }

    __table_args__ = (Index("ix_kind_name", kind, name, unique=True),)


class Dwelling(AutoID, BaseModel):
    """A living space where hubs and devices can be installed."""

    name: Mapped[str] = mapped_column(unique=True, index=True)
    occupancy: Mapped[OccupancyState] = mapped_column(default=OccupancyState.Vacant)
    hubs: Mapped[list[Hub]] = relationship(default_factory=list, back_populates="dwelling")
    devices: Mapped[list[Device]] = relationship(
        default_factory=list, secondary="hub", viewonly=True
    )


class DeviceHardware(MappedAsDataclass):
    """Mixin used for subclasses of Device."""

    @declared_attr
    def id(cls: Self) -> Mapped[DbID]:
        return mapped_column(ForeignKey("device.id"), primary_key=True, init=False)

    @declared_attr.directive
    def __mapper_args__(cls: Self) -> dict[str, Any]:
        try:
            return {"polymorphic_identity": DeviceKind(cls.__name__.lower())}
        except ValueError:
            raise TypeError(f"Device {cls.__name__.lower()} is not a declared DeviceKind")


class Switch(DeviceHardware, Device):
    """A device that can be turned on or off."""

    state: Mapped[SwitchState] = mapped_column(default=SwitchState.Off)


class Dimmer(DeviceHardware, Device):
    """A device that provides variable lighting."""

    value: Mapped[int] = mapped_column(default=0)
    min_value: Mapped[int] = mapped_column(default=0)
    max_value: Mapped[int] = mapped_column(default=100)
    scale: Mapped[int] = mapped_column(default=1)

    display_value: Mapped[float] = column_property(value / scale)


Dimmer.__table__.append_constraint(
    CheckConstraint("min_value <= max_value", name="range_is_valid"),
)
Dimmer.__table__.append_constraint(
    CheckConstraint("min_value <= value AND value <= max_value", name="value_in_range"),
)
Dimmer.__table__.append_constraint(CheckConstraint("scale != 0", name="scale_not_zero"))


class Lock(DeviceHardware, Device):
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


class Thermostat(DeviceHardware, Device):
    """A device for controlling heat/cool levels in a dwelling."""

    mode: Mapped[ThermoMode] = mapped_column(default=ThermoMode.Off)
    state: Mapped[ThermoOperation] = mapped_column(default=ThermoOperation.Off)
    display: Mapped[ThermoDisplay] = mapped_column(default=ThermoDisplay.Celcius)
    low_centi_c: Mapped[CentiCelcius] = mapped_column(default=2220)
    high_centi_c: Mapped[CentiCelcius] = mapped_column(default=2220)
    current_centi_c: Mapped[CentiCelcius] = mapped_column(default=2220)
    target_centi_c: Mapped[CentiCelcius] = mapped_column(default=2220)

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


Thermostat.__table__.append_constraint(
    CheckConstraint("low_centi_c <= high_centi_c", name="high_temp_above_low")
)


DeviceT = TypeVar("DeviceT", Switch, Dimmer, Lock, Thermostat, Device)
_T = TypeVar("_T", Dwelling, Hub, Switch, Dimmer, Lock, Thermostat, Device)


def get_by_name(session: Session, kind: type[_T], name: str, operation: str) -> _T:
    """Find an item by name."""

    try:
        return session.scalars(select(kind).where(kind.name == name)).one()
    except sqlalchemy.exc.NoResultFound:
        raise errors.NoResultError(kind.__tablename__, name, operation)


def rename(session: Session, kind: type[_T], old_name: str, new_name: str) -> None:
    """Rename an item."""

    get_by_name(session, kind, old_name, "rename").name = new_name


def delete(session: Session, kind: type[_T], name: str) -> None:
    """Delete an item."""

    match get_by_name(session, kind, name, "delete"):
        case Device() as d if d.hub is not None:
            raise errors.PairedError(d.kind.name, name, "Hub", d.hub.name, "delete")
        case Hub() as h if h.dwelling is not None:
            raise errors.PairedError("Hub", name, "Dwelling", h.dwelling.name, "delete")
        case Hub() as h if any(h.devices):
            raise errors.HasDependenciesError("Hub", name, "delete")
        case Dwelling() as d if any(d.hubs):
            raise errors.HasDependenciesError("Dwelling", name, "delete")
        case other:
            session.delete(other)


def install_hub(session: Session, hub_name: str, dwelling_name: str) -> None:
    """Associate a `Hub` with a `Dwelling`."""

    hub = get_by_name(session, Hub, hub_name, "install hub")
    dwelling = get_by_name(session, Dwelling, dwelling_name, "install hub")

    if hub.dwelling is not None and hub.dwelling_id != dwelling.id:
        raise errors.PairedError("Hub", hub.name, "Dwelling", hub.dwelling.name, "install hub")

    hub.dwelling = dwelling


def uninstall_hub(session: Session, hub_name: str) -> None:
    """Disassociate a `Hub` from its `Dwelling`."""

    hub = get_by_name(session, Hub, hub_name, "uninstall hub")

    if hub.dwelling is None:
        raise errors.UnpairedError("Hub", hub.name, "Dwelling", "uninstall hub")

    hub.dwelling = None


def pair_device(session: Session, kind: type[_T], device_name: str, hub_name: str) -> None:
    """Associate a `Device` with a `Hub`."""

    device = get_by_name(session, kind, device_name, "pair device")
    hub = get_by_name(session, Hub, hub_name, "pair device")

    if device.hub is not None and device.hub_id != hub.id:
        raise errors.PairedError(
            device.kind.name, device.name, "Hub", device.hub.name, "pair device"
        )

    device.hub = hub


def unpair_device(session: Session, kind: type[_T], device_name: str) -> None:
    """Disassociate a `Device` from its `Hub`."""

    device = get_by_name(session, kind, device_name, "unpair device")

    if device.hub is None:
        raise errors.UnpairedError(device.kind.name, device.name, "Hub", "unpair device")

    device.hub = None


def delete_device(session: Session, device: Device) -> None:
    """Delete a `Device`."""

    if device.hub is not None:
        raise errors.PairedError(
            device.kind.name, device.name, "Hub", device.hub.name, "delete device"
        )

    session.delete(device)


def new_dwelling(session: Session, name: str) -> None:
    """Create a new `Dwelling`."""

    session.add(Dwelling(name))


def new_hub(session: Session, name: str) -> None:
    """Create a new `Hub`."""

    session.add(Hub(name))


def new_switch(session: Session, name: str) -> None:
    """Create a new `Switch`."""

    session.add(Switch(name))


def new_dimmer(
    session: Session, name: str, min_value: int, max_value: int, scale: int
) -> None:
    """Create a new `Dimmer`."""

    if not (min_value <= max_value and scale != 0):
        raise errors.TrackerError("need low <= high and scale != 0")

    session.add(
        Dimmer(name, min_value=min_value, max_value=max_value, scale=scale, value=min_value)
    )


def new_lock(session: Session, name: str, pin: str) -> None:
    """Create a new `Lock`."""

    if not re.match(r"[0-9]{4,}", pin):
        raise errors.TrackerError("pin must be 4 or more digits (0-9 only)")

    session.add(Lock(name, pin_codes=[pin]))


def new_thermostat(session: Session, name: str, display: ThermoDisplay) -> None:
    """Create a new `Thermostat`."""

    session.add(Thermostat(name, display=display))


def update_dimmer(
    session: Session, name: str, min_value: int, max_value: int, scale: int
) -> None:
    """Change the range or scale of an existing `Dimmer`."""

    dimmer = get_by_name(session, Dimmer, name, "update range")
    dimmer.value = min_value
    dimmer.min_value = min_value
    dimmer.max_value = max_value
    dimmer.scale = scale


def update_thermostat(session: Session, name: str, display: ThermoDisplay) -> None:
    """Change the display mode for a `Thermostat`."""

    get_by_name(session, Thermostat, name, "update mode").display = display


def set_dwelling_occupancy(session: Session, name: str, state: OccupancyState) -> None:
    """Change the occupancy state of a `Dwelling`."""

    get_by_name(session, Dwelling, name, "set occupancy").occupancy = state


def set_switch_state(session: Session, name: str, state: SwitchState) -> None:
    """Set a `Switch`'s state."""

    switch = get_by_name(session, Switch, name, "set state")
    switch.state = state


def set_dimmer_value(session: Session, name: str, value: int) -> None:
    """Set a `Dimmer`'s value."""

    dimmer = get_by_name(session, Dimmer, name, "set")
    if not (dimmer.min_value <= value <= dimmer.max_value):
        raise errors.OutOfRangeError(
            "Dimmer", name, value, dimmer.min_value, dimmer.max_value, "set"
        )

    dimmer.value = value


def _change_thermo_state(thermo: Thermostat) -> None:
    """Check and, if necessary, change the `Thermostat`'s mode to reach the target temperature."""
    if thermo.mode is ThermoMode.Off:
        return

    # TODO: hysteresis
    if thermo.current_centi_c > thermo.high_centi_c and thermo.mode in (
        ThermoMode.Cool,
        ThermoMode.HeatCool,
    ):
        thermo.state = ThermoOperation.Cooling
    elif thermo.current_centi_c < thermo.low_centi_c and thermo.mode in (
        ThermoMode.Heat,
        ThermoMode.HeatCool,
    ):
        thermo.state = ThermoOperation.Heating
    else:
        thermo.state = ThermoOperation.Off


def set_thermo_mode(session: Session, name: str, mode: ThermoMode) -> None:
    """Set a `Thermostat`'s operation mode."""

    thermo = get_by_name(session, Thermostat, name, "set mode")
    thermo.mode = mode
    _change_thermo_state(thermo)


def set_thermo_current_temp(session: Session, name: str, value: CentiCelcius) -> None:
    """Set a `Thermostat`'s current temperature.

    In principle, this would be the device updating the system about the current value.
    """

    thermo = get_by_name(session, Thermostat, name, "set current temperature")
    thermo.current_centi_c = value
    _change_thermo_state(thermo)


def set_thermo_set_points(
    session: Session, name: str, low: CentiCelcius, high: CentiCelcius
) -> None:
    """Set a `Thermostat`'s low and high set points."""

    if not (low <= high):
        raise errors.TrackerError("need low <= high")

    thermo = get_by_name(session, Thermostat, name, "set temperature")
    thermo.low_centi_c = low
    thermo.high_centi_c = high
    _change_thermo_state(thermo)


def lock_door(session: Session, name: str) -> None:
    """Set a `Lock` to locked."""

    get_by_name(session, Lock, name, "lock").state = LockState.Locked


def unlock_door(session: Session, name: str, pin: str) -> None:
    """Attempt to unlock a `Lock`, if the `pin` is correct ."""

    lock = get_by_name(session, Lock, name, "lock")
    if pin not in lock.pin_codes:
        raise errors.InvalidPinError()

    lock.state = LockState.Unlocked


def add_lock_pin(session: Session, name: str, pin: str) -> None:
    """Add a new `pin` to a `Lock`. Does nothing if it is already present."""

    if not re.match(r"[0-9]{4,}", pin):
        raise errors.TrackerError("pin must be 4 or more digits (0-9 only)")

    lock = get_by_name(session, Lock, name, "lock")
    if pin not in lock.pin_codes:
        lock.pin_codes.append(pin)


def remove_lock_pin(session: Session, name: str, pin: str) -> None:
    """Remove a `pin` from a `Lock`."""

    lock = get_by_name(session, Lock, name, "lock")
    if pin not in lock.pin_codes:
        raise errors.InvalidPinError()

    lock.pin_codes.remove(pin)
