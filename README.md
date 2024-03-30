
# Tracking System Prototype

The code in this repository implements a basic IoT tracking system.

## Install Locally

If you have `git` and `python` 3.11+, you can easily start like this:

```shell
git clone $this_repo_url tracking-proto
cd tracking-proto
python -m venv .venv
source .venv/bin/activate
pip install .[dev]
python src/driver.py < examples/example-commands.txt
```

You can run the unit tests by moving into the `src` directory
and running `python -m pytest ../tests`,
or accomplish the same from the root directory using `make test`,
if you have `Make` installed.

## Basic Use

The driver script [src/driver.py][] shows an example of using this project.

When run as `python driver.py`, it reads from `stdin`
and writes output to `stdout` and logs to `stderr`.
It processes each line as a command according to the simple syntax below.
Each valid command will call to one of the library functions.
Lines with invalid syntax or that otherwise result in errors
will log an error message to `stderr`.

If a command generates an error (or the command is unknown),
the processing script will show an error with details of the issue,
but the script will continue to process the lines that follow.

You can use the driver script interactively,
ending the session with `Ctrl+D` when done,
or you can redirect input from a file,
such as the example files included in the [examples/][] directory.

### Syntax

Lines are executed in order, and lines starting with '#' are ignored.
Words/arguments are whitespace delimited and consecutive spaces are ignored.

The general syntax for commands are:

    {COMMAND} {TARGET KIND} {TARGET NAME} [ARGUMENTS]

A `{PLACE}` is either `DWELLING` or `HUB`.
A `{DEVICE}` is one of `SWITCH`, `DIMMER`, `LOCK`, or `THERMOSTAT`.
An `{ITEM}` is one of the `{PLACE}`s or `{DEVICE}`s
or the literal word `DEVICE` to match all devices.

- Create/delete items (see below for device-specific properties)
  - `NEW {PLACE} place_name`
  - `NEW {DEVICE} device_name [PROPS]`
  - `DELETE {PLACE | DEVICE} item_name`
- Associate items together
  - `INSTALL hub_name INTO building_name`
  - `PAIR {DEVICE} device_name WITH hub_name`
- Change properties and device states:
  - `RENAME {PLACE | DEVICE} current_name new_name`
  - `SET DWELLING dwelling_name { OCCUPIED | VACANT }`
  - `SET {DEVICE} device_name [STATE]`
  - `MODIFY {DEVICE} device_name [PROPS]`
- Show information about items:
  - `LIST {ITEM}S`
  - `DETAIL {ITEM}S`
  - `SHOW {ITEM} item_name`
- Switches have on/off states:
  - `NEW SWITCH name`
  - `SET SWITCH name TO {ON | OFF}`
- Dimmers have integer values in a range scaled by a factor:
  - `NEW DIMMER name RANGE low TO high WITH FACTOR factor`
  - `MODIFY DIMMER name RANGE low TO high WITH FACTOR factor`
  - `SET DIMMER name TO value`
- Locks have locked/unlocked states and associated PINs of 4 or more digits:
  - `NEW LOCK name WITH PIN pin_code`
  - `MODIFY LOCK name ADD PIN pin_code`
  - `MODIFY LOCK name REMOVE PIN pin_code`
  - `SET LOCK name TO LOCKED `
  - `SET LOCK name TO UNLOCKED USING pin_code`
- Thermostats have operating states, a display format (C or F),
  and low/high set-points (always integers in 1/100th of a degree Celsius):
  - `NEW THERMOSTAT name WITH DISPLAY IN { C | F }`
  - `MODIFY THERMOSTAT name WITH DISPLAY IN { C | F }`
  - `SET THERMOSTAT name TEMPERATURE TO low_temp TO high_temp`
  - `SET THERMOSTAT name TO {OFF | HEAT | COOL | HEATCOOL}`

