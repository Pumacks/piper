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
            State=2,
        )

        icon, label, tooltip = BetterUiApplication._battery_snapshot(proxy)

        self.assertEqual(icon, "battery-level-30-symbolic")
        self.assertEqual(label, "35%")
        self.assertEqual(tooltip, "Battery: 35% (discharging)")

    def test_snapshot_uses_filled_charging_icon(self):
        proxy = FakeProxy(Percentage=95.0, State=1)

        icon, label, tooltip = BetterUiApplication._battery_snapshot(proxy)

        self.assertEqual(icon, "battery-level-90-charging-symbolic")
        self.assertEqual(label, "95%")
        self.assertEqual(tooltip, "Battery: 95% (charging)")

    def test_snapshot_clamps_invalid_percentage(self):
        proxy = FakeProxy(Percentage=125.0)

        _icon, label, _tooltip = BetterUiApplication._battery_snapshot(proxy)

        self.assertEqual(label, "100%")

    def test_snapshot_handles_unavailable_battery(self):
        icon, label, tooltip = BetterUiApplication._battery_snapshot(None)

        self.assertEqual(icon, "battery-missing-symbolic")
        self.assertEqual(label, "Unknown")
        self.assertEqual(tooltip, "Battery level unavailable")

    def test_device_name_matching_handles_upower_variants(self):
        self.assertTrue(
            BetterUiApplication._device_names_match(
                "G502 LIGHTSPEED Wireless Gaming Mouse",
                "Logitech G502 LIGHTSPEED Wireless Gaming Mouse",
            )
        )
        self.assertTrue(
            BetterUiApplication._device_names_match(
                "G502 LIGHTSPEED Wireless Gaming Mouse", "Logitech G502"
            )
        )
        self.assertFalse(
            BetterUiApplication._device_names_match("Logitech G502", "Logitech G604")
        )


if __name__ == "__main__":
    unittest.main()
