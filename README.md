
# Tracking System Prototype

The code in this repository implements a basic IoT tracking system.

## Quick Start

If you have `git`, `docker`, and `make` installed,
this short script shows how to get started quickly:

```shell
git clone https://github.com/saites/tracking-prototype.git tracking-prototype
cd tracking-prototype

# Create image and run tests.
make docker-test

# Pipe in example files.
make docker-examples

# Run interactive; type commands, then use Ctrl+D when done, e.g.:
make docker-interactive
NEW DWELLING my_dwelling
SET DWELLING my_dwelling TO OCCUPIED
NEW HUB my_hub
INSTALL my_hub INTO my_dwelling
NEW SWITCH sw1
PAIR SWITCH sw1 WITH my_hub
SET SWITCH sw1 TO ON
DETAIL DWELLINGS
# Ctrl+D
```

### Running Directly with Python

You'll need `python` 3.11 installed.
First, create and activate a `virtualenv` (optional, but recommended),
then install the project with `make setup` or `pip install -e .[test,dev]`.

```shell
python -m venv .venv
source .venv/bin/activate
make setup
```

Now you can pipe in the example commands or run the driver script:

```shell
make examples
# --or--
python src/driver.py < examples/example-commands.txt
python src/driver.py < examples/invalid-commands.txt

# Run interactively; type commands, then use Ctrl+D when done.
python src/driver.py
```

#### Development Targets

- `make test` runs the unit tests via `pytest`.
- `make type-check` runs `mypy src`.
- `make format` runs `isort` and `black` to format the project.

## Usage

The [driver script](src/driver.py) shows example usage of the project.
It processes commands from `stdin` according to the simple syntax below,
and each valid command calls into the project's library functions.

You can use the driver script interactively,
ending the session with `Ctrl+D` when done,
or you can redirect input from a file,
such as the example files included in the [examples directory](examples/).

### Driver Command Syntax

Lines are executed in order, and lines starting with '#' are ignored.
Words/arguments are whitespace delimited and consecutive spaces are ignored.
Lines that result in errors logs messages to `stderr`,
but the script will continue to process the lines that follow.

- General syntax:
  - A `{PLACE}` is either `DWELLING` or `HUB`.
  - A `{DEVICE}` is one of `SWITCH`, `DIMMER`, `LOCK`, or `THERMOSTAT`.
  - An `{ITEM}` is one of the `{PLACE}`s or `{DEVICE}`s
    or the literal word `DEVICE` to match all devices.
- Create/delete items (see below for device-specific properties)
  - `NEW {PLACE} place_name`
  - `NEW {DEVICE} device_name [PROPS]`
  - `DELETE { PLACE | DEVICE } item_name`
- Associate items together
  - `INSTALL hub_name INTO dwelling_name`
  - `PAIR {DEVICE} device_name WITH hub_name`
- Change properties and device states:
  - `RENAME { PLACE | DEVICE } current_name new_name`
  - `SET DWELLING dwelling_name { OCCUPIED | VACANT }`
  - `SET {DEVICE} device_name [STATE]`
  - `MODIFY {DEVICE} device_name [PROPS]`
- Show information about items:
  - `SHOW {ITEM} item_name`
  - `LIST {ITEM}S`
  - `DETAIL {ITEM}S`
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
  - `SET LOCK name TO LOCKED`
  - `SET LOCK name TO UNLOCKED USING pin_code`
- Thermostats have operating states, a display format (C or F),
  and low/high set-points (always integers in 1/100th of a degree Celsius):
  - `NEW THERMOSTAT name WITH DISPLAY IN { C | F }`
  - `MODIFY THERMOSTAT name WITH DISPLAY IN { C | F }`
  - `SET THERMOSTAT name TEMPERATURE TO low_temp TO high_temp`
  - `SET THERMOSTAT name TO {OFF | HEAT | COOL | HEATCOOL}`

## Design Considerations

The code is organized into the following modules:

- `datamodel.py` defines the types, data classes, relationships, and constraints
  used throughout the codebase.
- `datastore.py` provides transactional helper functions
  to interact with the data modeled above.
- `errors.py` provides a simple `Exception` hierarchy

