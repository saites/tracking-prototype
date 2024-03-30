"""
These are a collection of pretty basic tests,
meant really only to demonstrate
    1. the datastore code indeed persists values between transactions, and
    2. the code doesn't crash when executing these basic operations. 

A real test suite would include better properties-based testing and fuzzing.
"""

import random
import string

import pytest

from tracker import datamodel as dm
from tracker import errors
from tracker.datastore import DataSession


@pytest.fixture
def rng() -> random.Random:
    return random.Random(0x62590)


class NameGen:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def __call__(self, min_len: int = 5, max_len: int = 20, charset: str | None = None) -> str:
        if not charset:
            charset = string.digits + string.ascii_letters
        return "".join(self.rng.choices(charset, k=self.rng.randint(min_len, max_len)))


@pytest.fixture
def name_gen(rng: random.Random) -> NameGen:
    return NameGen(rng)


class TestDatastore:
    def test_dwelling(self, session: DataSession, name_gen: NameGen) -> None:
        name = name_gen()

        with session.transaction() as t:
            result = t.new_dwelling(name)

        with session.transaction() as t:
            assert t.get_by_name(dm.Dwelling, name) == result

        with session.transaction() as t:
            t.delete(dm.Dwelling, name)

        with session.transaction() as t:
            with pytest.raises(errors.NoResultError):
                t.get_by_name(dm.Dwelling, name)

    def test_hub(self, session: DataSession, name_gen: NameGen) -> None:
        name = name_gen()

        with session.transaction() as t:
            result = t.new_hub(name)

        with session.transaction() as t:
            assert t.get_by_name(dm.Hub, name) == result

        with session.transaction() as t:
            t.delete(dm.Hub, name)

        with session.transaction() as t:
            with pytest.raises(errors.NoResultError):
                t.get_by_name(dm.Hub, name)

    def test_switch(self, session: DataSession, name_gen: NameGen) -> None:
        name = name_gen()

        with session.transaction() as t:
            result = t.new_switch(name)

        with session.transaction() as t:
            assert t.get_by_name(dm.Switch, name) == result

        with session.transaction() as t:
            t.delete(dm.Switch, name)

        with session.transaction() as t:
            with pytest.raises(errors.NoResultError):
                t.get_by_name(dm.Switch, name)

    def test_dimmer(self, session: DataSession, name_gen: NameGen) -> None:
        name = name_gen()

        with session.transaction() as t:
            result = t.new_dimmer(name, 0, 100, 1)

        with session.transaction() as t:
            assert t.get_by_name(dm.Dimmer, name) == result

        with session.transaction() as t:
            t.delete(dm.Dimmer, name)

        with session.transaction() as t:
            with pytest.raises(errors.NoResultError):
                t.get_by_name(dm.Dimmer, name)

    def test_lock(self, session: DataSession, name_gen: NameGen) -> None:
        name = name_gen()

        with session.transaction() as t:
            result = t.new_lock(name, "12345")

        with session.transaction() as t:
            assert t.get_by_name(dm.Lock, name) == result

        with session.transaction() as t:
            t.delete(dm.Lock, name)

        with session.transaction() as t:
            with pytest.raises(errors.NoResultError):
                t.get_by_name(dm.Lock, name)

    def test_thermostat(self, session: DataSession, name_gen: NameGen) -> None:
        name = name_gen()

        with session.transaction() as t:
            result = t.new_thermostat(name, dm.ThermoDisplay.Celsius)

        with session.transaction() as t:
            assert t.get_by_name(dm.Thermostat, name) == result

        with session.transaction() as t:
            t.delete(dm.Thermostat, name)

        with session.transaction() as t:
            with pytest.raises(errors.NoResultError):
                t.get_by_name(dm.Thermostat, name)

    def test_same_names(self, session: DataSession, name_gen: NameGen) -> None:
        name = name_gen()

        with session.transaction() as t:
            switch = t.new_switch(name)
            dimmer = t.new_dimmer(name, 0, 100, 1)
            lock = t.new_lock(name, "1234")
            therm = t.new_thermostat(name, dm.ThermoDisplay.Celsius)

        with session.transaction() as t:
            assert t.get_by_name(dm.Switch, name) == switch
            assert t.get_by_name(dm.Dimmer, name) == dimmer
            assert t.get_by_name(dm.Lock, name) == lock
            assert t.get_by_name(dm.Thermostat, name) == therm

    def test_associations(self, session: DataSession, name_gen: NameGen) -> None:
        dwelling_name = name_gen()
        hub_name = name_gen()
        switch_name = name_gen()

        with session.transaction() as t:
            t.new_dwelling(dwelling_name)
            t.new_hub(hub_name)
            t.new_switch(switch_name)
            t.install_hub(hub_name, dwelling_name)
            t.pair_device(dm.Switch, switch_name, hub_name)

        with session.transaction() as t:
            dwelling = t.get_by_name(dm.Dwelling, dwelling_name)
            hub = t.get_by_name(dm.Hub, hub_name)
            switch = t.get_by_name(dm.Switch, switch_name)
            assert list(hub.devices) == [switch]
            assert list(dwelling.hubs) == [hub]

            with pytest.raises(errors.HasDependenciesError):
                t.delete(dm.Dwelling, dwelling_name)
            with pytest.raises(errors.PairedError):
                t.delete(dm.Hub, hub_name)

            t.uninstall_hub(hub_name)
            t.delete(dm.Dwelling, dwelling_name)

            with pytest.raises(errors.HasDependenciesError):
                t.delete(dm.Hub, hub_name)
            with pytest.raises(errors.PairedError):
                t.delete(dm.Switch, switch_name)

            t.unpair_device(dm.Switch, switch_name)
            t.delete(dm.Switch, switch_name)
            t.delete(dm.Hub, hub_name)

            assert list(t.get_all(dm.Dwelling)) == []


