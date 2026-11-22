#!/usr/bin/python3
"""Pair a Bluetooth keyboard from a terminal and keep the pairing code on screen.

Talks to BlueZ over D-Bus: registers its own pairing agent, waits for the
keyboard to show up, pairs it, marks it trusted and connects it.
"""
import argparse
import datetime
import os
import platform
import random
import re
import signal
import subprocess
import sys

BLUEZ = "org.bluez"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
AGENT = "org.bluez.Agent1"
AGENT_MANAGER = "org.bluez.AgentManager1"
OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
PROPERTIES = "org.freedesktop.DBus.Properties"
AGENT_PATH = "/keybond/agent"

EXIT_OK = 0
EXIT_PAIR_FAILED = 1
EXIT_NOT_FOUND = 2
EXIT_ENVIRONMENT = 3

MAX_FAILURES = 5      # real pairing failures (wrong code, cancelled) before giving up
SETTLE_SECONDS = 4    # with no address given, wait this long for a second keyboard
RETRY_SECONDS = 5
PAIR_TIMEOUT = 120

__version__ = "0.4.0"

# Failures that only mean "the keyboard is not answering right now".
UNREACHABLE = {"ConnectionAttemptFailed", "UnknownObject", "InProgress", "NotReady"}

HINTS = {
    "AuthenticationFailed": "The code typed on the keyboard did not match, or Enter was "
                            "not pressed after it.",
    "AuthenticationCanceled": "Something cancelled the pairing. Close the desktop's "
                              "Bluetooth settings window, and check the keyboard is still "
                              "in pairing mode.",
    "AuthenticationRejected": "The keyboard refused. Clear the pairing slot on the "
                              "keyboard and try again.",
    "AuthenticationTimeout": "The code was not typed in time.",
    "ConnectionAttemptFailed": "The keyboard did not answer; its pairing mode has "
                               "probably ended.",
    "NoReply": "The Bluetooth service did not answer in time.",
}

LOGO_GLYPHS = {
    "K": ("█   █", "█  █ ", "███  ", "█  █ ", "█   █"),
    "E": ("█████", "█    ", "████ ", "█    ", "█████"),
    "Y": ("█   █", " █ █ ", "  █  ", "  █  ", "  █  "),
    "B": ("████ ", "█   █", "████ ", "█   █", "████ "),
    "O": (" ███ ", "█   █", "█   █", "█   █", " ███ "),
    "N": ("█   █", "██  █", "█ █ █", "█  ██", "█   █"),
    "D": ("████ ", "█   █", "█   █", "█   █", "████ "),
}
BRAND = "Jdai Tool"
TAGLINE = "the pairing code stays on screen"

FONT = {
    "0": (" ███ ", "█   █", "█   █", "█   █", " ███ "),
    "1": ("  █  ", " ██  ", "  █  ", "  █  ", " ███ "),
    "2": (" ███ ", "█   █", "  ██ ", " █   ", "█████"),
    "3": ("████ ", "    █", " ███ ", "    █", "████ "),
    "4": ("█  █ ", "█  █ ", "█████", "   █ ", "   █ "),
    "5": ("█████", "█    ", "████ ", "    █", "████ "),
    "6": (" ███ ", "█    ", "████ ", "█   █", " ███ "),
    "7": ("█████", "   █ ", "  █  ", " █   ", " █   "),
    "8": (" ███ ", "█   █", " ███ ", "█   █", " ███ "),
    "9": (" ███ ", "█   █", " ████", "    █", " ███ "),
}

COMMANDS = ("pair", "status", "fix")

EPILOG = """\
commands (put the command first; with none, keybond pairs):
  keybond                      pair the one keyboard that is in pairing mode
  keybond AA:BB:CC:DD:EE:FF    pair this keyboard
  keybond --again              remove the old pairing first, then pair afresh
  keybond status               list the keyboards paired here and their state
  keybond fix                  find out why a paired keyboard will not connect
  keybond COMMAND --help       the options of one command

before you pair:
  1. Close the desktop's Bluetooth settings window; while open it can take over
     the pairing and cancel it.
  2. Put the keyboard in pairing mode (its manual says how; usually a pairing
     button or key combination until a light blinks).
  3. When the code appears here, type it ON THE NEW KEYBOARD and press Enter.

exit status:
  0  paired / connected       1  pairing failed / still not connected
  2  no keyboard found, or more than one     3  Bluetooth off or unreachable
"""


# ---- pure helpers (unit tested) -------------------------------------------

def normalize_mac(text):
    """Return the address as AA:BB:CC:DD:EE:FF, or raise ValueError."""
    mac = text.strip().upper().replace("-", ":")
    if not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
        raise ValueError(f"not a Bluetooth address: {text!r} (expected AA:BB:CC:DD:EE:FF)")
    return mac


def format_code(code):
    """The code spaced out in a box. Used when big digits are not wanted."""
    digits = " ".join(str(code))
    body = f"   {digits}   then Enter   "
    return "\n".join(["┌" + "─" * len(body) + "┐", "│" + body + "│",
                      "└" + "─" * len(body) + "┘"])


