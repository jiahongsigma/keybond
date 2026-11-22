"""End-to-end runs of the tool against fake_bluez.py on a private D-Bus.

No Bluetooth hardware is touched: dbus-run-session starts a throwaway bus and
DBUS_SYSTEM_BUS_ADDRESS points both programs at it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEV = "/org/bluez/hci0/dev_AA_BB_CC_00_00_01"

try:
    import dbus  # noqa: F401
    from gi.repository import GLib  # noqa: F401
    HAVE = shutil.which("dbus-run-session") is not None
except ImportError:
    HAVE = False

SCRIPT = r'''
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
"$PY" "$HERE/fake_bluez.py" & FAKE=$!
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    [ -s "$FAKE_STATE" ] && break; sleep 0.1
done
"$PY" "$ROOT/keybond.py" $TOOL_ARGS --plain < /dev/null; RC=$?
sleep 0.3; kill $FAKE 2>/dev/null
exit $RC
'''


@unittest.skipUnless(HAVE, "needs python3-dbus, python3-gi and dbus-run-session")
class Flow(unittest.TestCase):
    def play(self, scenario, args="--timeout 25", preset="", connect="ok"):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "state.json")
            env = dict(os.environ, FAKE_SCENARIO=scenario, FAKE_STATE=state, PY=sys.executable,
                       FAKE_PRESET=preset, FAKE_CONNECT=connect,
                       HERE=HERE, ROOT=ROOT, TOOL_ARGS=args)
            run = subprocess.run(["dbus-run-session", "--", "sh", "-c", SCRIPT], env=env,
                                 capture_output=True, text=True, timeout=120)
            with open(state, encoding="utf-8") as fh:
                return run.returncode, run.stdout + run.stderr, json.load(fh)

    def assert_clean_exit(self, world):
        self.assertFalse(world["agent"], "agent unregistered")
        self.assertFalse(world["discovering"], "scan stopped")

    def test_passkey_typed_on_the_keyboard(self):
        rc, out, world = self.play("passkey")
        self.assertEqual(rc, 0, out)
        self.assertIn("0 0 1 2 3 4", out, "leading zeros kept")
        self.assertEqual(out.count("then Enter"), 1, "code shown once, not per key")
        self.assertIn("●●●●●●", out)
        self.assertNotIn("old-style", out, "no caution for a modern pairing")
        dev = world["devices"][DEV]
        self.assertTrue(dev["Paired"] and dev["Trusted"] and dev["Connected"], dev)
        self.assertEqual(world["pair_calls"], 1)
        self.assert_clean_exit(world)

    def test_legacy_pin_shown_by_the_service(self):
        rc, out, world = self.play("legacy")
        self.assertEqual(rc, 0, out)
        self.assertIn("5 8 3 7 4 7", out)
        self.assertTrue(world["devices"][DEV]["Trusted"])
        self.assertIn("old-style PIN pairing", out)
        self.assertIn("a place you trust", out)
        self.assertLess(out.index("old-style PIN pairing"), out.index("5 8 3 7 4 7"),
                        "the caution comes before the code, while there is time to stop")

    def test_pin_requested_from_us(self):
        rc, out, world = self.play("request-pin")
        self.assertEqual(rc, 0, out)
        pin = [c for c in world["agent_calls"] if c.startswith("pin=")][0][4:]
        self.assertRegex(pin, r"^\d{6}$")
        self.assertIn(" ".join(pin), out, "the PIN we answered with is the one on screen")

    def test_address_given(self):
        rc, out, world = self.play("passkey", "--timeout 25 aa-bb-cc-00-00-01")
        self.assertEqual(rc, 0, out)
        self.assertTrue(world["devices"][DEV]["Paired"])

    def test_cancelled_once_then_succeeds(self):
        rc, out, world = self.play("cancel-then-ok")
        self.assertEqual(rc, 0, out)
        self.assertIn("AuthenticationCanceled", out)
        self.assertIn("Bluetooth settings window", out, "says what usually causes it")
        self.assertEqual(world["pair_calls"], 2)
        self.assertTrue(world["devices"][DEV]["Trusted"])

    def test_not_answering_is_retried_quietly(self):
        rc, out, world = self.play("unreachable-then-ok", "--timeout 40")
        self.assertEqual(rc, 0, out)
        self.assertEqual(world["pair_calls"], 3)
        self.assertEqual(out.count("Pairing failed"), 1, "reported once, not per retry")

    def test_wrong_code_every_time_gives_up(self):
        rc, out, world = self.play("always-wrong", "--timeout 60")
        self.assertEqual(rc, 1, out)
        self.assertEqual(world["pair_calls"], 5)
        self.assertFalse(world["devices"][DEV]["Trusted"])
        self.assert_clean_exit(world)

    def test_paired_without_a_code_is_not_kept_unasked(self):
        rc, out, world = self.play("justworks")
        self.assertEqual(rc, 1, out)
        self.assertIn("without asking for a code", out)
        self.assertEqual(world["removed"], [DEV], "the unproven pairing is removed again")

    def test_code_less_authorization_is_refused_without_a_terminal(self):
        rc, out, world = self.play("authorize", "--timeout 8")
        self.assertEqual(rc, 1, out)
        self.assertFalse(world["devices"][DEV]["Paired"])

    def test_code_shown_by_the_device_is_refused_without_a_terminal(self):
        rc, out, world = self.play("confirm", "--timeout 8")
        self.assertEqual(rc, 1, out)
        self.assertIn("424242", out)
        self.assertFalse(world["devices"][DEV]["Paired"])

    def test_request_about_another_device_is_refused(self):
        rc, out, world = self.play("wrong-device", "--timeout 8")
        self.assertEqual(rc, 1, out)
        self.assertNotIn("1 1 1 1 1 1", out, "another device's code is never displayed")
        self.assertFalse(world["devices"][DEV]["Paired"])

    def test_two_keyboards_asks_for_an_address(self):
        rc, out, world = self.play("two-keyboards")
        self.assertEqual(rc, 2, out)
        self.assertIn("AA:BB:CC:00:00:01", out)
        self.assertIn("AA:BB:CC:00:00:02", out)
        self.assertNotIn("Headset", out)
        self.assertEqual(world["pair_calls"], 0)

    def test_nothing_shows_up(self):
        rc, out, world = self.play("passkey", "--timeout 3 AA:BB:CC:00:00:77")
        self.assertEqual(rc, 2, out)
        self.assertEqual(world["pair_calls"], 0)
        self.assert_clean_exit(world)

    # -- nothing found: say what was seen --

    def test_nothing_found_names_what_was_seen(self):
        rc, out, world = self.play("only-others", "--timeout 3")
        self.assertEqual(rc, 2, out)
        self.assertIn("Headset (AA:BB:CC:00:00:09)", out)
        self.assertIn("keybond <address>", out)
        self.assertNotIn("AA:BB:CC:00:00:08", out, "unnamed devices are not listed")

    def test_nothing_found_points_at_an_already_paired_keyboard(self):
        rc, out, world = self.play("only-others", "--timeout 3", preset="paired")
        self.assertEqual(rc, 2, out)
        self.assertIn("Already paired here, so skipped: Fake Keyboard", out)
        self.assertIn("keybond --again", out)
        self.assertIn("keybond fix", out)

    # -- pairing again --

    def test_already_paired_says_how_to_go_on(self):
        rc, out, world = self.play("passkey", "AA:BB:CC:00:00:01", preset="paired")
        self.assertEqual(rc, 0, out)
        self.assertIn("already paired: not connected", out)
        self.assertIn("keybond fix AA:BB:CC:00:00:01", out)
        self.assertIn("keybond --again AA:BB:CC:00:00:01", out)
        self.assertEqual((world["pair_calls"], world["removed"]), (0, []))

    def test_again_removes_the_old_pairing_and_pairs_afresh(self):
        rc, out, world = self.play("passkey", "--again --timeout 25", preset="paired")
        self.assertEqual(rc, 0, out)
        self.assertIn("Removed the old pairing of Fake Keyboard", out)
        self.assertEqual(world["removed"], [DEV])
        self.assertEqual(world["pair_calls"], 1)
        self.assertTrue(world["devices"][DEV]["Trusted"])

    def test_again_with_two_paired_keyboards_removes_neither(self):
        rc, out, world = self.play("passkey", "--again --timeout 5", preset="paired,second")
        self.assertEqual(rc, 2, out)
        self.assertIn("Say which one", out)
        self.assertEqual(world["removed"], [])

    def test_again_with_nothing_paired_just_pairs(self):
        rc, out, world = self.play("passkey", "--again --timeout 25")
        self.assertEqual(rc, 0, out)
        self.assertEqual(world["removed"], [])

    # -- status --

    def test_status_lists_paired_keyboards(self):
        rc, out, world = self.play("passkey", "status", preset="paired,second")
        self.assertEqual(rc, 0, out)
        self.assertIn("Fake Keyboard (AA:BB:CC:00:00:01): not connected", out)
        self.assertIn("Other Keyboard (AA:BB:CC:00:00:02): not connected", out)
        self.assertIn("keybond fix", out)

    def test_status_and_fix_caution_about_old_style_keyboards(self):
        rc, out, world = self.play("passkey", "status", preset="paired,legacy")
        self.assertIn("Old-style PIN pairing: Fake Keyboard", out)
        rc, out, world = self.play("passkey", "fix --wait 6", preset="paired,legacy",
                                   connect="silent")
        self.assertEqual(rc, 1, out)
        self.assertIn("If you do pair it again: this keyboard uses old-style", out)
        rc, out, world = self.play("passkey", "status", preset="paired")
        self.assertNotIn("ld-style", out)

    def test_status_with_nothing_paired(self):
        rc, out, world = self.play("passkey", "status")
        self.assertEqual(rc, 0, out)
        self.assertIn("No keyboard is paired", out)

    # -- fix: paired but will not connect --

    def test_fix_reconnects_when_the_keyboard_wakes(self):
        rc, out, world = self.play("passkey", "fix --wait 15", preset="paired", connect="wakes")
        self.assertEqual(rc, 0, out)
        self.assertIn("is back", out)
        self.assertFalse(world["discovering"], "scan stopped")

    def test_fix_connects_straight_away_when_it_can(self):
        rc, out, world = self.play("passkey", "fix --wait 10", preset="paired")
        self.assertEqual(rc, 0, out)
        self.assertTrue(world["devices"][DEV]["Connected"])

    def test_fix_mends_a_keyboard_that_was_not_trusted(self):
        rc, out, world = self.play("passkey", "fix --wait 10", preset="paired,untrusted")
        self.assertEqual(rc, 0, out)
        self.assertIn("could not reconnect by itself", out)
        self.assertTrue(world["devices"][DEV]["Trusted"])

    def test_fix_says_the_keyboard_is_not_answering(self):
        rc, out, world = self.play("passkey", "fix --wait 6", preset="paired", connect="silent")
        self.assertEqual(rc, 1, out)
        self.assertIn("This computer's side is fine", out)
        self.assertIn("keybond --again AA:BB:CC:00:00:01", out)
        self.assertEqual(world["removed"], [], "fix never removes a pairing by itself")

    def test_fix_says_the_keyboard_forgot_the_pairing(self):
        rc, out, world = self.play("passkey", "fix --wait 6", preset="paired",
                                   connect="forgotten")
        self.assertEqual(rc, 1, out)
        self.assertIn("forgotten this computer", out)

    def test_fix_notices_a_keyboard_sitting_in_pairing_mode(self):
        rc, out, world = self.play("in-pairing-mode", "fix --wait 6", preset="paired",
                                   connect="silent")
        self.assertEqual(rc, 1, out)
        self.assertIn("is in pairing mode", out)

    def test_fix_with_two_keyboards_down_asks_which(self):
        rc, out, world = self.play("passkey", "fix --wait 5", preset="paired,second")
        self.assertEqual(rc, 2, out)
        self.assertIn("Say which one", out)

    def test_fix_of_a_keyboard_that_is_not_paired(self):
        rc, out, world = self.play("passkey", "fix AA:BB:CC:00:00:55 --wait 5")
        self.assertEqual(rc, 2, out)
        self.assertIn("is not paired with this computer", out)
        rc, out, world = self.play("passkey", "fix --wait 5")
        self.assertEqual(rc, 2, out)
        self.assertIn("No keyboard is paired", out)


if __name__ == "__main__":
    unittest.main()
