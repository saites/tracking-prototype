"""
This module defines functions to manipulate data this project manages. 
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Iterator, TypeAlias, TypeVar

import sqlalchemy.exc
from sqlalchemy import Engine, StaticPool, create_engine, engine, event, select
from sqlalchemy.orm import Session

from . import errors
from .datamodel import (
    BaseModel,
    CentiCelsius,
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
    @event.listens_for(db_engine, "connect")
    def on_connect(dbapi_connection, connection_record):  # type: ignore
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(db_engine, "begin")
    def on_begin(conn):  # type: ignore
        conn.exec_driver_sql("BEGIN")

    BaseModel.metadata.create_all(db_engine)

    return db_engine


PlaceOrDevice: TypeAlias = Dwelling | Hub | Device
PlaceOrDeviceT = TypeVar("PlaceOrDeviceT", bound=PlaceOrDevice)


class DataStore:
    """A DataStore provides access to DataSessions for DataTransactions."""

    def __init__(self, engine: Engine | None = None) -> None:
        if engine is None:
            engine = get_sqlite_engine()
        self.engine = engine

    @contextlib.contextmanager
    def session(self) -> Iterator[DataSession]:
        """Get a DataSession for multiple transactions."""

        with Session(self.engine) as session:
            yield DataSession(session)


class DataSession:
    """Provides a context for individual transactions by wrapping the Session object.

    This is not really an ideal way to work with SQLAlchemy,
    but is done to hide the implementation from the driver script that calls into this.
    In a more realistic practice, incoming operations would generate their own session
    and inject it into handlers that interact with the datamodel classes.
    Doing it that way reduces the temptation to interact with mapped classes outside a session, 
    which would implicitly begin a new transaction context (which should then be committed).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    @contextlib.contextmanager
    def transaction(self) -> Iterator[DataTransaction]:
        self.session.begin()
        try:
            yield DataTransaction(self.session)
            self.session.commit()
        except sqlalchemy.exc.IntegrityError as err:
            self.session.rollback()
            raise errors.TrackerError(str(err.orig)) from err
        except:
            self.session.rollback()
            raise