def big_code(code):
    """The code in five-line digits, or None if it has characters the font lacks."""
    code = str(code)
    if not code or any(ch not in FONT for ch in code):
        return None
    rows = ["   ".join(FONT[ch][row] for ch in code) for row in range(5)]
    width = len(rows[0]) + 6
    lines = ["╔" + "═" * width + "╗", "║" + " " * width + "║"]
    lines += ["║   " + row + "   ║" for row in rows]
    lines += ["║" + " " * width + "║", "╚" + "═" * width + "╝"]
    return "\n".join(lines)


def logo():
    """The name in block letters, with the version, brand and tagline under it."""
    rows = ["   " + "  ".join(LOGO_GLYPHS[ch][row] for ch in "KEYBOND").rstrip()
            for row in range(5)]
    return "\n".join(rows + ["", f"   keybond {__version__}  ·  {BRAND}  ·  {TAGLINE}"])


def render_code(code, fancy):
    return (big_code(code) if fancy else None) or format_code(code)


def progress(entered, total=6):
    """Dots for the keys the keyboard has reported so far."""
    entered = max(0, min(int(entered), total))
    return "●" * entered + "○" * (total - entered)


def clean(text, limit=64):
    """A device-supplied string made safe to print: no control characters, bounded."""
    text = "".join(ch if ch.isprintable() else "?" for ch in str(text))
    return text if len(text) <= limit else text[:limit - 1] + "…"


def describe(props):
    name = props.get("Name") or props.get("Alias") or "unnamed device"
    return f"{clean(name)} ({clean(props.get('Address', '?'), 17)})"


def is_keyboard(props):
    return str(props.get("Icon", "")).startswith("input-keyboard")


def is_live(path, props, fresh):
    """True when the device is being seen now, not just remembered by BlueZ."""
    return "RSSI" in props or path in fresh


def candidates(devices, fresh, target=None):
    """Unpaired devices worth pairing: the target address, or any live keyboard."""
    found = []
    for path, props in sorted(devices.items()):
        if props.get("Paired"):
            continue
        if not is_live(path, props, fresh):
            continue
        if target is not None:
            if str(props.get("Address", "")).upper() == target:
                found.append(path)
        elif is_keyboard(props):
            found.append(path)
    return found


def paired_keyboards(devices):
    """Paths of the keyboards this computer is paired with."""
    return [path for path, props in sorted(devices.items())
            if props.get("Paired") and is_keyboard(props)]


def find_by_address(devices, address):
    for path, props in sorted(devices.items()):
        if str(props.get("Address", "")).upper() == address:
            return path
    return None


def explain_not_found(devices, fresh, target=None):
    """Why nothing was paired: (line, may it go in the log) pairs for the user.

    Lines naming other people's devices are shown but kept out of the log.
    """
    lines = []
    if target:
        lines.append((f"{target} was not seen. Is its pairing light blinking? "
                      "Is it close to the computer?", True))
    paired = [devices[p] for p in paired_keyboards(devices)]
    for props in paired:
        lines.append((f"Already paired here, so skipped: {describe(props)}", True))
    if paired:
        lines.append(("  to pair one of those afresh:  keybond --again <address>", True))
        lines.append(("  if it just will not connect:    keybond fix <address>", True))
    named, unnamed = [], 0
    for path, props in sorted(devices.items()):
        if props.get("Paired") or not is_live(path, props, fresh) or is_keyboard(props):
            continue
        if target and str(props.get("Address", "")).upper() == target:
            continue
        if props.get("Name"):
            named.append(props)
        else:
            unnamed += 1
    if named and not target:
        lines.append(("Seen nearby, but not announcing themselves as keyboards:", False))
        for props in named[:6]:
            lines.append((f"  {describe(props)}", False))
        lines.append(("  if one of them is your keyboard:  keybond <address>", False))
    if not target:
        if not named and not paired:
            where = f"{unnamed} unnamed devices nearby, " if unnamed else "Nothing nearby, "
            lines.append((where + "none in keyboard pairing mode.", True))
        lines.append(("Is the keyboard's pairing light blinking? Is it close to the "
                      "computer?", True))
    return lines


# What a failed Connect() says about a keyboard that is already paired.
BOND_LOST = ("key-missing", "authentication", "refused", "invalid exchange", "rejected")
NOT_ANSWERING = ("page-timeout", "create-socket", "host is down", "host-down", "timed out",
                 "timeout", "noreply", "connection-unknown", "aborted", "canceled")


def connect_verdict(error_name, message=""):
    """'off' | 'busy' | 'forgotten' | 'silent' | 'unknown' for a failed Connect()."""
    text = f"{error_name} {message}".lower()
    if "notready" in text:
        return "off"
    if "inprogress" in text or "in progress" in text or "busy" in text:
        return "busy"
    if any(word in text for word in BOND_LOST):
        return "forgotten"
    if any(word in text for word in NOT_ANSWERING):
        return "silent"
    return "unknown"


def state_words(props):
    """How a paired keyboard is doing, in a few words."""
    words = ["connected" if props.get("Connected") else "not connected"]
    if props.get("Blocked"):
        words.append("blocked")
    if not props.get("Trusted"):
        words.append("not trusted, so it will not reconnect by itself")
    return ", ".join(words)


def failure_kind(dbus_error_name):
    """(short name, is it only 'not answering right now', hint or None)."""
    short = str(dbus_error_name).rsplit(".", 1)[-1]
    return short, short in UNREACHABLE, HINTS.get(short)