class TestDwelling:
    @pytest.fixture
    def dwelling(self, session: DataSession, name_gen: NameGen) -> dm.Dwelling:
        with session.transaction() as t:
            dwelling = t.new_dwelling(name_gen())
        return dwelling

    @pytest.mark.parametrize("state", list(dm.OccupancyState))
    def test_set_state(
        self, session: DataSession, dwelling: dm.Dwelling, state: dm.OccupancyState
    ) -> None:

        with session.transaction() as t:
            name = dwelling.name
            t.set_dwelling_occupancy(name, state)

        with session.transaction() as t:
            dwelling = t.get_by_name(dm.Dwelling, name)
            assert dwelling.occupancy is state

    def test_duplicates(self, session: DataSession, dwelling: dm.Dwelling) -> None:
        with pytest.raises(errors.TrackerError):
            with session.transaction() as t:
                t.new_dwelling(dwelling.name)


class TestSwitch:
    @pytest.fixture
    def switch(self, session: DataSession, name_gen: NameGen) -> dm.Switch:
        with session.transaction() as t:
            return t.new_switch(name_gen())

    @pytest.mark.parametrize("state", list(dm.SwitchState))
    def test_set_state(
        self, session: DataSession, switch: dm.Switch, state: dm.SwitchState
    ) -> None:
        with session.transaction() as t:
            t.set_switch_state(switch.name, state)

        with session.transaction() as t:
            s = t.get_by_name(dm.Switch, switch.name)
            assert s.state is state


class TestDimmer:
    minv = 0
    maxv = 100
    scale = 1

    @pytest.fixture
    def dimmer(self, session: DataSession, name_gen: NameGen) -> dm.Dimmer:
        with session.transaction() as t:
            return t.new_dimmer(name_gen(), TestDimmer.minv, TestDimmer.maxv, TestDimmer.scale)

    @pytest.mark.parametrize(
        ("mn", "mx", "s"),
        [(-10, 10, 10), (100, 101, 36), (10, 201, 13), (1, 1, 1), (-1, -1, -1)],
    )
    def test_update_ok(
        self, session: DataSession, dimmer: dm.Dimmer, mn: int, mx: int, s: int
    ) -> None:

        with session.transaction() as t:
            t.update_dimmer(dimmer.name, mn, mx, s)

        with session.transaction() as t:
            d = t.get_by_name(dm.Dimmer, dimmer.name)
            assert d.min_value == mn
            assert d.max_value == mx
            assert d.scale == s

    @pytest.mark.parametrize(
        ("mn", "mx", "s"),
        [
            (1, 100, 0),
            (10, -10, 10),
            (101, 100, 36),
            (201, -201, 13),
        ],
    )
    def test_update_bad(
        self, session: DataSession, dimmer: dm.Dimmer, mn: int, mx: int, s: int
    ) -> None:

        with pytest.raises(errors.TrackerError):
            with session.transaction() as t:
                t.update_dimmer(dimmer.name, mn, mx, s)

    @pytest.mark.parametrize("value", range(minv, maxv))
    def test_set_value(self, session: DataSession, dimmer: dm.Dimmer, value: int) -> None:
        with session.transaction() as t:
            t.set_dimmer_value(dimmer.name, value)

        with session.transaction() as t:
            d = t.get_by_name(dm.Dimmer, dimmer.name)
            assert d.value == value

    @pytest.mark.parametrize("value", [-10, -1, 101, 500])
    def test_invalid(self, session: DataSession, dimmer: dm.Dimmer, value: int) -> None:
        with pytest.raises(errors.TrackerError):
            with session.transaction() as t:
                t.set_dimmer_value(dimmer.name, value)


