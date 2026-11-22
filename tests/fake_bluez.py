#!/usr/bin/env python3
"""A stand-in for bluetoothd, for testing keybond.py without hardware.

Owns org.bluez on whatever bus DBUS_SYSTEM_BUS_ADDRESS points at (use a private
bus from dbus-run-session, never the real system bus) and plays one scenario,
named by FAKE_SCENARIO. Final state is written as JSON to FAKE_STATE.
"""
import json
import os
import sys

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

OM = "org.freedesktop.DBus.ObjectManager"
PROPS = "org.freedesktop.DBus.Properties"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
AGENT = "org.bluez.Agent1"
HCI = "/org/bluez/hci0"

SCENARIO = os.environ.get("FAKE_SCENARIO", "passkey")
PRESET = os.environ.get("FAKE_PRESET", "").split(",")   # paired, untrusted, second
CONNECT = os.environ.get("FAKE_CONNECT", "ok")           # ok, silent, wakes, forgotten
STATE_PATH = os.environ.get("FAKE_STATE")


def error(name, message="fake"):
    exc = dbus.DBusException(message)
    exc._dbus_error_name = "org.bluez.Error." + name
    return exc


class World:
    def __init__(self, bus):
        self.bus = bus
        self.devices = {}
        self.agent = None          # (sender, path)
        self.removed = []
        self.pair_calls = 0
        self.agent_calls = []
        self.discovering = False

    def save(self):
        if STATE_PATH:
            data = {
                "devices": {p: {k: (bool(v) if isinstance(v, dbus.Boolean) else str(v))
                                for k, v in d.props.items()} for p, d in self.devices.items()},
                "removed": self.removed, "pair_calls": self.pair_calls,
                "agent_calls": self.agent_calls, "agent": bool(self.agent),
                "discovering": self.discovering,
            }
            with open(STATE_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh)

    def call_agent(self, method, signature, args, ok, err):
        self.agent_calls.append(method)
        self.save()
        sender, path = self.agent
        proxy = dbus.Interface(self.bus.get_object(sender, path), AGENT)
        getattr(proxy, method)(*args, signature=signature, reply_handler=ok, error_handler=err,
                               timeout=20)