def ask(question):
    """A yes/no question on the terminal. No terminal, or anything but y, means no."""
    if not sys.stdin.isatty():
        return False
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def settings_window_open(proc="/proc"):
    """True if GNOME Settings is running; its Bluetooth page can cancel a pairing."""
    try:
        for entry in os.listdir(proc):
            if entry.isdigit():
                try:
                    with open(os.path.join(proc, entry, "comm"), encoding="utf-8") as fh:
                        if fh.read().strip() == "gnome-control-c":
                            return True
                except OSError:
                    continue
    except OSError:
        pass
    return False


class Screen:
    """Terminal output: colour and the one-line waiting ticker, both optional."""

    def __init__(self, fancy, colour, note):
        self.fancy, self.colour, self.note = fancy, colour, note
        self.ticker_drawn = False

    def paint(self, code, text):
        return f"\033[{code}m{text}\033[0m" if self.colour else text

    def clear_ticker(self):
        if self.ticker_drawn:
            sys.stdout.write("\r\033[K")
            self.ticker_drawn = False

    def ticker(self, text):
        if self.fancy:
            sys.stdout.write("\r\033[K" + self.paint("2", text))
            sys.stdout.flush()
            self.ticker_drawn = True

    def say(self, message="", log=True):
        self.clear_ticker()
        print(message, flush=True)
        plain = re.sub(r"\033\[[0-9;]*m", "", message).strip()
        if plain and log:
            self.note(plain.replace("\n", " | "))

    def ok(self, message):
        self.say("  " + self.paint("32", "✓" if self.fancy else "ok:") + " " + message)

    def bad(self, message):
        self.say("  " + self.paint("31", "✗" if self.fancy else "FAILED:") + " " + message)

    def hint(self, message, log=True):
        self.say("    " + self.paint("2", message), log)

    def warn(self, message):
        self.say("  " + self.paint("33", "!") + " " + message)

    def code(self, code):
        """Show the code. It is printed but never written to the log line by line."""
        self.clear_ticker()
        print()
        print(self.paint("1", "  Type this ON THE NEW KEYBOARD, then press Enter:"))
        print()
        for line in render_code(code, self.fancy).splitlines():
            print("  " + self.paint("1;36", line))
        print(flush=True)


# ---- D-Bus session ---------------------------------------------------------

def import_dbus():
    """The system D-Bus bindings as (dbus, GLib), or None after saying how to get them."""
    try:
        import dbus
        import dbus.mainloop.glib
        import dbus.service
        from gi.repository import GLib
    except ImportError as exc:
        print(f"Missing system library: {exc}.\n"
              "On Debian/Ubuntu: sudo apt install python3-dbus python3-gi\n"
              "Run it with the system Python (/usr/bin/python3); a virtualenv or conda "
              "Python usually cannot see these.", file=sys.stderr)
        return None
    return dbus, GLib


def open_log(log_path):
    """(note, close): note(message) appends a timestamped line when a log was asked for."""
    log_file = open(os.path.expanduser(log_path), "a", encoding="utf-8") if log_path else None

    def note(message):
        if log_file:
            stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
            log_file.write(f"{stamp} {message}\n")
            log_file.flush()

    def close():
        if log_file and not log_file.closed:
            log_file.close()

    return note, close


def show_logo(ui):
    if ui.fancy:
        art, _, credit = logo().rpartition("\n")
        print("\n" + ui.paint("1;36", art) + "\n" + credit + "\n")


def open_bluez(dbus, ui, adapter_name):
    """(bus, objects, adapter_path, adapter), or an exit code after saying what is wrong."""
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object(BLUEZ, "/"), OBJECT_MANAGER)
        objects = manager.GetManagedObjects()
    except dbus.DBusException as exc:
        ui.bad("Cannot reach the Bluetooth service (bluetoothd): "
               + clean(exc.get_dbus_message(), 120))
        ui.hint("Is it running?  systemctl status bluetooth")
        return EXIT_ENVIRONMENT

    adapters = sorted(p for p, ifaces in objects.items() if ADAPTER in ifaces)
    if adapter_name:
        adapters = [p for p in adapters if p.rsplit("/", 1)[-1] == adapter_name]
    if not adapters:
        ui.bad(f"No Bluetooth adapter named {adapter_name}." if adapter_name
               else "No Bluetooth adapter found.")
        return EXIT_ENVIRONMENT
    adapter_path = adapters[0]
    if not objects[adapter_path][ADAPTER].get("Powered"):
        ui.bad("Bluetooth is switched off. Turn it on and run this again.")
        return EXIT_ENVIRONMENT
    adapter = dbus.Interface(bus.get_object(BLUEZ, adapter_path), ADAPTER)
    return bus, objects, adapter_path, adapter


def devices_of(objects, adapter_path):
    return {str(path): dict(ifaces[DEVICE]) for path, ifaces in objects.items()
            if DEVICE in ifaces and str(path).startswith(adapter_path + "/")}


