# SPDX-License-Identifier: GPL-2.0-or-later

import sys
from typing import Optional

import gi

from piper.ratbagd import RatbagdProfile

from .util.gobject import connect_signal_with_weak_ref

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa


@Gtk.Template(resource_path="/org/freedesktop/Piper/ui/ProfileRow.ui")
class ProfileRow(Gtk.ListBoxRow):
    """A Gtk.ListBoxRow subclass containing the widgets to display a profile in
    the profile poper."""

    __gtype_name__ = "ProfileRow"

    title: Gtk.Label = Gtk.Template.Child()  # type: ignore

    def __init__(self, profile: RatbagdProfile, *args, **kwargs) -> None:
        Gtk.ListBoxRow.__init__(self, *args, **kwargs)
        self._profile = profile
        connect_signal_with_weak_ref(
            self, self._profile, "notify::disabled", self._on_profile_notify_disabled
        )

        name = profile.name
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
     		title="rename Profile",
       		transient_for=self.get_toplevel(),
         	flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           Gtk.STOCK_OK, Gtk.ResponseType.OK)

        entry = Gtk.Entry()
        entry.set_text(self.title.get_text())

        box = dialog.get_content_area()
        box.add(entry)
        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_name = entry.get_text()
            self.title.set_text(new_name)
        dialog.destroy()


    def set_active(self) -> None:
        """Activates the profile paired with this row."""
        self._profile.set_active()

    @GObject.Property
    def name(self) -> str:
        return self.title.get_text()

    @GObject.Property
    def profile(self) -> RatbagdProfile:
        return self._profile