class Root(dbus.service.Object):
    def __init__(self, world):
        super().__init__(world.bus, "/")
        self.world = world

    @dbus.service.method(OM, in_signature="", out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        objects = {dbus.ObjectPath(HCI): {ADAPTER: {"Powered": dbus.Boolean(True),
                                                    "Modalias": "usb:fake"}}}
        for path, dev in self.world.devices.items():
            objects[dbus.ObjectPath(path)] = {DEVICE: dev.props}
        return objects

    @dbus.service.signal(OM, signature="oa{sa{sv}}")
    def InterfacesAdded(self, path, ifaces):
        pass

    @dbus.service.signal(OM, signature="oas")
    def InterfacesRemoved(self, path, ifaces):
        pass


class AgentManager(dbus.service.Object):
    def __init__(self, world):
        super().__init__(world.bus, "/org/bluez")
        self.world = world

    @dbus.service.method("org.bluez.AgentManager1", in_signature="os", out_signature="",
                         sender_keyword="sender")
    def RegisterAgent(self, path, capability, sender=None):
        self.world.agent = (sender, str(path))
        self.world.save()

    @dbus.service.method("org.bluez.AgentManager1", in_signature="o", out_signature="")
    def RequestDefaultAgent(self, path):
        pass

    @dbus.service.method("org.bluez.AgentManager1", in_signature="o", out_signature="")
    def UnregisterAgent(self, path):
        self.world.agent = None
        self.world.save()


class Adapter(dbus.service.Object):
    def __init__(self, world, root):
        super().__init__(world.bus, HCI)
        self.world, self.root = world, root

    def appear(self, address, name, icon="input-keyboard"):
        path = HCI + "/dev_" + address.replace(":", "_")
        if path in self.world.devices:      # already known (paired): it is not re-announced
            return False
        dev = Device(self.world, path, address, name, icon)
        self.world.devices[path] = dev
        self.root.InterfacesAdded(dbus.ObjectPath(path), {DEVICE: dev.props})
        self.world.save()
        return False

    def preset(self, address, name, trusted=True):
        """A keyboard paired before this run: known, not connected, not being seen."""
        path = HCI + "/dev_" + address.replace(":", "_")
        dev = Device(self.world, path, address, name, "input-keyboard")
        dev.props["Paired"] = dbus.Boolean(True)
        dev.props["Trusted"] = dbus.Boolean(trusted)
        del dev.props["RSSI"]
        self.world.devices[path] = dev

    @dbus.service.method(ADAPTER, in_signature="", out_signature="")
    def StartDiscovery(self):
        self.world.discovering = True
        if SCENARIO == "only-others":
            GLib.timeout_add(300, self.appear, "AA:BB:CC:00:00:09", "Headset", "audio-headset")
            GLib.timeout_add(300, self.appear, "AA:BB:CC:00:00:08", None, "")
            return
        if SCENARIO == "in-pairing-mode":    # a paired keyboard that shows up in the scan
            dev = self.world.devices[HCI + "/dev_AA_BB_CC_00_00_01"]
            GLib.timeout_add(500, lambda: dev.set("RSSI", dbus.Int16(-50)) and False)
        GLib.timeout_add(500, self.appear, "AA:BB:CC:00:00:01", "Fake Keyboard")
        if SCENARIO == "two-keyboards":
            GLib.timeout_add(900, self.appear, "AA:BB:CC:00:00:02", "Other Keyboard")
        # A headset nearby must never be picked.
        GLib.timeout_add(300, self.appear, "AA:BB:CC:00:00:09", "Headset", "audio-headset")

    @dbus.service.method(ADAPTER, in_signature="", out_signature="")
    def StopDiscovery(self):
        self.world.discovering = False
        self.world.save()

    @dbus.service.method(ADAPTER, in_signature="o", out_signature="")
    def RemoveDevice(self, path):
        dev = self.world.devices.pop(str(path))
        dev.remove_from_connection()
        self.world.removed.append(str(path))
        self.root.InterfacesRemoved(path, [DEVICE])
        self.world.save()


class Device(dbus.service.Object):
    def __init__(self, world, path, address, name, icon):
        super().__init__(world.bus, path)
        self.world, self.path = world, path
        self.connect_calls = 0
        self.props = dbus.Dictionary({
            "Address": address, "Alias": name or address.replace(":", "-"), "Icon": icon,
            "Paired": dbus.Boolean(False), "Trusted": dbus.Boolean(False),
            "Connected": dbus.Boolean(False), "RSSI": dbus.Int16(-55),
        }, signature="sv")
        if name:
            self.props["Name"] = name

    def set(self, key, value):
        self.props[key] = value
        self.PropertiesChanged(DEVICE, {key: value}, [])
        self.world.save()

    @dbus.service.signal(PROPS, signature="sa{sv}as")
    def PropertiesChanged(self, iface, changed, invalidated):
        pass

    @dbus.service.method(PROPS, in_signature="ssv", out_signature="")
    def Set(self, iface, key, value):
        self.set(key, value)

    @dbus.service.method(DEVICE, in_signature="", out_signature="",
                         async_callbacks=("ok", "err"))
    def Connect(self, ok, err):
        self.connect_calls += 1
        self.world.agent_calls.append("Connect")

        def fail(message):
            exc = dbus.DBusException(message)
            exc._dbus_error_name = "org.bluez.Error.Failed"
            GLib.timeout_add(200, lambda: err(exc) and False)

        if CONNECT == "silent":
            fail("br-connection-page-timeout")
        elif CONNECT == "forgotten":
            fail("br-connection-key-missing")
        elif CONNECT == "wakes":
            # The computer cannot wake it; a little later the keyboard connects by itself.
            if self.connect_calls == 1:
                GLib.timeout_add(3000, lambda: self.set("Connected", dbus.Boolean(True)) and False)
            fail("br-connection-page-timeout")
        else:
            self.set("Connected", dbus.Boolean(True))
            ok()

    @dbus.service.method(DEVICE, in_signature="", out_signature="")
    def CancelPairing(self):
        self.world.agent_calls.append("CancelPairing")
        self.world.save()

    @dbus.service.method(DEVICE, in_signature="", out_signature="",
                         async_callbacks=("ok", "err"))
    def Pair(self, ok, err):
        world = self.world
        world.pair_calls += 1
        world.save()
        n = world.pair_calls
        me = dbus.ObjectPath(self.path)

        def done(*_):
            self.set("Paired", dbus.Boolean(True))
            ok()

        def refused(exc):
            err(error("AuthenticationRejected", str(exc)))

        if SCENARIO == "unreachable-then-ok" and n <= 2:
            GLib.timeout_add(300, lambda: err(error("ConnectionAttemptFailed", "Page Timeout")))
        elif SCENARIO == "cancel-then-ok" and n == 1:
            GLib.timeout_add(300, lambda: err(error("AuthenticationCanceled", "Canceled")))
        elif SCENARIO == "always-wrong":
            GLib.timeout_add(100, lambda: err(error("AuthenticationFailed", "wrong code")))
        elif SCENARIO == "justworks":
            GLib.timeout_add(200, done)          # no agent call at all
        elif SCENARIO == "authorize":
            world.call_agent("RequestAuthorization", "o", (me,), done, refused)
        elif SCENARIO == "confirm":
            world.call_agent("RequestConfirmation", "ou", (me, dbus.UInt32(424242)),
                             done, refused)
        elif SCENARIO == "legacy":
            world.call_agent("DisplayPinCode", "os", (me, "583747"),
                             lambda *_: GLib.timeout_add(300, done), refused)
        elif SCENARIO == "request-pin":
            world.call_agent("RequestPinCode", "o", (me,),
                             lambda pin: (world.agent_calls.append(f"pin={pin}"), done()),
                             refused)
        elif SCENARIO == "wrong-device":
            # A request about some other device must be refused by the agent.
            other = dbus.ObjectPath(HCI + "/dev_AA_BB_CC_00_00_09")
            world.call_agent("DisplayPinCode", "os", (other, "111111"), done, refused)
        else:  # passkey: shown first, then one report per key typed
            def step(entered):
                if entered > 6:
                    done()
                    return False
                world.call_agent("DisplayPasskey", "ouq",
                                 (me, dbus.UInt32(1234), dbus.UInt16(entered)),
                                 lambda *_: GLib.timeout_add(40, step, entered + 1), refused)
                return False
            step(0)


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    address = os.environ.get("DBUS_SYSTEM_BUS_ADDRESS", "")
    if not address or "system_bus_socket" in address:
        sys.exit("refusing to run: DBUS_SYSTEM_BUS_ADDRESS must point at a private test bus")
    bus = dbus.SystemBus()
    name = dbus.service.BusName("org.bluez", bus, do_not_queue=True)  # noqa: F841
    world = World(bus)
    root = Root(world)
    AgentManager(world)
    adapter = Adapter(world, root)
    if "paired" in PRESET:
        adapter.preset("AA:BB:CC:00:00:01", "Fake Keyboard", trusted="untrusted" not in PRESET)
    if "second" in PRESET:
        adapter.preset("AA:BB:CC:00:00:02", "Other Keyboard")
    world.save()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
