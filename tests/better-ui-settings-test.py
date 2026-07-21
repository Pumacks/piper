#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from piper.better_ui import BetterUiApplication  # noqa: E402
from piper.ratbagd import RatbagdLed, RatbagdResolution  # noqa: E402


class FakeResolution:
    CAP_DISABLE = RatbagdResolution.CAP_DISABLE

    def __init__(
        self, events, index, dpi, *, active=False, default=False, disabled=False
    ):
        self.events = events
        self.index = index
        self.resolution = (dpi,)
        self.resolutions = [400, 800, 1600, 3200]
        self.capabilities = [self.CAP_DISABLE]
        self.is_active = active
        self.is_default = default
        self.is_disabled = disabled

    def set_active(self):
        self.events.append((self.index, "active", True))
        self.is_active = True

    def set_disabled(self, disabled):
        self.events.append((self.index, "disabled", disabled))
        self.is_disabled = disabled


class FakeLed:
    def __init__(self, mode, color, brightness, duration):
        self.events = []
        self._mode = mode
        self._color = color
        self._brightness = brightness
        self._duration = duration

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self.events.append(("mode", value))
        self._mode = value

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self.events.append(("color", value))
        self._color = value

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        self.events.append(("brightness", value))
        self._brightness = value

    @property
    def effect_duration(self):
        return self._duration

    @effect_duration.setter
    def effect_duration(self, value):
        self.events.append(("duration", value))
        self._duration = value


class FakeProfile:
    def __init__(self, resolutions=None, leds=None):
        self.resolutions = resolutions or []
        self.leds = leds or []


class FakeSwitch:
    def __init__(self, active):
        self.active = active

    def get_active(self):
        return self.active


class FakeApplication:
    def __init__(self, draft):
        self._draft = draft
        self.apply_sensitive = False

    def _set_apply_sensitive(self, sensitive):
        self.apply_sensitive = sensitive


class BetterUiSettingsTest(unittest.TestCase):
    def test_disabling_stage_is_staged_until_apply(self):
        draft = {"resolution_disabled": [False, False]}
        app = FakeApplication(draft)

        BetterUiApplication._on_resolution_enabled_changed(
            app, FakeSwitch(False), None, 1
        )

        self.assertEqual(draft["resolution_disabled"], [False, True])
        self.assertTrue(app.apply_sensitive)

    def test_resolution_apply_protects_active_and_default_stages(self):
        events = []
        resolutions = [
            FakeResolution(events, 0, 800, active=True),
            FakeResolution(events, 1, 1600, default=True),
            FakeResolution(events, 2, 1600, disabled=True),
        ]
        profile = FakeProfile(resolutions=resolutions)
        draft = {
            "resolutions": [800, 1600, 3200],
            "resolution_disabled": [True, True, True],
            "active_resolution": 2,
        }

        BetterUiApplication._apply_resolution_draft(profile, draft)

        self.assertEqual(resolutions[2].resolution, (3200,))
        self.assertTrue(resolutions[0].is_disabled)
        self.assertFalse(resolutions[1].is_disabled)
        self.assertFalse(resolutions[2].is_disabled)
        self.assertEqual(
            events,
            [
                (2, "disabled", False),
                (2, "active", True),
                (0, "disabled", True),
            ],
        )

    def test_off_effect_only_writes_mode(self):
        led = FakeLed(RatbagdLed.Mode.ON, (1, 2, 3), 50, 1000)
        profile = FakeProfile(leds=[led])
        draft = {
            "leds": [
                {
                    "mode": RatbagdLed.Mode.OFF,
                    "color": (4, 5, 6),
                    "brightness": 100,
                    "effect_duration": 2000,
                }
            ]
        }

        BetterUiApplication._apply_led_draft(profile, draft)

        self.assertEqual(led.events, [("mode", RatbagdLed.Mode.OFF)])

    def test_cycle_effect_does_not_write_irrelevant_color(self):
        led = FakeLed(RatbagdLed.Mode.CYCLE, (1, 2, 3), 50, 1000)
        profile = FakeProfile(leds=[led])
        draft = {
            "leds": [
                {
                    "mode": RatbagdLed.Mode.CYCLE,
                    "color": (4, 5, 6),
                    "brightness": 100,
                    "effect_duration": 2000,
                }
            ]
        }

        BetterUiApplication._apply_led_draft(profile, draft)

        self.assertEqual(
            led.events, [("brightness", 100), ("duration", 2000)]
        )


if __name__ == "__main__":
    unittest.main()
