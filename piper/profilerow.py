# SPDX-License-Identifier: GPL-2.0-or-later

import sys
from typing import Optional

import json
from pathlib import Path

import gi

from piper.ratbagd import RatbagdDevice, RatbagdProfile

from .util.gobject import connect_signal_with_weak_ref

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GObject, Gtk  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ProfileRow.ui")
class ProfileRow(Gtk.ListBoxRow):
    """A Gtk.ListBoxRow subclass containing the widgets to display a profile in
    the profile poper."""

    __gtype_name__ = "ProfileRow"

    title: Gtk.Label = Gtk.Template.Child()  # type: ignore

    def __init__(
        self,
        device: RatbagdDevice,
        profile: RatbagdProfile,
        *args,
        **kwargs,
    ) -> None:
        Gtk.ListBoxRow.__init__(self, *args, **kwargs)
        self._device = device
        self._profile = profile
        connect_signal_with_weak_ref(
            self, self._profile, "notify::disabled", self._on_profile_notify_disabled
        )

        name = self._load_profile_alias() or profile.name
        if not name:
            name = f"Profile {profile.index}"

        self.title.set_text(name)
        self.show_all()
        self.set_visible(not profile.disabled)

    def _on_profile_notify_disabled(
        self, profile: RatbagdProfile, pspec: Optional[GObject.ParamSpec]
    ) -> None:
        self.set_visible(not profile.disabled)

    @Gtk.Template.Callback("_on_delete_button_clicked")
    def _on_delete_button_clicked(self, button: Gtk.Button) -> None:
        if not self._profile.is_active:
            self._profile.disabled = True
        else:
            # TODO: display this in the app
            print("Trying to disable the active profile", file=sys.stderr)

    @Gtk.Template.Callback("_on_rename_button_clicked")
    def _on_rename_button_clicked(self, button: Gtk.Button) -> None:
        dialog = Gtk.Dialog(
            title="Rename Profile", transient_for=self.get_toplevel(), flags=0
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,
            Gtk.ResponseType.OK,
        )

        entry = Gtk.Entry()
        entry.set_text(self.title.get_text())

        box = dialog.get_content_area()
        box.add(entry)
        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_name = entry.get_text().strip()
            if new_name:
                self.set_name(new_name)

        dialog.destroy()

    def set_active(self) -> None:
        """Activates the profile paired with this row."""
        self._profile.set_active()

    def set_name(self, name: str) -> None:
        """Persist and display a local name for the onboard profile."""
        name = name.strip()
        if not name:
            return
        self._save_profile_alias(name)
        self.title.set_text(name)
        self.notify("name")

    @GObject.Property
    def name(self) -> str:
        return self.title.get_text()

    @GObject.Property
    def profile(self) -> RatbagdProfile:
        return self._profile

    def _profile_aliases_path(self) -> Path:
        return Path(GLib.get_user_config_dir()) / "piper" / "profile_names.json"

    def _profile_alias_key(self) -> str:
        device_name = getattr(self._device, "name", "unknown-device")
        return f"{device_name}:{self._profile.index}"

    def _load_profile_aliases(self) -> dict:
        path = self._profile_aliases_path()
        if not path.exists():
            return {}

        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_profile_alias(self, name: str) -> None:
        path = self._profile_aliases_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        aliases = self._load_profile_aliases()
        aliases[self._profile_alias_key()] = name

        with path.open("w", encoding="utf-8") as f:
            json.dump(aliases, f, indent=2, sort_keys=True)

    def _load_profile_alias(self) -> Optional[str]:
        aliases = self._load_profile_aliases()
        value = aliases.get(self._profile_alias_key())

        if isinstance(value, str) and value.strip():
            return value

        return None
