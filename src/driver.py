"""
This driver script shows an example of using this project. 

When run as a script (`python driver.py`), it executes the `main` function below,
which reads from `stdin` and writes output to `stdout` and logs to `stderr`.
It processes each line as a command according to a simple DSL,
wherein each valid command will call to one of the library functions.
Lines with invalid syntax or that otherwise result in errors log their error message. 

See the README for more details on the DSL, or have a look at the `process_command` function.
"""

import logging
import sys
import typing
from pprint import pprint

from tracker import datamodel as dm
from tracker import datastore as ds
from tracker import errors

logging.basicConfig()
logger = logging.getLogger("driver")


def main(command_file: typing.TextIO, output_file: typing.TextIO) -> None:
    """Reads commands from `command_file` and processes them, writing to `output_file` as needed.

    This is called by default when this script is executed without arguments.
    In that case, `command_file` is `sys.stdin` and `output_file` is `sys.stdout`.
    """

    store = ds.DataStore()
    with store.begin() as session: 
        for line_num, line in enumerate(map(lambda line: line.strip(), command_file)):
            process_one(session, line_num, line, output_file)


def process_one(session: ds.DataSession, line_num: int, line: str, output_file: typing.TextIO) -> None:
    """Process a single line. This is split out to reduce nesting."""
    with session.begin() as transaction:
        try:
            process_command(transaction, line, output_file)
        except (errors.TrackerError, ValueError) as err:
            logger.error(f"Command on line {line_num} failed: {err}\n\t> {line}\n")


# These helpers associate command strings to item types.
_devices: dict[str, type[dm.Device]] = {
    "SWITCH": dm.Switch,
    "DIMMER": dm.Dimmer,
    "LOCK": dm.Lock,
    "THERMOSTAT": dm.Thermostat,
}
_dev_or_place = typing.cast(dict[str, type[ds.PlaceOrDevice]], _devices | {"DWELLING": dm.Dwelling, "HUB": dm.Hub})
_all_kinds = _dev_or_place | {"DEVICE": dm.Device}
_plural_kinds = { f"{k}S": v for k, v in _all_kinds.items() if k != "SWITCH" } | { "SWITCHES": dm.Switch }


def process_command(dt: ds.DataTransaction, command: str, output_file: typing.TextIO) -> None:
    """Process a command, possibly writing text to the `output_file`."""

    match command.split():
        case ["#", *_] | []:  # Skip comments and empty lines.
            return

        case ["NEW", "DWELLING", name]:
            dt.new_dwelling(name)
        case ["SET", "DWELLING", name, "TO", ("OCCUPIED" | "VACANT") as state]:
            dt.set_dwelling_occupancy(name, dm.OccupancyState(state.lower()))

        case ["NEW", "HUB", name]:
            dt.new_hub(name)
        case ["INSTALL", hub_name, "INTO", dwelling_name]:
            dt.install_hub(hub_name, dwelling_name)
        case ["UNINSTALL", hub_name]:
            dt.uninstall_hub(hub_name)

        case ["PAIR", dev_kind, device_name, "WITH", hub_name] if (dcls := _devices.get(dev_kind)):
            dt.pair_device(dcls, device_name, hub_name) 
        case ["UNPAIR", dev_kind, device_name] if (dcls := _devices.get(dev_kind)):
            dt.unpair_device(dcls, device_name)

        case ["NEW", "SWITCH", name]:
            dt.new_switch(name)
        case ["SET", "SWITCH", name, "TO", ("ON" | "OFF") as state]:
            dt.set_switch_state(name, dm.SwitchState(state.lower()))

        case ["NEW", "DIMMER", name, "RANGE", low, "TO", high, "WITH", "FACTOR", factor]:
            dt.new_dimmer(name, int(low), int(high), int(factor))
        case ["MODIFY", "DIMMER", name, "RANGE", low, "TO", high, "WITH", "FACTOR", factor]:
            dt.update_dimmer(name, int(low), int(high), int(factor))
        case ["SET", "DIMMER", name, "TO", value]:
            dt.set_dimmer_value(name, int(value))

        case ["NEW", "LOCK", name, "WITH", "PIN", pin]:
            dt.new_lock(name, pin)
        case ["MODIFY", "LOCK", name, "ADD", "PIN", pin]:
            dt.add_lock_pin(name, pin)
        case ["MODIFY", "LOCK", name, "REMOVE", "PIN", pin]:
            dt.remove_lock_pin(name, pin)
        case ["SET", "LOCK", name, "TO", "LOCKED"]:
            dt.lock_door(name)
        case ["SET", "LOCK", name, "TO", "UNLOCKED", "USING", pin]:
            dt.unlock_door(name, pin)

        case ["NEW", "THERMOSTAT", name, "WITH", "DISPLAY", "IN", ("C" | "F") as display]:
            dt.new_thermostat(name, dm.ThermoDisplay(display.lower()))
        case ["MODIFY", "THERMOSTAT", name, "WITH", "DISPLAY", "IN", ("C" | "F") as display]:
            dt.update_thermostat(name, dm.ThermoDisplay(display.lower()))
        case ["SET", "THERMOSTAT", name, "TO", ("OFF" | "HEAT" | "COOL" | "HEATCOOL") as mode]:
            dt.set_thermo_mode(name, dm.ThermoMode(mode.lower()))
        case ["SET", "THERMOSTAT", name, "TARGET", "TO", low, "TO", high]:
            dt.set_thermo_set_points(name, int(low), int(high))
        case ["SET", "THERMOSTAT", name, "CURRENT", "TO", current]:
            dt.set_thermo_current_temp(name, int(current))
        
        case ["RENAME", kind, old_name, "TO", new_name] if (devp := _dev_or_place.get(kind)):
            dt.rename(devp, old_name, new_name)
        case ["DELETE", kind, name] if (devp := _dev_or_place.get(kind)):
            dt.delete(devp, name)

        case ["SHOW", kind, name] if (cls := _all_kinds.get(kind)):
            output_file.write(f"--{kind} '{name}'--\n")
            show([dt.get_by_name(cls, name, "detail")], output_file, depth=1)
        case ["DETAIL", kind, name] if (cls := _all_kinds.get(kind)):
            output_file.write(f"--{kind} '{name}'--\n")
            show([dt.get_by_name(cls, name, "detail")], output_file)
        case ["DETAIL", kind] if (cls := _plural_kinds.get(kind)):
            output_file.write(f"--All {kind}--\n")
            show(dt.get_all(cls), output_file)
        case ["LIST", kind] if (cls := _plural_kinds.get(kind)):
            output_file.write(f"--All {kind}--\n")
            show(dt.get_all_names(cls), output_file)

        case _:
            raise errors.TrackerError("unknown command or bad syntax")


def show(items: typing.Iterable[typing.Any], output_file: typing.TextIO, depth: int = 2) -> None:
    """Pretty-print information selected items to `output_file`."""

    for d in items:
        pprint(d, stream=output_file, sort_dicts=False, width=100, depth=depth)
    output_file.write("\n")


if __name__ == "__main__":
    main(sys.stdin, sys.stdout)