def run_status(adapter_name, fancy, colour):
    """List the keyboards paired with this computer."""
    mods = import_dbus()
    if mods is None:
        return EXIT_ENVIRONMENT
    dbus, _ = mods
    ui = Screen(fancy, colour, lambda message: None)
    show_logo(ui)
    opened = open_bluez(dbus, ui, adapter_name)
    if isinstance(opened, int):
        return opened
    _, objects, adapter_path, _ = opened
    devices = devices_of(objects, adapter_path)
    paired = paired_keyboards(devices)
    if not paired:
        ui.say("  No keyboard is paired with this computer.")
        ui.hint("To pair one:  keybond")
        return EXIT_OK
    ui.say("  Keyboards paired with this computer:\n")
    for path in paired:
        props = devices[path]
        mark = ui.ok if props.get("Connected") else (
            lambda text: ui.say("  " + ("•" if fancy else "-") + " " + text))
        mark(f"{describe(props)}: {state_words(props)}")
    ui.say()
    if any(not devices[p].get("Connected") for p in paired):
        ui.hint("Not connected is normal for a keyboard that is asleep, off or away.")
        ui.hint("If one will not come back:  keybond fix <address>")
    return EXIT_OK


def run_fix(target, adapter_name, wait, log_path, fancy, colour):
    """Find out why a paired keyboard will not connect, and mend what can be mended."""
    mods = import_dbus()
    if mods is None:
        return EXIT_ENVIRONMENT
    dbus, GLib = mods
    note, close_log = open_log(log_path)
    ui = Screen(fancy, colour, note)
    show_logo(ui)
    opened = open_bluez(dbus, ui, adapter_name)
    if isinstance(opened, int):
        close_log()
        return opened
    bus, objects, adapter_path, adapter = opened
    devices = devices_of(objects, adapter_path)
    note(f"keybond {__version__} fix; kernel {platform.release()}")

    def done(code):
        note(f"exit {code}")
        close_log()
        return code

    # -- which keyboard --
    if target:
        path = find_by_address(devices, target)
        if path is None or not devices[path].get("Paired"):
            ui.bad(f"{target} is not paired with this computer.")
            ui.hint(f"To pair it:  keybond {target}")
            return done(EXIT_NOT_FOUND)
    else:
        paired = paired_keyboards(devices)
        if not paired:
            ui.bad("No keyboard is paired with this computer.")
            ui.hint("To pair one:  keybond")
            return done(EXIT_NOT_FOUND)
        down = [p for p in paired if not devices[p].get("Connected")]
        if not down:
            for p in paired:
                ui.ok(f"{describe(devices[p])}: {state_words(devices[p])}")
            ui.say("\n  Every paired keyboard is connected; nothing to fix.")
            ui.hint("If keys still do nothing, switch the keyboard off and on again.")
            return done(EXIT_OK)
        if len(down) > 1:
            ui.bad("More than one paired keyboard is not connected. Say which one:")
            for p in down:
                ui.say("      " + describe(devices[p]))
            return done(EXIT_NOT_FOUND)
        path = down[0]

    props = devices[path]
    name, address = describe(props), str(props.get("Address", ""))
    ui.say(f"  Checking {name}\n")
    ui.ok("Paired with this computer")
    device_props = dbus.Interface(bus.get_object(BLUEZ, path), PROPERTIES)
    device = dbus.Interface(bus.get_object(BLUEZ, path), DEVICE)

    for key, wanted, problem in (
            ("Blocked", False, "It was blocked on this computer; unblocked it"),
            ("Trusted", True, "It was not trusted, so it could not reconnect by itself; "
                              "trusted it")):
        if bool(props.get(key)) != wanted:
            try:
                device_props.Set(DEVICE, key, dbus.Boolean(wanted))
                props[key] = wanted
                ui.ok(problem)
            except dbus.DBusException as exc:
                ui.bad(f"Could not set {key}: " + clean(exc.get_dbus_message(), 120))
        elif key == "Trusted":
            ui.ok("Trusted, so it may reconnect by itself")

    if props.get("Connected"):
        ui.ok("Connected")
        ui.say("\n  The link is up. If keys still do nothing, switch the keyboard off and "
               "on again.\n")
        return done(EXIT_OK)

    if settings_window_open():
        ui.warn("GNOME Settings is open. If its Bluetooth page is showing, close it: its "
                "constant scanning gets in the way of reconnecting.")

    # -- wake it and watch --
    state = {"left": wait, "connected": False, "calling": False, "verdict": None,
             "error": "", "discoverable": False, "stopped": False}
    loop = GLib.MainLoop()

    def properties_changed(iface, changed, invalidated, path_=None):
        if iface != DEVICE or path_ != path:
            return
        if "RSSI" in changed:
            state["discoverable"] = True
            note("device: seen in the scan (discoverable)")
        if changed.get("Connected"):
            state["connected"] = True
            loop.quit()

    def connected():
        state["calling"] = False
        state["connected"] = True
        loop.quit()

    def connect_failed(exc):
        state["calling"] = False
        state["error"] = f"{exc.get_dbus_name()}: {clean(exc.get_dbus_message(), 120)}"
        state["verdict"] = connect_verdict(exc.get_dbus_name(), exc.get_dbus_message())
        note(f"Connect() failed: {state['error']} -> {state['verdict']}")

    def tick():
        state["left"] -= 1
        if state["left"] <= 0:
            loop.quit()
            return False
        if not state["calling"] and state["left"] % 5 == 0:
            state["calling"] = True
            device.Connect(reply_handler=connected, error_handler=connect_failed, timeout=25)
        ui.ticker(f"  … waiting for the keyboard to answer  ({state['left']}s left, "
                  "Ctrl+C to stop)")
        return True

    def interrupted():
        state["stopped"] = True
        loop.quit()
        return False

    bus.add_signal_receiver(properties_changed, bus_name=BLUEZ, dbus_interface=PROPERTIES,
                            signal_name="PropertiesChanged", path_keyword="path_")
    ui.say("\n  Press any key on the keyboard now, to wake it.")
    if not fancy:
        ui.say(f"  Waiting up to {wait}s for it to answer…")
    scanning = False
    try:
        try:
            adapter.StartDiscovery()   # a paired keyboard only shows up here in pairing mode
            scanning = True
        except dbus.DBusException:
            pass
        state["calling"] = True
        device.Connect(reply_handler=connected, error_handler=connect_failed, timeout=25)
        GLib.timeout_add_seconds(1, tick)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, interrupted)
        loop.run()
    finally:
        ui.clear_ticker()
        if scanning:
            try:
                adapter.StopDiscovery()
            except dbus.DBusException:
                pass

    if state["connected"]:
        ui.ok("Connected")
        ui.say(f"\n  {name} is back.\n")
        return done(EXIT_OK)
    if state["stopped"]:
        ui.say("\n  Stopped.")
        return done(EXIT_PAIR_FAILED)

    ui.bad("Still not connected")
    again = f"keybond --again {address}"
    if state["discoverable"]:
        ui.say("\n  The keyboard is in pairing mode, which means it is not looking for this "
               "computer:\n  it forgot the pairing, or it is on a different slot.")
        ui.hint("Switch it to the slot it used with this computer, or pair it afresh:")
        ui.hint(f"  {again}")
    elif state["verdict"] == "forgotten":
        ui.say("\n  The keyboard answered but would not accept the stored key: it has "
               "forgotten this computer.")
        ui.hint(f"Pair it afresh:  {again}")
    else:
        ui.say("\n  This computer's side is fine. The keyboard is not answering.")
        ui.hint("Is it switched on, with charge in its batteries?")
        ui.hint("Is it on the slot it used with this computer?")
        ui.hint("Is it connected to another computer, phone or tablet right now?")
        ui.hint("Is it within a couple of metres?")
        ui.hint(f"If none of that helps, pair it afresh:  {again}")
    ui.say()
    return done(EXIT_PAIR_FAILED)


