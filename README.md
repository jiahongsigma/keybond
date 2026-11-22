<h1 align="center">Keybond</h1>

<p align="center">
  <a href="https://langvector.com"><img src="https://raw.githubusercontent.com/jiahongsigma/keybond/main/assets/jdai-tool-mark.svg" width="26" height="26" alt="" align="absmiddle"></a>
  <a href="https://langvector.com"><b>Jdai Tool</b></a>
</p>

<p align="center">
  <a href="https://github.com/jiahongsigma/keybond/actions/workflows/tests.yml"><img alt="tests" src="https://github.com/jiahongsigma/keybond/actions/workflows/tests.yml/badge.svg"></a>
  <a href="https://github.com/jiahongsigma/keybond/blob/main/LICENSE"><img alt="license: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <img alt="python 3" src="https://img.shields.io/badge/python-3-blue.svg">
  <img alt="platform: Linux" src="https://img.shields.io/badge/platform-Linux-lightgrey.svg">
  <img alt="Bluetooth: BlueZ" src="https://img.shields.io/badge/Bluetooth-BlueZ-0a66c2.svg">
</p>

<p align="center"><b>English</b> | <a href="https://github.com/jiahongsigma/keybond/blob/main/README.zh-CN.md">简体中文</a></p>

<p align="center"><b>Pair a Bluetooth keyboard on Linux when the desktop's pairing code disappears before you can read it.</b></p>

To pair a Bluetooth keyboard, your computer shows a code and you type it on the keyboard.
On some Linux desktops the window with the code closes by itself after a moment, so the
pairing can never finish. keybond shows the code in your terminal instead, and keeps it
there until you have typed it.

## Quick start

```
git clone https://github.com/jiahongsigma/keybond.git
cd keybond
./keybond.py
```

Then:

1. Put the keyboard in pairing mode (hold its pairing button or key combination until a
   light blinks).
2. Type the code keybond shows **on the new keyboard**, and press `Enter` on it.

That's all. The keyboard is paired, and reconnects by itself from now on.

## What it looks like

```
  Put the keyboard in pairing mode now.
  ✓ Found Majestouch Convertible 2 (AA:BB:CC:DD:EE:FF)

  Type this ON THE NEW KEYBOARD, then press Enter:

  ╔═══════════════════════════════════════════════════╗
  ║                                                   ║
  ║   █████    ███    ████    █████   █  █    █████   ║
  ║   █       █   █       █      █    █  █       █    ║
  ║   ████     ███     ███      █     █████     █     ║
  ║       █   █   █       █    █         █     █      ║
  ║   ████     ███    ████     █         █     █      ║
  ║                                                   ║
  ╚═══════════════════════════════════════════════════╝

  ✓ Paired
  ✓ Trusted, so it reconnects by itself
  ✓ Connected
```

## If it doesn't work first time

**Nothing is found.** Check three things:

- The keyboard's pairing light is blinking, and it is close to the computer.
- The desktop's Bluetooth settings window is closed. While open, it can cancel the pairing.
- The keyboard was not already paired to this computer. If it was, keybond says so; pair
  it afresh with:

  ```
  ./keybond.py --again
  ```

When nothing is found, keybond lists what it did see nearby, in case your keyboard is
there under another name.

**"Pairing failed".** keybond says why and tries again by itself when the keyboard answers.
Usually the fix is to put the keyboard back in pairing mode and type the code again.

**"Missing system library".** Install the two packages below and run it with the system
Python, not a virtualenv or conda one:

```
sudo apt install python3-dbus python3-gi
/usr/bin/python3 keybond.py
```

**Several keyboards nearby.** keybond lists them. Run it again with the one you want:

```
./keybond.py AA:BB:CC:DD:EE:FF
```

## A keyboard that was paired but will not connect

This is the other common trouble: the keyboard worked, and now it does nothing.

```
./keybond.py status
./keybond.py fix
```

`status` lists the keyboards paired with this computer and whether each is connected.

`fix` checks one of them. It mends what it can on the computer's side (a keyboard that is
not trusted cannot reconnect by itself), asks you to press a key to wake the keyboard, and
waits for it. Then it says what it found:

```
  Checking Convertible 2 TKL (AA:BB:CC:DD:EE:FF)

  ✓ Paired with this computer
  ✓ Trusted, so it may reconnect by itself

  Press any key on the keyboard now, to wake it.
  ✗ Still not connected

  This computer's side is fine. The keyboard is not answering.
    Is it switched on, with charge in its batteries?
    Is it on the slot it used with this computer?
    Is it connected to another computer, phone or tablet right now?
    Is it within a couple of metres?
    If none of that helps, pair it afresh:  keybond --again AA:BB:CC:DD:EE:FF
```

It also recognises a keyboard that has forgotten this computer, or is sitting in pairing
mode, and tells you to pair it again. `fix` never removes a pairing by itself.

## What you need

- Linux with BlueZ, the standard Bluetooth service (Ubuntu, Debian, Fedora and most others).
- Python 3. Ubuntu desktop already has everything else.
- Another keyboard to type the commands with: a laptop's built-in one, or a USB one.

No root, and nothing to install: keybond is a single file.

---

The rest is reference. Click a heading to open it.