class TestLock:
    pin = "12345"

    @pytest.fixture
    def lock(self, session: DataSession, name_gen: NameGen) -> dm.Lock:
        with session.transaction() as t:
            return t.new_lock(name_gen(), TestLock.pin)

    @pytest.mark.parametrize("pin", ["1234", "0123", "0000", "0" * 100])
    def test_bad_pin(self, session: DataSession, lock: dm.Lock, pin: str) -> None:
        with session.transaction() as t:
            t.lock_door(lock.name)

        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Locked
            with pytest.raises(errors.InvalidPinError):
                t.unlock_door(lock.name, pin)

        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Locked

    @pytest.mark.parametrize("pin", ["", "012", "asdf"])
    def test_add_bad(self, session: DataSession, lock: dm.Lock, pin: str) -> None:
        with pytest.raises(errors.TrackerError):
            with session.transaction() as t:
                t.add_lock_pin(lock.name, pin)

    @pytest.mark.parametrize("pin", ["1234", "0123", "0000", "0" * 100])
    def test_add_remove(self, session: DataSession, lock: dm.Lock, pin: str) -> None:
        with session.transaction() as t:
            t.add_lock_pin(lock.name, pin)
            t.lock_door(lock.name)

        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Locked
            t.unlock_door(lock.name, pin)

        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Unlocked
            t.lock_door(lock.name)

        # The original pin still works.
        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Locked
            t.unlock_door(lock.name, TestLock.pin)

        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Unlocked

        # Remove the added pin and verify we can't use it any longer.
        with session.transaction() as t:
            t.remove_lock_pin(lock.name, pin)
            t.lock_door(lock.name)
            assert lock.state is dm.LockState.Locked

        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Locked
            with pytest.raises(errors.InvalidPinError):
                t.unlock_door(lock.name, pin)

        # But the original pin still works even still.
        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Locked
            t.unlock_door(lock.name, TestLock.pin)

        with session.transaction() as t:
            l = t.get_by_name(dm.Lock, lock.name)
            assert l.state is dm.LockState.Unlocked


class TestThermostat:
    @pytest.fixture
    def therm(self, session: DataSession, name_gen: NameGen) -> dm.Thermostat:
        with session.transaction() as t:
            return t.new_thermostat(name_gen(), dm.ThermoDisplay.Celsius)

    @pytest.mark.parametrize("mode", list(dm.ThermoMode))
    def test_change_mode(
        self, session: DataSession, therm: dm.Thermostat, mode: dm.ThermoMode
    ) -> None:
        with session.transaction() as t:
            t.set_thermo_mode(therm.name, mode)

        with session.transaction() as t:
            th = t.get_by_name(dm.Thermostat, therm.name)
            assert th.mode is mode

    @pytest.mark.parametrize("display", list(dm.ThermoDisplay))
    def test_change_display(
        self, session: DataSession, therm: dm.Thermostat, display: dm.ThermoDisplay
    ) -> None:
        with session.transaction() as t:
            t.update_thermostat(therm.name, display)

        with session.transaction() as t:
            th = t.get_by_name(dm.Thermostat, therm.name)
            assert th.display is display

    @pytest.mark.parametrize(
        ("low", "high"),
        [
            (0, 100),
            (-10, 10),
            (15, 20),
        ],
    )
    def test_set(
        self, session: DataSession, therm: dm.Thermostat, low: int, high: int
    ) -> None:

        with session.transaction() as t:
            t.set_thermo_set_points(therm.name, low, high)

        with session.transaction() as t:
            th = t.get_by_name(dm.Thermostat, therm.name)
            assert th.low_centi_c == low
            assert th.high_centi_c == high
