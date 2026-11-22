import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keybond as bkp  # noqa: E402

A = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"
B = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_02"
C = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_03"


def kbd(address, **extra):
    props = {"Address": address, "Icon": "input-keyboard", "Paired": False, "RSSI": -60}
    props.update(extra)
    return props


class NormalizeMac(unittest.TestCase):
    def test_accepts_lowercase_and_dashes(self):
        self.assertEqual(bkp.normalize_mac(" aa-bb-cc-dd-ee-ff "), "AA:BB:CC:DD:EE:FF")

    def test_rejects_garbage(self):
        for bad in ("", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", "AABBCCDDEEFF"):
            with self.assertRaises(ValueError):
                bkp.normalize_mac(bad)


class FormatCode(unittest.TestCase):
    def test_digits_are_spaced_and_boxed(self):
        text = bkp.format_code("583747")
        self.assertIn("5 8 3 7 4 7", text)
        self.assertIn("Enter", text)
        widths = {len(line) for line in text.splitlines()}
        self.assertEqual(len(widths), 1, "box edges line up")

    def test_keeps_leading_zeros(self):
        self.assertIn("0 0 1 2 3 4", bkp.format_code("001234"))


class BigCode(unittest.TestCase):
    def test_every_digit_has_five_rows_of_five(self):
        for digit, rows in bkp.FONT.items():
            self.assertEqual([len(r) for r in rows], [5] * 5, digit)
        self.assertEqual(len({rows for rows in bkp.FONT.values()}), 10, "digits differ")

    def test_frame_lines_up(self):
        text = bkp.big_code("0123456789")
        self.assertEqual(len({len(line) for line in text.splitlines()}), 1)
        self.assertEqual(len(text.splitlines()), 9)

    def test_falls_back_when_the_font_lacks_a_character(self):
        self.assertIsNone(bkp.big_code("12ab"))
        self.assertIsNone(bkp.big_code(""))
        self.assertIn("1 2 a b", bkp.render_code("12ab", fancy=True))

    def test_plain_never_uses_big_digits(self):
        self.assertEqual(bkp.render_code("123456", fancy=False), bkp.format_code("123456"))
        self.assertIn("█", bkp.render_code("123456", fancy=True))

    def test_progress_dots(self):
        self.assertEqual(bkp.progress(0), "○○○○○○")
        self.assertEqual(bkp.progress(2), "●●○○○○")
        self.assertEqual(bkp.progress(99), "●●●●●●")


class Logo(unittest.TestCase):
    def test_letters_are_five_by_five_and_spell_the_name(self):
        for letter in "KEYBOND":
            self.assertEqual([len(r) for r in bkp.LOGO_GLYPHS[letter]], [5] * 5, letter)

    def test_logo_carries_version_brand_and_tagline(self):
        lines = bkp.logo().splitlines()
        self.assertEqual(len(lines), 7)
        self.assertTrue(all("█" in line for line in lines[:5]))
        self.assertIn(bkp.__version__, lines[-1])
        self.assertIn("Jdai Tool", lines[-1])


class ScreenLog(unittest.TestCase):
    def test_colour_never_reaches_the_log(self):
        import contextlib, io
        notes = []
        screen = bkp.Screen(True, True, notes.append)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            screen.ok("Paired")
        self.assertIn("\033[32m", out.getvalue())
        self.assertEqual(notes, ["✓ Paired"])


class NotFound(unittest.TestCase):
    def test_lists_named_non_keyboards_but_keeps_them_out_of_the_log(self):
        devices = {A: {"Address": "AA:BB:CC:DD:EE:01", "Name": "Headset", "RSSI": -50},
                   B: {"Address": "AA:BB:CC:DD:EE:02", "Alias": "AA-BB", "RSSI": -70}}
        lines = bkp.explain_not_found(devices, set())
        shown = [text for text, _ in lines]
        self.assertTrue(any("Headset (AA:BB:CC:DD:EE:01)" in t for t in shown))
        self.assertFalse(any("AA:BB:CC:DD:EE:02" in t for t in shown), "unnamed: not listed")
        for text, loggable in lines:
            if "Headset" in text:
                self.assertFalse(loggable)

    def test_points_at_paired_keyboards(self):
        devices = {A: kbd("AA:BB:CC:DD:EE:01", Paired=True, Name="Mine")}
        text = " ".join(t for t, _ in bkp.explain_not_found(devices, set()))
        self.assertIn("Already paired here, so skipped: Mine", text)
        self.assertIn("keybond --again", text)

    def test_target_not_seen(self):
        text = " ".join(t for t, _ in bkp.explain_not_found({}, set(), "AA:BB:CC:DD:EE:09"))
        self.assertIn("AA:BB:CC:DD:EE:09 was not seen", text)

    def test_nothing_at_all(self):
        text = " ".join(t for t, _ in bkp.explain_not_found({}, set()))
        self.assertIn("Nothing nearby", text)


class Paired(unittest.TestCase):
    def test_paired_keyboards_only(self):
        devices = {A: kbd("AA:BB:CC:DD:EE:01", Paired=True),
                   B: kbd("AA:BB:CC:DD:EE:02"),
                   C: {"Address": "AA:BB:CC:DD:EE:03", "Paired": True, "Icon": "input-mouse"}}
        self.assertEqual(bkp.paired_keyboards(devices), [A])
        self.assertEqual(bkp.find_by_address(devices, "AA:BB:CC:DD:EE:03"), C)
        self.assertIsNone(bkp.find_by_address(devices, "AA:BB:CC:DD:EE:99"))

    def test_state_words(self):
        self.assertEqual(bkp.state_words({"Connected": True, "Trusted": True}), "connected")
        words = bkp.state_words({"Connected": False, "Trusted": False, "Blocked": True})
        self.assertIn("not connected", words)
        self.assertIn("blocked", words)
        self.assertIn("will not reconnect by itself", words)


class ConnectVerdict(unittest.TestCase):
    def test_real_messages(self):
        failed = "org.bluez.Error.Failed"
        self.assertEqual(bkp.connect_verdict(failed, "br-connection-create-socket"), "silent")
        self.assertEqual(bkp.connect_verdict(failed, "br-connection-page-timeout"), "silent")
        self.assertEqual(bkp.connect_verdict(failed, "Host is down"), "silent")
        self.assertEqual(bkp.connect_verdict(failed, "br-connection-key-missing"), "forgotten")
        self.assertEqual(bkp.connect_verdict("org.bluez.Error.InProgress", ""), "busy")
        self.assertEqual(bkp.connect_verdict("org.bluez.Error.NotReady", ""), "off")
        self.assertEqual(bkp.connect_verdict(failed, "something new"), "unknown")


class Commands(unittest.TestCase):
    def test_command_comes_first_and_defaults_to_pair(self):
        self.assertEqual(bkp.split_command(["status"]), ("status", []))
        self.assertEqual(bkp.split_command(["fix", "--wait", "5"]), ("fix", ["--wait", "5"]))
        self.assertEqual(bkp.split_command([]), ("pair", []))
        self.assertEqual(bkp.split_command(["AA:BB:CC:DD:EE:FF"]), ("pair", ["AA:BB:CC:DD:EE:FF"]))
        self.assertEqual(bkp.split_command(["--again"]), ("pair", ["--again"]))

    def test_each_command_has_help(self):
        self.assertIn("--wait", bkp.build_parser("fix").format_help())
        self.assertIn("paired with this computer", bkp.build_parser("status").format_help())
        top = bkp.build_parser().format_help()
        for needle in ("keybond status", "keybond fix", "--again"):
            self.assertIn(needle, top)


class FailureKind(unittest.TestCase):
    def test_not_answering_is_not_a_real_failure(self):
        short, unreachable, hint = bkp.failure_kind("org.bluez.Error.ConnectionAttemptFailed")
        self.assertEqual((short, unreachable), ("ConnectionAttemptFailed", True))
        self.assertTrue(hint)

    def test_wrong_code_and_cancel_are_real_failures_with_hints(self):
        for name in ("AuthenticationFailed", "AuthenticationCanceled"):
            short, unreachable, hint = bkp.failure_kind("org.bluez.Error." + name)
            self.assertFalse(unreachable)
            self.assertTrue(hint)

    def test_unknown_error_has_no_hint(self):
        self.assertEqual(bkp.failure_kind("x.y.Weird"), ("Weird", False, None))


class Cli(unittest.TestCase):
    def test_help_explains_the_steps_and_exit_codes(self):
        text = bkp.build_parser().format_help()
        for needle in ("commands", "before you pair:", "exit status:", "--plain", "--log",
                       "Jdai Tool"):
            self.assertIn(needle, text)

    def test_timeout_must_be_positive(self):
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            bkp.positive_seconds("0")
        self.assertEqual(bkp.positive_seconds("30"), 30)

    def test_settings_detection_reads_process_names(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as proc:
            os.mkdir(os.path.join(proc, "123"))
            with open(os.path.join(proc, "123", "comm"), "w") as fh:
                fh.write("bash\n")
            self.assertFalse(bkp.settings_window_open(proc))
            with open(os.path.join(proc, "123", "comm"), "w") as fh:
                fh.write("gnome-control-c\n")
            self.assertTrue(bkp.settings_window_open(proc))


class Candidates(unittest.TestCase):
    def test_finds_the_one_live_keyboard(self):
        devices = {A: kbd("AA:BB:CC:DD:EE:01"),
                   B: {"Address": "AA:BB:CC:DD:EE:02", "Icon": "audio-headset", "RSSI": -50}}
        self.assertEqual(bkp.candidates(devices, set()), [A])

    def test_skips_paired_keyboards(self):
        devices = {A: kbd("AA:BB:CC:DD:EE:01", Paired=True)}
        self.assertEqual(bkp.candidates(devices, set()), [])

    def test_skips_remembered_but_not_visible(self):
        stale = kbd("AA:BB:CC:DD:EE:01")
        del stale["RSSI"]
        self.assertEqual(bkp.candidates({A: stale}, set()), [])
        self.assertEqual(bkp.candidates({A: stale}, {A}), [A], "newly announced counts as live")

    def test_target_matches_by_address_whatever_the_icon(self):
        devices = {A: kbd("AA:BB:CC:DD:EE:01"),
                   C: {"Address": "AA:BB:CC:DD:EE:03", "Paired": False, "RSSI": -70}}
        self.assertEqual(bkp.candidates(devices, set(), "AA:BB:CC:DD:EE:03"), [C])

    def test_target_not_live_is_not_a_candidate(self):
        devices = {C: {"Address": "AA:BB:CC:DD:EE:03", "Paired": False}}
        self.assertEqual(bkp.candidates(devices, set(), "AA:BB:CC:DD:EE:03"), [])

    def test_two_keyboards_are_both_reported(self):
        devices = {A: kbd("AA:BB:CC:DD:EE:01"), B: kbd("AA:BB:CC:DD:EE:02")}
        self.assertEqual(bkp.candidates(devices, set()), [A, B])


class Describe(unittest.TestCase):
    def test_name_then_alias_then_placeholder(self):
        self.assertEqual(bkp.describe({"Name": "K", "Address": "X"}), "K (X)")
        self.assertEqual(bkp.describe({"Alias": "Al", "Address": "X"}), "Al (X)")
        self.assertEqual(bkp.describe({}), "unnamed device (?)")

    def test_device_supplied_names_cannot_carry_control_characters(self):
        text = bkp.describe({"Name": "kbd\x1b[2J\nPairing successful.\r", "Address": "X"})
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\n", text)
        self.assertNotIn("\r", text)

    def test_long_names_are_cut(self):
        self.assertLessEqual(len(bkp.clean("a" * 500)), 64)


class Ask(unittest.TestCase):
    def test_no_terminal_means_no(self):
        import io, sys
        old, sys.stdin = sys.stdin, io.StringIO("y\n")
        try:
            self.assertFalse(bkp.ask("ok?"))
        finally:
            sys.stdin = old


if __name__ == "__main__":
    unittest.main()