<details>
<summary><b>Every message and what to do about it</b></summary>

| what you see | what it means | what to do |
|---|---|---|
| `No keyboard in pairing mode showed up` | nothing was found in time | see "Nothing is found" above |
| `Pairing failed (AuthenticationFailed)` | the code did not match, or Enter was not pressed | type the code again on the new keyboard, then Enter on it |
| `Pairing failed (AuthenticationCanceled)` | something else cancelled the pairing | close the desktop's Bluetooth settings window |
| `Pairing failed (AuthenticationRejected)` | the keyboard refused | clear the pairing slot on the keyboard |
| `Pairing failed (AuthenticationTimeout)` | the code was not typed in time | try again and type it promptly |
| `Pairing failed (ConnectionAttemptFailed)` | the keyboard stopped answering | put it back in pairing mode |
| `More than one keyboard is in pairing mode` | several were found | run again with an address |
| `… paired without asking for a code` | nothing proved which device answered | answer `y` only if you are sure it is yours |
| `Bluetooth is switched off` | the adapter is off | turn Bluetooth on |
| `Cannot reach the Bluetooth service` | the service is not running | `systemctl status bluetooth` |

keybond gives up after five real failures, or when the time runs out.

</details>

<details>
<summary><b>Install it as a command</b></summary>

Running `./keybond.py` from a clone needs no installation. To have a `keybond` command
available everywhere, install the clone with [pipx](https://pipx.pypa.io):

```
pipx install --system-site-packages .
keybond
```

`--system-site-packages` matters: it lets keybond see the D-Bus bindings that your
distribution provides (`python3-dbus`, `python3-gi`). keybond does not pull them in
through pip, because pip would have to compile them.

</details>

<details>
<summary><b>Options</b></summary>

| command | what it does |
|---|---|
| `keybond` | pair the one keyboard that is in pairing mode |
| `keybond AA:BB:CC:DD:EE:FF` | pair this keyboard |
| `keybond --again [address]` | remove the old pairing first, then pair afresh |
| `keybond status` | list the paired keyboards and their state |
| `keybond fix [address]` | find out why a paired keyboard will not connect |

| option | meaning |
|---|---|
| `--timeout SECONDS` | pairing: how long to wait for the keyboard (default 180) |
| `--wait SECONDS` | `fix`: how long to wait for the keyboard to answer (default 30) |
| `--adapter NAME` | which Bluetooth adapter to use, e.g. `hci0` (default: the first) |
| `--log FILE` | append a timestamped record of the attempt to `FILE` |
| `--plain` | no logo, large digits, colour or countdown. Automatic when output is not a terminal |
| `--help` | commands, options, and a short version of the steps |
| `--version` | print the version |

Press `Ctrl+C` to stop at any point.

Exit status: `0` paired or connected, `1` pairing failed or still not connected, `2` no
keyboard found (or more than one), `3` Bluetooth is off or unreachable.

</details>

<details>
<summary><b>Is it safe?</b></summary>

A paired, trusted keyboard can type anything on your computer, so it matters that the
device being paired is really yours.

- Typing the code on the keyboard is the proof. A device that cannot see your screen
  cannot type the code.
- If a device pairs without any code, or shows a code instead of taking one, keybond asks
  you before keeping it. Answering no removes it again.
- While it runs, keybond refuses pairing requests about any other device.
- Names sent by devices are stripped of control characters before they are shown.

</details>

<details>
<summary><b>How it works</b></summary>

keybond talks to the Bluetooth service (`bluetoothd`) over D-Bus:

1. registers its own pairing agent, so requests for a code come to it and not to the
   desktop;
2. scans, and waits for an unpaired keyboard that is visible right now;
3. calls `Pair` and displays the code the service hands to the agent;
4. sets `Trusted` and calls `Connect`.

On exit it stops the scan and unregisters the agent, so the desktop is back in charge. It
works around the vanishing window; it does not fix the desktop.

</details>

<details>
<summary><b>Reporting a pairing bug</b></summary>

A record of the attempt helps, whether you report to keybond or to your desktop's
maintainers:

```
./keybond.py --log pairing.log
```

The log has versions, your keyboard's name and address, each request from the Bluetooth
service, and the result. Other nearby devices are not recorded. It contains the pairing
code, which is useless once the attempt is over.

For the radio-level trace maintainers usually ask for, run this in a second terminal
during the attempt:

```
sudo btmon -w pairing.btsnoop
```

</details>

<details>
<summary><b>Status and tests</b></summary>

Early. On real hardware (Ubuntu 24.04, BlueZ 5.72): pairing a Filco Majestouch
Convertible 2 with old-style PIN pairing, and `fix` against a paired keyboard that was out
of range. Everything else is tested only against a stand-in Bluetooth service: the newer
passkey method, Bluetooth Low Energy keyboards, and the other failure paths. Reports from
other keyboards and distributions are welcome.

```
python3 -m unittest discover -s tests
```

`tests/test_keybond.py` covers the helpers. `tests/test_flow.py` runs the tool end to end against
`tests/fake_bluez.py`, a stand-in for the Bluetooth service on a private D-Bus, so no hardware
is touched. It takes about two minutes.

</details>

## License

MIT © Jiahong Dai