class DataTransaction:
    """A DataTransaction execute operations within a single data transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_all(self, kind: type[PlaceOrDeviceT]) -> Iterator[PlaceOrDeviceT]:
        """Get all items of a certain kind."""

        return self.session.scalars(select(kind))

    def get_all_names(self, kind: type[PlaceOrDeviceT]) -> Iterator[str]:
        """Get the names of all items of a certain kind."""

        return self.session.scalars(select(kind.name))

    def get_by_name(
        self, kind: type[PlaceOrDeviceT], name: str, operation: str = "get"
    ) -> PlaceOrDeviceT:
        """Find an item by name."""

        try:
            return self.session.scalars(select(kind).where(kind.name == name)).one()
        except sqlalchemy.exc.NoResultFound:
            raise errors.NoResultError(kind.__tablename__, name, operation)

    def rename(self, kind: type[PlaceOrDevice], old_name: str, new_name: str) -> None:
        """Rename an item."""

        self.get_by_name(kind, old_name, "rename").name = new_name

    def delete(self, kind: type[PlaceOrDevice], name: str) -> None:
        """Delete an item."""

        item = self.get_by_name(kind, name, "delete")
        if isinstance(item, Device) and item.hub is not None:
            raise errors.PairedError(item.kind.name, name, "Hub", item.hub.name, "delete")
        elif isinstance(item, Hub) and item.dwelling is not None:
            raise errors.PairedError("Hub", name, "Dwelling", item.dwelling.name, "delete")
        elif isinstance(item, Hub) and len(item.devices) > 0:
            raise errors.HasDependenciesError("Hub", name, "delete")
        elif isinstance(item, Dwelling) and len(item.hubs) > 0:
            raise errors.HasDependenciesError("Dwelling", name, "delete")

        self.session.delete(item)

    def install_hub(self, hub_name: str, dwelling_name: str) -> None:
        """Associate a `Hub` with a `Dwelling`."""

        hub = self.get_by_name(Hub, hub_name, "install hub")
        dwelling = self.get_by_name(Dwelling, dwelling_name, "install hub")

        if hub.dwelling is not None and hub.dwelling_id != dwelling.id:
            raise errors.PairedError(
                "Hub", hub.name, "Dwelling", hub.dwelling.name, "install hub"
            )

        hub.dwelling = dwelling

    def uninstall_hub(self, hub_name: str) -> None:
        """Disassociate a `Hub` from its `Dwelling`."""

        hub = self.get_by_name(Hub, hub_name, "uninstall hub")

        if hub.dwelling is None:
            raise errors.UnpairedError("Hub", hub.name, "Dwelling", "uninstall hub")

        hub.dwelling = None

    def pair_device(self, kind: type[Device], device_name: str, hub_name: str) -> None:
        """Associate a `Device` with a `Hub`."""

        device = self.get_by_name(kind, device_name, "pair device")
        hub = self.get_by_name(Hub, hub_name, "pair device")

        if device.hub is not None and device.hub_id != hub.id:
            raise errors.PairedError(
                device.kind.name, device.name, "Hub", device.hub.name, "pair device"
            )

        device.hub = hub

    def unpair_device(self, kind: type[Device], device_name: str) -> None:
        """Disassociate a `Device` from its `Hub`."""

        device = self.get_by_name(kind, device_name, "unpair device")

        if device.hub is None:
            raise errors.UnpairedError(device.kind.name, device.name, "Hub", "unpair device")

        device.hub = None

    def new_dwelling(self, name: str) -> Dwelling:
        """Create a new `Dwelling`."""

        dwelling = Dwelling(name)
        self.session.add(dwelling)
        return dwelling

    def new_hub(self, name: str) -> Hub:
        """Create a new `Hub`."""

        hub = Hub(name)
        self.session.add(hub)
        return hub

    def new_switch(self, name: str) -> Switch:
        """Create a new `Switch`."""

        switch = Switch(name)
        self.session.add(switch)
        return switch

    def new_dimmer(self, name: str, min_value: int, max_value: int, scale: int) -> Dimmer:
        """Create a new `Dimmer`."""

        dimmer = Dimmer(
            name, min_value=min_value, max_value=max_value, scale=scale, value=min_value
        )
        self.session.add(dimmer)
        return dimmer

    def new_lock(self, name: str, pin: str) -> Lock:
        """Create a new `Lock`."""

        lock = Lock(name, pin_codes=[pin])
        self.session.add(lock)
        return lock

    def new_thermostat(self, name: str, display: ThermoDisplay) -> Thermostat:
        """Create a new `Thermostat`."""

        thermostat = Thermostat(name, display=display)
        self.session.add(thermostat)
        return thermostat

    def update_dimmer(self, name: str, min_value: int, max_value: int, scale: int) -> None:
        """Change the range or scale of an existing `Dimmer`."""

        dimmer = self.get_by_name(Dimmer, name, "update range")
        dimmer.value = min_value
        dimmer.min_value = min_value
        dimmer.max_value = max_value
        dimmer.scale = scale

    def update_thermostat(self, name: str, display: ThermoDisplay) -> None:
        """Change the display mode for a `Thermostat`."""

        self.get_by_name(Thermostat, name, "update mode").display = display

    def set_dwelling_occupancy(self, name: str, state: OccupancyState) -> None:
        """Change the occupancy state of a `Dwelling`."""

        self.get_by_name(Dwelling, name, "set occupancy").occupancy = state

    def set_switch_state(self, name: str, state: SwitchState) -> None:
        """Set a `Switch`'s state."""

        switch = self.get_by_name(Switch, name, "set state")
        switch.state = state

    def set_dimmer_value(self, name: str, value: int) -> None:
        """Set a `Dimmer`'s value."""

        dimmer = self.get_by_name(Dimmer, name, "set")
        if not (dimmer.min_value <= value <= dimmer.max_value):
            raise errors.OutOfRangeError(
                "Dimmer", name, value, dimmer.min_value, dimmer.max_value, "set"
            )

        dimmer.value = value

    def _change_thermo_state(self, thermo: Thermostat) -> None:
        """Check and, if necessary, change the `Thermostat`'s mode to reach the target temperature."""

        if thermo.mode is ThermoMode.Off:
            return

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

    def set_thermo_mode(self, name: str, mode: ThermoMode) -> None:
        """Set a `Thermostat`'s operation mode."""

        thermo = self.get_by_name(Thermostat, name, "set mode")
        thermo.mode = mode
        self._change_thermo_state(thermo)

    def set_thermo_current_temp(self, name: str, value: CentiCelsius) -> None:
        """Set a `Thermostat`'s current temperature.

        In principle, this would be the device updating the system about the current value,
        or our system polling the device and updating our state on some cadence.
        """

        thermo = self.get_by_name(Thermostat, name, "set current temperature")
        thermo.current_centi_c = value
        self._change_thermo_state(thermo)

    def set_thermo_set_points(self, name: str, low: CentiCelsius, high: CentiCelsius) -> None:
        """Set a `Thermostat`'s low and high set points."""

        thermo = self.get_by_name(Thermostat, name, "set temperature")
        thermo.low_centi_c = low
        thermo.high_centi_c = high
        self._change_thermo_state(thermo)

    def lock_door(self, name: str) -> None:
        """Set a `Lock` to locked."""

        self.get_by_name(Lock, name, "lock").state = LockState.Locked

    def unlock_door(self, name: str, pin: str) -> None:
        """Attempt to unlock a `Lock`, if the `pin` is correct ."""

        lock = self.get_by_name(Lock, name, "lock")
        if pin not in lock.pin_codes:
            raise errors.InvalidPinError()

        lock.state = LockState.Unlocked

    def add_lock_pin(self, name: str, pin: str) -> None:
        """Add a new `pin` to a `Lock`. Does nothing if it is already present."""

        lock = self.get_by_name(Lock, name, "lock")
        if pin not in lock.pin_codes:
            lock.pin_codes.append(pin)

    def remove_lock_pin(self, name: str, pin: str) -> None:
        """Remove a `pin` from a `Lock`."""

        lock = self.get_by_name(Lock, name, "lock")
        if pin not in lock.pin_codes:
            raise errors.InvalidPinError()

        lock.pin_codes.remove(pin)