def run(target, adapter_name, timeout, log_path, fancy, colour, again=False):
    mods = import_dbus()
    if mods is None:
        return EXIT_ENVIRONMENT
    dbus, GLib = mods

    class Rejected(dbus.DBusException):
        _dbus_error_name = "org.bluez.Error.Rejected"

    note, close_log = open_log(log_path)
    ui = Screen(fancy, colour, note)
    show_logo(ui)
    opened = open_bluez(dbus, ui, adapter_name)
    if isinstance(opened, int):
        close_log()
        return opened
    bus, objects, adapter_path, adapter = opened
    adapter_props = objects[adapter_path][ADAPTER]

    note(f"keybond {__version__}; python {platform.python_version()}; "
         f"kernel {platform.release()}")
    try:
        bluez_version = subprocess.run(["bluetoothctl", "--version"], capture_output=True,
                                       text=True, timeout=5).stdout.strip().split()[-1]
    except (OSError, subprocess.SubprocessError, IndexError):
        bluez_version = "unknown"
    note(f"bluez: {bluez_version}; adapter {adapter_path} "
         f"modalias {adapter_props.get('Modalias', '?')}")

    state = {
        "devices": {}, "fresh": set(),
        "pairing": None,    # path of the device a Pair() call is in flight for
        "quiet": False,     # the attempt in flight is a silent re-try
        "started": False,   # at least one attempt was made
        "failures": 0,      # real failures, not "keyboard not answering"
        "proved": False,    # a code was typed on the device, or the user vouched for it
        "shown": None,      # the code currently on screen
        "settling": False, "expired": False, "left": timeout,
        "done": False, "code": EXIT_NOT_FOUND,
    }
    state["devices"] = devices_of(objects, adapter_path)
    loop = GLib.MainLoop()

    def finish(code):
        if not state["done"]:
            state["done"] = True
            state["code"] = code
            loop.quit()

    def show_code(code):
        state["proved"] = True
        if state["shown"] != code:
            state["shown"] = code
            ui.code(code)

    # -- the pairing agent: BlueZ calls these while Pair() is in flight --

    class Agent(dbus.service.Object):
        def _check(self, device):
            if str(device) != state["pairing"]:
                note(f"agent: rejected a request for {device}")
                raise Rejected("not the device being paired")

        @dbus.service.method(AGENT, in_signature="", out_signature="")
        def Release(self):
            note("agent: Release")

        @dbus.service.method(AGENT, in_signature="o", out_signature="s")
        def RequestPinCode(self, device):
            self._check(device)
            pin = f"{random.SystemRandom().randrange(10**6):06d}"
            note(f"agent: RequestPinCode -> {pin}")
            show_code(pin)
            return pin

        @dbus.service.method(AGENT, in_signature="os", out_signature="")
        def DisplayPinCode(self, device, pincode):
            self._check(device)
            pincode = clean(pincode, 16)
            note(f"agent: DisplayPinCode {pincode}")
            show_code(pincode)

        @dbus.service.method(AGENT, in_signature="o", out_signature="u")
        def RequestPasskey(self, device):
            self._check(device)
            passkey = random.SystemRandom().randrange(10**6)
            note(f"agent: RequestPasskey -> {passkey:06d}")
            show_code(f"{passkey:06d}")
            return dbus.UInt32(passkey)

        @dbus.service.method(AGENT, in_signature="ouq", out_signature="")
        def DisplayPasskey(self, device, passkey, entered):
            self._check(device)
            note(f"agent: DisplayPasskey {int(passkey):06d} entered={int(entered)}")
            show_code(f"{int(passkey):06d}")
            if int(entered):
                line = f"  keys received: {progress(entered)}"
                if fancy:
                    ui.ticker(line)
                else:
                    print(line, flush=True)

        @dbus.service.method(AGENT, in_signature="ou", out_signature="")
        def RequestConfirmation(self, device, passkey):
            self._check(device)
            ui.say(f"\n  The device shows a code instead of taking one: {int(passkey):06d}")
            if not ask("  Does the device show exactly this code?"):
                note("agent: RequestConfirmation -> rejected")
                raise Rejected("code not confirmed")
            note("agent: RequestConfirmation -> confirmed by the user")
            state["proved"] = True

        @dbus.service.method(AGENT, in_signature="o", out_signature="")
        def RequestAuthorization(self, device):
            self._check(device)
            name = describe(state["devices"].get(str(device), {}))
            ui.say(f"\n  {name} wants to pair without any code, so nothing proves it is "
                   "your keyboard.")
            if not ask("  Is that the device in front of you?"):
                note("agent: RequestAuthorization -> rejected")
                raise Rejected("not confirmed")
            note("agent: RequestAuthorization -> confirmed by the user")
            state["proved"] = True

        @dbus.service.method(AGENT, in_signature="os", out_signature="")
        def AuthorizeService(self, device, uuid):
            self._check(device)
            note(f"agent: AuthorizeService {uuid} -> accepted")

        @dbus.service.method(AGENT, in_signature="", out_signature="")
        def Cancel(self):
            note("agent: Cancel")

    # -- pairing flow --

    def device_iface(path, iface=DEVICE):
        return dbus.Interface(bus.get_object(BLUEZ, path), iface)

    def after_pairing(path):
        props = state["devices"].get(path, {})
        if not state["proved"]:
            # Paired with no code at all: anything nearby could have answered.
            ui.say(f"\n  {describe(props)} paired without asking for a code, so nothing "
                   "proves it is your keyboard.")
            if not ask("  Keep it and let it type on this computer?"):
                try:
                    adapter.RemoveDevice(dbus.ObjectPath(path))
                    ui.ok("Removed it again.")
                except dbus.DBusException as exc:
                    ui.bad("Could not remove it: " + clean(exc.get_dbus_message(), 120))
                finish(EXIT_PAIR_FAILED)
                return
        ui.ok("Paired")
        try:
            device_iface(path, PROPERTIES).Set(DEVICE, "Trusted", dbus.Boolean(True))
            ui.ok("Trusted, so it reconnects by itself")
        except dbus.DBusException as exc:
            ui.bad("Could not mark it trusted: " + clean(exc.get_dbus_message(), 120))

        def connected():
            ui.ok("Connected")
            ui.say(f"\n  {describe(props)} is ready. Try typing on it.\n")
            finish(EXIT_OK)

        def connect_failed(exc):
            note(f"Connect failed: {exc.get_dbus_name()}")
            ui.say(f"\n  {describe(props)} is paired. It did not connect right away; "
                   "press a key on it to wake it.\n")
            finish(EXIT_OK)

        device_iface(path).Connect(reply_handler=connected, error_handler=connect_failed,
                                   timeout=30)

    def start_pairing(path, quiet=False):
        state.update(pairing=path, quiet=quiet, proved=False, shown=None, started=True)
        if not quiet:
            ui.ok(f"Found {describe(state['devices'][path])}")
            ui.say("  Pairing… keep the keyboard in pairing mode.")
        note(f"Pair() on {path} quiet={quiet}")

        def paired():
            note("Pair() succeeded")
            after_pairing(path)

        def pair_failed(exc):
            short, unreachable, hint = failure_kind(exc.get_dbus_name())
            note(f"Pair() failed: {exc.get_dbus_name()}: {clean(exc.get_dbus_message(), 120)}")
            if short == "AlreadyExists":
                after_pairing(path)
                return
            state["pairing"] = None
            # Demand a new sighting, or the retry timer, before the next attempt.
            state["fresh"].discard(path)
            state["devices"].get(path, {}).pop("RSSI", None)
            if not unreachable:
                state["failures"] += 1
            if not (unreachable and quiet):
                ui.bad(f"Pairing failed ({short})")
                if hint:
                    ui.hint(hint)
            if state["expired"] or state["failures"] >= MAX_FAILURES:
                finish(EXIT_PAIR_FAILED)
                return
            if not quiet:
                ui.say("  Put the keyboard back in pairing mode; trying again as soon as "
                       "it answers.")
            GLib.timeout_add_seconds(RETRY_SECONDS, retry, path)

        device_iface(path).Pair(reply_handler=paired, error_handler=pair_failed,
                                timeout=PAIR_TIMEOUT)

    def retry(path):
        if state["done"] or state["pairing"]:
            return False
        props = state["devices"].get(path)
        if props is not None and not props.get("Paired"):
            start_pairing(path, quiet=True)
        else:
            consider()
        return False

    def settle():
        state["settling"] = False
        if state["pairing"] or state["done"]:
            return False
        found = candidates(state["devices"], state["fresh"])
        if len(found) == 1:
            start_pairing(found[0])
        elif len(found) > 1:
            ui.bad("More than one keyboard is in pairing mode. Run again with an address:")
            for path in found:
                ui.say("      " + describe(state["devices"][path]))
            finish(EXIT_NOT_FOUND)
        return False

    def consider():
        if state["pairing"] or state["done"]:
            return
        found = candidates(state["devices"], state["fresh"], target)
        if not found:
            return
        if target:
            start_pairing(found[0])
        elif not state["settling"]:
            state["settling"] = True
            GLib.timeout_add_seconds(SETTLE_SECONDS, settle)

    # -- signals from BlueZ --

    def interfaces_added(path, ifaces):
        if DEVICE in ifaces and str(path).startswith(adapter_path + "/"):
            props = dict(ifaces[DEVICE])
            state["devices"][str(path)] = props
            state["fresh"].add(str(path))
            if is_keyboard(props) or str(props.get("Address", "")).upper() == target:
                # Other people's devices stay out of a log meant for bug reports.
                note(f"seen: {describe(props)} icon={props.get('Icon', '-')} "
                     f"legacy={bool(props.get('LegacyPairing', False))}")
            consider()

    def interfaces_removed(path, ifaces):
        if DEVICE in ifaces:
            state["devices"].pop(str(path), None)
            state["fresh"].discard(str(path))

    def properties_changed(iface, changed, invalidated, path=None):
        if iface != DEVICE or path not in state["devices"]:
            return
        props = state["devices"][path]
        props.update(changed)
        for key in invalidated:
            props.pop(key, None)
        if path == state["pairing"] or (target and props.get("Address") == target):
            shown = {str(k): (int(v) if k == "RSSI" else bool(v)) for k, v in changed.items()
                     if k in ("Connected", "Paired", "Bonded", "ServicesResolved", "RSSI")}
            if shown:
                note(f"device: {shown}")
        consider()

    def tick():
        if state["done"]:
            return False
        state["left"] -= 1
        if state["left"] <= 0:
            state["expired"] = True
            if not state["pairing"] or state["quiet"]:
                if state["started"]:
                    ui.bad("Gave up: the keyboard did not come back in time.")
                    finish(EXIT_PAIR_FAILED)
                else:
                    ui.bad("No keyboard in pairing mode showed up.")
                    for line, loggable in explain_not_found(state["devices"], state["fresh"],
                                                            target):
                        ui.hint(line, loggable)
                    finish(EXIT_NOT_FOUND)
            return False  # an attempt showing a code is in flight: let it finish
        if not state["pairing"] or state["quiet"]:
            what = target or "a keyboard in pairing mode"
            ui.ticker(f"  … waiting for {what}  ({state['left']}s left, Ctrl+C to stop)")
        return True

    def interrupted():
        ui.say("\n  Stopped.")
        finish(EXIT_PAIR_FAILED if state["started"] else EXIT_NOT_FOUND)
        return False

    # -- already paired? --

    if again:
        if target:
            known = find_by_address(state["devices"], target)
            doomed = [known] if known and state["devices"][known].get("Paired") else []
        else:
            doomed = paired_keyboards(state["devices"])
            if len(doomed) > 1:
                ui.bad("More than one keyboard is paired here. Say which one to pair again:")
                for path in doomed:
                    ui.say("      " + describe(state["devices"][path]))
                close_log()
                return EXIT_NOT_FOUND
        for path in doomed:
            props = state["devices"][path]
            try:
                adapter.RemoveDevice(dbus.ObjectPath(path))
            except dbus.DBusException as exc:
                ui.bad(f"Could not remove the old pairing of {describe(props)}: "
                       + clean(exc.get_dbus_message(), 120))
                close_log()
                return EXIT_PAIR_FAILED
            state["devices"].pop(path, None)
            ui.ok(f"Removed the old pairing of {describe(props)}")
            target = target or str(props.get("Address", "")).upper()  # pair that same one

    if target:
        known = find_by_address(state["devices"], target)
        if known and state["devices"][known].get("Paired"):
            props = state["devices"][known]
            ui.ok(f"{describe(props)} is already paired: {state_words(props)}.")
            if not props.get("Trusted"):
                device_iface(known, PROPERTIES).Set(DEVICE, "Trusted", dbus.Boolean(True))
                ui.ok("Trusted, so it reconnects by itself")
            ui.hint(f"If it will not connect:  keybond fix {target}")
            ui.hint(f"To pair it afresh:       keybond --again {target}")
            close_log()
            return EXIT_OK

    # -- go --

    if settings_window_open():
        ui.warn("GNOME Settings is open. If its Bluetooth page is showing, close it: it "
                "can cancel the pairing.")

    agent = Agent(bus, AGENT_PATH)
    agent_manager = dbus.Interface(bus.get_object(BLUEZ, "/org/bluez"), AGENT_MANAGER)
    agent_manager.RegisterAgent(AGENT_PATH, "KeyboardDisplay")
    agent_manager.RequestDefaultAgent(AGENT_PATH)
    note("agent registered as default (KeyboardDisplay)")

    bus.add_signal_receiver(interfaces_added, bus_name=BLUEZ, dbus_interface=OBJECT_MANAGER,
                            signal_name="InterfacesAdded")
    bus.add_signal_receiver(interfaces_removed, bus_name=BLUEZ, dbus_interface=OBJECT_MANAGER,
                            signal_name="InterfacesRemoved")
    bus.add_signal_receiver(properties_changed, bus_name=BLUEZ, dbus_interface=PROPERTIES,
                            signal_name="PropertiesChanged", path_keyword="path")

    scanning = False
    try:
        try:
            adapter.StartDiscovery()
            scanning = True
        except dbus.DBusException as exc:
            if not exc.get_dbus_name().endswith("InProgress"):
                ui.bad("Could not start scanning: " + clean(exc.get_dbus_message(), 120))
                return EXIT_ENVIRONMENT
        ui.say("  Put the keyboard in pairing mode now.")
        if not fancy:
            ui.say(f"  Waiting up to {timeout}s for {target or 'a keyboard'}…")
        GLib.timeout_add_seconds(1, tick)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, interrupted)
        consider()
        loop.run()
    finally:
        ui.clear_ticker()
        calls = []
        if state["pairing"] and state["code"] != EXIT_OK:
            calls.append(device_iface(state["pairing"]).CancelPairing)
        if scanning:
            calls.append(adapter.StopDiscovery)
        calls.append(lambda: agent_manager.UnregisterAgent(AGENT_PATH))
        for call in calls:
            try:
                call()
            except dbus.DBusException:
                pass
        agent.remove_from_connection()
        note(f"exit {state['code']}")
        close_log()
    return state["code"]


