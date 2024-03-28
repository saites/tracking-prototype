import logging
import sys
import typing
from pprint import pprint

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from tracker import basemodel
from tracker import datamodel as dm
from tracker import errors

logging.basicConfig()
logger = logging.getLogger("driver")


def main(command_file: typing.TextIO, output_file: typing.TextIO) -> None:
    """Reads commands from `command_file` and processes them, writing to `output_file` as needed.

    This is called by default when this script is executed without arguments.
    In that case, `command_file` is `sys.stdin` and `output_file` is `sys.stdout`.
    """
    engine = basemodel.get_sqlite_engine()

    with Session(engine) as session:
        for line_num, line in enumerate(command_file):
            line = line.strip()
            session.begin()
            try:
                process_command(session, line, output_file)
                session.commit()
            except errors.TrackerError as err:
                logger.error(f"Command on line {line_num} failed: {err}\n\t> {line}\n")
                session.rollback()


# Create helper dicts to associate command strings to item types.
_devices = {
    "SWITCH": dm.Switch,
    "DIMMER": dm.Dimmer,
    "LOCK": dm.Lock,
    "THERMOSTAT": dm.Thermostat,
}
_kinds = _devices | {"DWELLING": dm.Dwelling, "HUB": dm.Hub}
_all_kinds = _kinds | {"DEVICE": dm.Device}
_plural_kinds = {f"{k}S": v for k, v in _all_kinds.items() if k != "SWITCH"} | {
    "SWITCHES": dm.Switch
}


def process_command(session: Session, command: str, output_file: typing.TextIO) -> None:
    """Process a command, possibly writing text to the `output_file`."""

    match command.split():
        case ["#", *_] | []:  # Skip comments and empty lines.
            return

        case ["NEW", "DWELLING", name]:
            dm.new_dwelling(session, name)
        case ["SET", "DWELLING", name, "TO", ("OCCUPIED" | "VACANT") as state]:
            dm.set_dwelling_occupancy(session, name, dm.OccupancyState(state.lower()))

        case ["NEW", "HUB", name]:
            dm.new_hub(session, name)
        case ["INSTALL", hub_name, "INTO", dwelling_name]:
            dm.install_hub(session, hub_name, dwelling_name)
        case ["UNINSTALL", hub_name]:
            dm.uninstall_hub(session, hub_name)

        case ["PAIR", kind, device_name, "WITH", hub_name] if (cls := _devices.get(kind)):
            dm.pair_device(session, cls, device_name, hub_name)
        case ["UNPAIR", kind, device_name] if (cls := _devices.get(kind)):
            dm.unpair_device(session, cls, device_name)

        case ["NEW", "SWITCH", name]:
            dm.new_switch(session, name)
        case ["SET", "SWITCH", name, "TO", ("ON" | "OFF") as state]:
            dm.set_switch_state(session, name, dm.SwitchState(state.lower()))

        case ["NEW", "DIMMER", name, "RANGE", low, "TO", high, "WITH", "FACTOR", factor]:
            dm.new_dimmer(session, name, int(low), int(high), int(factor))
        case ["MODIFY", "DIMMER", name, "RANGE", low, "TO", high, "WITH", "FACTOR", factor]:
            dm.update_dimmer(session, name, int(low), int(high), int(factor))
        case ["SET", "DIMMER", name, "TO", value]:
            dm.set_dimmer_value(session, name, int(value))

        case ["NEW", "LOCK", name, "WITH", "PIN", pin]:
            dm.new_lock(session, name, pin)
        case ["MODIFY", "LOCK", name, "ADD", "PIN", pin]:
            dm.add_lock_pin(session, name, pin)
        case ["MODIFY", "LOCK", name, "REMOVE", "PIN", pin]:
            dm.remove_lock_pin(session, name, pin)
        case ["SET", "LOCK", name, "TO", "LOCKED"]:
            dm.lock_door(session, name)
        case ["SET", "LOCK", name, "TO", "UNLOCKED", "USING", pin]:
            dm.unlock_door(session, name, pin)

        case ["NEW", "THERMOSTAT", name, "WITH", "DISPLAY", "IN", ("C" | "F") as display]:
            dm.new_thermostat(session, name, dm.ThermoDisplay(display.lower()))
        case ["MODIFY", "THERMOSTAT", name, "WITH", "DISPLAY", "IN", ("C" | "F") as display]:
            dm.update_thermostat(session, name, dm.ThermoDisplay(display.lower()))
        case ["SET", "THERMOSTAT", name, "TO", ("OFF" | "HEAT" | "COOL" | "HEATCOOL") as mode]:
            dm.set_thermo_mode(session, name, dm.ThermoMode(mode.lower()))
        case ["SET", "THERMOSTAT", name, "TARGET", "TO", low, "TO", high]:
            mn, mx = int(low), int(high)
            dm.set_thermo_set_points(session, name, mn, mx)
        case ["SET", "THERMOSTAT", name, "CURRENT", "TO", current]:
            dm.set_thermo_current_temp(session, name, int(current))

        case ["RENAME", kind, old_name, "TO", new_name] if (cls := _kinds.get(kind)):
            dm.rename(session, cls, old_name, new_name)
        case ["DELETE", kind, name] if (cls := _kinds.get(kind)):
            dm.delete(session, cls, name)

        case ["SHOW", kind, name] if (cls := _all_kinds.get(kind)):
            output_file.write(f"--{kind} '{name}'--\n")
            show(select(cls).where(cls.name == name), session, output_file, depth=1)  # type: ignore
        case ["DETAIL", kind, name] if (cls := _all_kinds.get(kind)):
            output_file.write(f"--{kind} '{name}'--\n")
            show(select(cls).where(cls.name == name), session, output_file)  # type: ignore
        case [("DETAIL" | "LIST") as specificity, kind] if (cls := _plural_kinds.get(kind)):
            output_file.write(f"--All {kind}--\n")
            q = select(cls.name) if specificity == "LIST" else select(cls)  # type: ignore
            show(q, session, output_file)

        case _:
            raise errors.TrackerError("unknown command or bad syntax")


T = typing.TypeVar("T", bound=typing.Tuple[typing.Any, ...])


def show(q: Select[T], session: Session, output_file: typing.TextIO, depth: int = 2) -> None:
    """Pretty-print information selected items to `output_file`."""

    for d in session.scalars(q):
        pprint(d, stream=output_file, sort_dicts=False, width=100, depth=depth)
    output_file.write("\n")


if __name__ == "__main__":
    main(sys.stdin, sys.stdout)
