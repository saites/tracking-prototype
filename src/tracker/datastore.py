"""
This module defines functions to manipulate data this project manages. 
"""

import uuid
from typing import TypeVar

import sqlalchemy.exc
from sqlalchemy import Engine, StaticPool, create_engine, engine, event, select
from sqlalchemy.orm import Session

from . import errors
from .datamodel import (
    BaseModel,
    CentiCelcius,
    Device,
    Dimmer,
    Dwelling,
    Hub,
    Lock,
    LockState,
    OccupancyState,
    Switch,
    SwitchState,
    ThermoDisplay,
    ThermoMode,
    ThermoOperation,
    Thermostat,
)


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

    BaseModel.metadata.create_all(db_engine)

    return db_engine


ItemT = TypeVar(
    "ItemT", Dwelling, Hub, Switch, Dimmer, Lock, Thermostat, Device, covariant=True
)
ItemTA = Dwelling | Hub | Switch | Dimmer | Lock | Thermostat | Device


def get_by_name(session: Session, kind: type[ItemT], name: str, operation: str) -> ItemT:
    """Find an item by name."""

    try:
        return session.scalars(select(kind).where(kind.name == name)).one()
    except sqlalchemy.exc.NoResultFound:
        raise errors.NoResultError(kind.__tablename__, name, operation)


def rename(session: Session, kind: type[ItemT], old_name: str, new_name: str) -> None:
    """Rename an item."""

    get_by_name(session, kind, old_name, "rename").name = new_name


def delete(session: Session, kind: type[ItemT], name: str) -> None:
    """Delete an item."""

    item = get_by_name(session, kind, name, "delete")
    if isinstance(item, Device) and item.hub is not None:
        raise errors.PairedError(item.kind.name, name, "Hub", item.hub.name, "delete")
    elif isinstance(item, Hub) and item.dwelling is not None:
        raise errors.PairedError("Hub", name, "Dwelling", item.dwelling.name, "delete")
    elif isinstance(item, Hub) and len(item.devices) > 0:
        raise errors.HasDependenciesError("Hub", name, "delete")
    elif isinstance(item, Dwelling) and len(item.hubs) > 0:
        raise errors.HasDependenciesError("Dwelling", name, "delete")

    session.delete(item)


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


def pair_device(session: Session, kind: type[Device], device_name: str, hub_name: str) -> None:
    """Associate a `Device` with a `Hub`."""

    device = get_by_name(session, kind, device_name, "pair device")
    hub = get_by_name(session, Hub, hub_name, "pair device")

    if device.hub is not None and device.hub_id != hub.id:
        raise errors.PairedError(
            device.kind.name, device.name, "Hub", device.hub.name, "pair device"
        )

    device.hub = hub


def unpair_device(session: Session, kind: type[Device], device_name: str) -> None:
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

    session.add(
        Dimmer(name, min_value=min_value, max_value=max_value, scale=scale, value=min_value)
    )


def new_lock(session: Session, name: str, pin: str) -> None:
    """Create a new `Lock`."""

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
    # Of course, in reality, this would be directed by the device itself.
    # We would just query the state (or ideally, be notified of it).
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

    lock = get_by_name(session, Lock, name, "lock")
    if pin not in lock.pin_codes:
        lock.pin_codes.append(pin)


def remove_lock_pin(session: Session, name: str, pin: str) -> None:
    """Remove a `pin` from a `Lock`."""

    lock = get_by_name(session, Lock, name, "lock")
    if pin not in lock.pin_codes:
        raise errors.InvalidPinError()

    lock.pin_codes.remove(pin)
