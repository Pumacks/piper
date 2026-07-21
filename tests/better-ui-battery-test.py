#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from piper.better_ui import BetterUiApplication  # noqa: E402


class FakeVariant:
    def __init__(self, value):
        self.value = value

    def unpack(self):
        return self.value


class FakeProxy:
    def __init__(self, **properties):
        self.properties = properties

    def get_cached_property(self, name):
        value = self.properties.get(name)
        return None if value is None else FakeVariant(value)


class BetterUiBatteryTest(unittest.TestCase):
    def test_snapshot_uses_upower_percentage_icon_and_state(self):
        proxy = FakeProxy(
            Percentage=35.0,
            IconName="battery-good-symbolic",
            State=2,
        )

        icon, label, tooltip = BetterUiApplication._battery_snapshot(proxy)

        self.assertEqual(icon, "battery-good-symbolic")
        self.assertEqual(label, "35%")
        self.assertEqual(tooltip, "Battery: 35% (discharging)")

    def test_snapshot_clamps_invalid_percentage(self):
        proxy = FakeProxy(Percentage=125.0)

        _icon, label, _tooltip = BetterUiApplication._battery_snapshot(proxy)

        self.assertEqual(label, "100%")

    def test_snapshot_handles_unavailable_battery(self):
        icon, label, tooltip = BetterUiApplication._battery_snapshot(None)

        self.assertEqual(icon, "battery-missing-symbolic")
        self.assertEqual(label, "Unknown")
        self.assertEqual(tooltip, "Battery level unavailable")


if __name__ == "__main__":
    unittest.main()
