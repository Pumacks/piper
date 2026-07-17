# SPDX-License-Identifier: GPL-2.0-or-later

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa


class VirtualProfileRow(Gtk.ListBoxRow):
    """A local virtual profile that can be loaded or deleted."""

    __gtype_name__ = "VirtualProfileRow"

    __gsignals__ = {
        "delete-requested": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_PYOBJECT,),
        )
    }

    def __init__(self, virtual_profile: dict) -> None:
        super().__init__()
        self.virtual_profile = virtual_profile

        box = Gtk.Box(spacing=6, margin_start=6, margin_end=6)
        label = Gtk.Label(
            label=virtual_profile["name"],
            xalign=0,
            hexpand=True,
            margin_top=6,
            margin_bottom=6,
        )
        delete_button = Gtk.Button.new_from_icon_name(
            "edit-delete-symbolic", Gtk.IconSize.MENU
        )
        delete_button.set_relief(Gtk.ReliefStyle.NONE)
        delete_button.set_tooltip_text("Delete this virtual profile")
        delete_button.connect("clicked", self._on_delete_clicked)
        box.pack_start(label, True, True, 0)
        box.pack_end(delete_button, False, False, 0)
        self.add(box)
        self.show_all()

    def _on_delete_clicked(self, _button: Gtk.Button) -> None:
        self.emit("delete-requested", self.virtual_profile)