The project description lends itself well to a relational database design,
and since an in-memory solution was desired, I chose `SQLite` as a backbone;
it is fast, included with (typical) Python distributions,
and capable of maintaining the necessary constraints and relational integrity.
Using `SQLAlchemy`, I was able to describe these relationships declaratively
while mapping them to corresponding Python objects.
The code includes relevant comments, but here's the gist of `datamodel.py`:

- `Dwelling`s have basic state information
  and attributes to access "installed" `Hub`s
  and those `Hub`'s `Device`s.
- `Hub`s and `Device`s have a common set of `Hardware` properties,
  such as hardware and firmware version numbers
  and when the state was last updated.
- `Hub`s include attributes to access its associated `Dwelling` and `Device`s.
- `Device`s are represented in the Python code via a thin class hierarchy
  and in the database using joined table inheritance.
  This enables code like `isinstance(Device, some_switch)` to do the right thing,
  while ensuring new device classes won't require major database changes,
  nor requiring a single table to have many columns full of `NULL` values.
  - The base `Device` class includes a mapping back to its `Hub`,
    as well as the common `Hardware` properties described above.
    It also includes a discriminator column (`kind`) to map to specific `Device` classes.
  - `Switch`, `Dimmer`, etc. subclass the `Device` class
    and add their device-specific properties.
    These are mapped to device-type-specific tables
    wherein the primary key is itself a foreign key reference
    to the underlying `Device` instance.
  - The details of the Python-to-database mapping are implemented automatically,
    keeping the class definitions clean.
    A new device class can be added with a single new `enum` value
    and a class that derives from `Device`, e.g.:
    ```python
    class DeviceKind(Enum):
        # existing enums ...
        MyNewDevice = "mynewdevice"

    class MyNewDevice(Device):
        some_state: Mapped[int]
    ```

As I imagine the expected use-case to be some form of
"process incoming messages by updating the data backend and dispatching to devices",
I designed my library functions to accept a `session` object spanning a single transaction.
As such, operations typically require a "key" made of the target class and its name
(e.g., you pair a switch by passing the class `Switch`
and the names of the target switch and hub).
Internally, the library uses the session to find the appropriate targets
and modify their states, potentially linking objects together if necessary.

Contrast this to methods declared directly on the class,
such as a hypothetical `Switch.change_state(new_state)` method.
While this is appealing to some extent, many methods have no such clear "owner"
(should it be `dwelling.install(hub)` or `hub.install_into(dwelling)`?).
Having these methods directly on the classes muddies the transactional boundaries,
as it encourages passing around references to implicitly unstable state,
with potential for more bugs down the line.

Moreover, the project description implies at some point this information
should be used to handle communication with devices via their native protocol.
If written as class methods, it would likely lead to deep class hierarchies
with high potential for conflicting or confusing method signatures.
With my approach, library functions would use protocol information
associated the device level to dispatch commands to an appropriate protocol handler.
These commands could be enqueued and processed by another service,
more easily allowing separate development and compute resourcing if necessary.

All this said, I wrapped the `SQLAlchemy` `Session` with a class of its own
in order to hide its implementation details from the `driver.py` script.
Note that hiding the `Session` in this manner
also encourages leaking mapped objects, with the risk that calling code
would use them outside of their framed transactional context.
This is, however, somewhat unlikely in practice:
as with the `driver.py` code, the most likely use-case
is to start a new transaction on each incoming command to be processed,
and execute its operations within the transaction context.
In that case, the primary risk comes from catching exceptions within the context,
as in some cases, doing so may require an explicit `rollback` or `commit`,
which is currently abstracted by the `contextmanager` itself.
In practice, though, the most likely place to run into this is unit tests,
and typically when intentionally triggering an error.

### Future Work

As this is only a PoC, the current version of the code leaves out several things:

- The `updated_at` timestamp is not actually updated when modifying state.
- Though there are places for hardware and firmware details,
  there isn't explicit library code to modify them.
- When setting a `Device`'s state,
  real code would use the `Device`'s hardware and firmware information
  to determine the appropriate protocol to use to communicate with the device.
  Likely, the `Device` table would need to add other properties for this purpose.
  The current code simply updates its own view of the property.
- Related to the above, `Device` updates should probably be enqueued
  and reattempted on failure,
  in which case the backend would store a `target_state`
  alongside a `last_known_state`, likely with timestamps associated with both.
- The PINs used to unlock a `Lock` should probably be associated with some sort of user account.
- This codebase only includes a small number of tests to verify functionality.