def positive_seconds(text):
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive number of seconds")
    return value


def build_parser(command="pair"):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--adapter", metavar="NAME",
                        help="Bluetooth adapter to use, e.g. hci0 (default: the first)")
    common.add_argument("--plain", action="store_true",
                        help="no logo, big digits, colour or live countdown "
                             "(automatic when output is not a terminal)")
    common.add_argument("--version", action="version",
                        version=f"keybond {__version__} ({BRAND})")
    if command == "status":
        return argparse.ArgumentParser(
            prog="keybond status", parents=[common],
            description="List the keyboards paired with this computer and whether each is "
                        "connected.")
    if command == "fix":
        parser = argparse.ArgumentParser(
            prog="keybond fix", parents=[common],
            description="Find out why a paired keyboard will not connect: checks this "
                        "computer's side, mends what it can, then waits for the keyboard "
                        "to answer and says what it found.")
        parser.add_argument("address", nargs="?",
                            help="keyboard address. Leave it out when only one paired "
                                 "keyboard is not connected")
        parser.add_argument("--wait", type=positive_seconds, default=30, metavar="SECONDS",
                            help="how long to wait for the keyboard to answer (default: 30)")
        parser.add_argument("--log", metavar="FILE",
                            help="append a timestamped record of the check to FILE")
        return parser
    parser = argparse.ArgumentParser(
        prog="keybond", parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="keybond: pair a Bluetooth keyboard and keep the pairing code on\n"
                    "screen until you have typed it. No root needed.",
        epilog=EPILOG + f"\n{BRAND}\n")
    parser.add_argument("address", nargs="?",
                        help="keyboard address, AA:BB:CC:DD:EE:FF. Leave it out to pair "
                             "the one keyboard that is in pairing mode")
    parser.add_argument("--again", action="store_true",
                        help="remove the keyboard's old pairing first, then pair it afresh")
    parser.add_argument("--timeout", type=positive_seconds, default=180, metavar="SECONDS",
                        help="how long to wait for the keyboard (default: 180)")
    parser.add_argument("--log", metavar="FILE",
                        help="append a timestamped record of the attempt to FILE")
    return parser


def split_command(argv):
    """('pair' | 'status' | 'fix', the remaining arguments). The command comes first."""
    if argv and argv[0] in COMMANDS:
        return argv[0], list(argv[1:])
    return "pair", list(argv)


def main(argv=None):
    command, rest = split_command(sys.argv[1:] if argv is None else argv)
    parser = build_parser(command)
    args = parser.parse_args(rest)
    address = getattr(args, "address", None)
    try:
        target = normalize_mac(address) if address else None
    except ValueError as exc:
        parser.error(str(exc))
    fancy = sys.stdout.isatty() and not args.plain
    colour = fancy and "NO_COLOR" not in os.environ
    if command == "status":
        return run_status(args.adapter, fancy, colour)
    if command == "fix":
        return run_fix(target, args.adapter, args.wait, args.log, fancy, colour)
    return run(target, args.adapter, args.timeout, args.log, fancy, colour, args.again)


if __name__ == "__main__":
    sys.exit(main())
