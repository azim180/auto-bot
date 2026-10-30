"""
Unit tests for bot.py — covers pure logic and configuration only.
Screen-dependent functions (locate_element, click_element, etc.) are not tested here
because they require a live 1440x900 display with Discord and iTunes open.
"""
import os
import sys
import types
import unittest

# ---------------------------------------------------------------------------
# Stub out Windows-only / GUI modules so tests run on any OS (including CI)
# ---------------------------------------------------------------------------
def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod

# pyautogui stub
_pag = _stub_module("pyautogui", FAILSAFE=True, PAUSE=0.25)
_pag.locateCenterOnScreen = lambda *a, **k: None
_pag.locateAllOnScreen   = lambda *a, **k: iter([])
_pag.click = lambda *a, **k: None
_pag.moveTo = lambda *a, **k: None
_pag.hotkey = lambda *a, **k: None
_pag.press  = lambda *a, **k: None
_pag.write  = lambda *a, **k: None
_pag.scroll = lambda *a, **k: None
_pag.dragTo = lambda *a, **k: None
_pag.center = lambda b: b
_pag.easeOutQuad = lambda n: n
_pag.position = lambda: (0, 0)
_pag.size = lambda: (1440, 900)

# cv2 stub (opencv-python) only where it is not installed; the matcher tests need the real one
import importlib.util
if importlib.util.find_spec("cv2") is None:
    _stub_module("cv2")

# tkinter stub
_tk = _stub_module("tkinter")
class _FakeTk:
    def withdraw(self): pass
    def clipboard_get(self): return ""
    def clipboard_clear(self): pass
    def clipboard_append(self, t): pass
    def update(self): pass
    def destroy(self): pass
_tk.Tk = _FakeTk
sys.modules["tkinter"] = _tk

# ctypes — provide a minimal windll stub so the import succeeds on Linux/Mac
import ctypes as _ctypes
if not hasattr(_ctypes, "windll"):
    _windll = types.SimpleNamespace(
        user32=types.SimpleNamespace(
            GetForegroundWindow=lambda: 0,
            GetWindowTextLengthW=lambda h: 0,
            GetWindowTextW=lambda h, b, n: None,
        )
    )
    _ctypes.windll = _windll

# Now import the real bot module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestConfiguration(unittest.TestCase):
    def test_confidence_in_range(self):
        self.assertGreater(bot.CONFIDENCE, 0)
        self.assertLessEqual(bot.CONFIDENCE, 1.0)

    def test_keep_alive_interval_positive(self):
        self.assertGreater(bot.KEEP_ALIVE_INTERVAL, 0)

    def test_code_wait_timeout_positive(self):
        self.assertGreater(bot.CODE_WAIT_TIMEOUT, 0)

    def test_coords_keys_present(self):
        expected = {
            "taskbar_discord_right", "taskbar_itunes",
            "itunes_menu_account", "itunes_manage_payments",
            "itunes_mobile_carrier", "itunes_phone_input_box",
            "itunes_submit_phone", "itunes_enter_code_box",
            "itunes_didnt_get_code", "itunes_submit_code",
        }
        self.assertEqual(expected, set(bot.COORDS_1440x900.keys()))

    def test_coords_are_2_tuples(self):
        for key, val in bot.COORDS_1440x900.items():
            self.assertEqual(len(val), 2, f"{key} should be (x, y)")

    def test_coords_within_1440x900(self):
        for key, (x, y) in bot.COORDS_1440x900.items():
            self.assertGreater(x, 0, f"{key} x must be > 0")
            self.assertLessEqual(x, 1440, f"{key} x must be <= 1440")
            self.assertGreater(y, 0, f"{key} y must be > 0")
            self.assertLessEqual(y, 900, f"{key} y must be <= 900")


class TestImgPath(unittest.TestCase):
    def test_returns_string(self):
        result = bot.img_path("discord_claim_btn.png")
        self.assertIsInstance(result, str)

    def test_ends_with_filename(self):
        result = bot.img_path("discord_claim_btn.png")
        self.assertTrue(result.endswith("discord_claim_btn.png"))

    def test_contains_images_dir(self):
        result = bot.img_path("test.png")
        self.assertIn("images", result)


class TestEveryReferencedImageExists(unittest.TestCase):
    def test_all_images_used_by_bot_are_in_images_folder(self):
        import re
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot.py")).read()
        names = set(re.findall(r'"([a-z0-9_]+\.png)"', source)) - {"debug_dropdown.png"}
        self.assertTrue(names)
        missing = sorted(n for n in names if not os.path.isfile(bot.img_path(n)))
        self.assertEqual(missing, [])


class TestImageFilesExist(unittest.TestCase):
    """Every image referenced in COORDS_1440x900 must exist in images/."""
    COORD_TO_FILE = {
        "taskbar_discord_right": "taskbar_discord_right.png",
        "taskbar_itunes":        "taskbar_itunes.png",
        "itunes_menu_account":   "itunes_menu_account.png",
    }

    def test_key_image_files_present(self):
        for coord_key, filename in self.COORD_TO_FILE.items():
            path = bot.img_path(filename)
            self.assertTrue(os.path.isfile(path), f"Missing image: {filename}")


class TestReturningUserWarning(unittest.TestCase):
    """✅⚠️ must trigger the special case; ✅ alone must not."""

    def _run(self, warn_visible):
        from PIL import Image

        line = Image.open(bot.img_path("discord_server_returning_warn.png")).convert("RGB")
        if not warn_visible:
            bg = line.getpixel((95, 8))
            for x in range(80, line.width):
                for y in range(line.height):
                    line.putpixel((x, y), bg)
        screen = Image.new("RGB", (400, 200), line.getpixel((95, 8)))
        screen.paste(line, (100, 50))

        from unittest import mock
        with mock.patch.object(bot, "locate_box", lambda *a, **k: (100, 50, 80, 17)), \
             mock.patch.object(bot.pyautogui, "screenshot", lambda region: screen.crop(
                 (region[0], region[1], region[0] + region[2], region[1] + region[3])), create=True):
            return bot.has_returning_user_warning((0, 0, 400, 200))

    def test_check_and_warning_is_special_case(self):
        self.assertTrue(self._run(warn_visible=True))

    def test_check_only_is_normal_ticket(self):
        self.assertFalse(self._run(warn_visible=False))

    def test_server_line_not_found(self):
        from unittest import mock
        with mock.patch.object(bot, "locate_box", lambda *a, **k: None):
            self.assertFalse(bot.has_returning_user_warning((0, 0, 400, 200)))


Point = __import__("collections").namedtuple("Point", "x y")


def _fake_screenshot(img):
    return lambda region=None, *a, **k: img.crop(
        (region[0], region[1], region[0] + region[2], region[1] + region[3]))


def _ticket_row(box_left=150, box_right=222, y=120):
    """A Discord embed row: embed background with the grey value box and some 'text' inside it."""
    from PIL import Image
    img = Image.new("RGB", (400, 200), (36, 36, 41))
    for x in range(box_left, box_right + 1):
        for yy in range(y - 6, y + 7):
            img.putpixel((x, yy), bot.VALUE_BOX_RGB)
    for x in range(box_left + 3, box_right - 3, 3):
        for yy in range(y - 3, y + 4):
            img.putpixel((x, yy), (220, 220, 225))
    return img


class TestValueExtraction(unittest.TestCase):
    def test_phone_numbers(self):
        cases = {
            "06 12 36 54 85": "06 12 36 54 85",
            " 06 12 36 54 85\n": "06 12 36 54 85",
            "Number \u2192 06 12 36 54 85": "06 12 36 54 85",
            "+33 6 12 34 56 78": "+33 6 12 34 56 78",
            "0612365485": "0612365485",
            "06\u00a012\u00a036\u00a054\u00a085": "06 12 36 54 85",
            "06\u202f12\u202f36\u202f54\u202f85": "06 12 36 54 85",
            "\u200b06 12 36 54 85\u200b": "06 12 36 54 85",
        }
        for text, expected in cases.items():
            self.assertEqual(bot.extract_phone(text), expected, text)
        for text in ("", "36", "06 12", "Number"):
            self.assertEqual(bot.extract_phone(text), "", text)

    def test_codes(self):
        for text in ("1122", " 1122 ", "Code \u2192 1122"):
            self.assertEqual(bot.extract_code(text), "1122", text)
        for text in ("", "12", "5 seconds ago", "Code"):
            self.assertEqual(bot.extract_code(text), "", text)


class TestFindValueBox(unittest.TestCase):
    def test_finds_the_box_right_of_the_label(self):
        from unittest import mock
        with mock.patch.object(bot.pyautogui, "screenshot", _fake_screenshot(_ticket_row()), create=True):
            self.assertEqual(bot.find_value_box(Point(111, 120)), (150, 222))

    def test_returns_none_without_a_box(self):
        from unittest import mock
        from PIL import Image
        plain = Image.new("RGB", (400, 200), (36, 36, 41))
        with mock.patch.object(bot.pyautogui, "screenshot", _fake_screenshot(plain), create=True):
            self.assertIsNone(bot.find_value_box(Point(111, 120)))


class TestCopyTicketValue(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        self.clicks, self.moves, self.drags, self.clipboard = [], [], [], []
        self._patchers = [
            mock.patch.object(bot, "human_pause", lambda *a, **k: None),
            mock.patch.object(bot, "wait_for_element", lambda *a, **k: Point(111, 120)),
            mock.patch.object(bot, "find_value_box", lambda label: (150, 222)),
            mock.patch.object(bot, "set_clipboard_text", lambda text: None),
            mock.patch.object(bot, "get_clipboard_text", lambda: self.clipboard.pop(0) if self.clipboard else ""),
            mock.patch.object(bot.pyautogui, "click", lambda *a, **k: self.clicks.append(k.get("clicks", 1))),
            mock.patch.object(bot.pyautogui, "moveTo", lambda x, y, **k: self.moves.append((x, y))),
            mock.patch.object(bot.pyautogui, "dragTo", lambda x, y, **k: self.drags.append((x, y))),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_double_clicks_the_middle_of_the_code_box(self):
        self.clipboard = ["1122"]
        code = bot.copy_ticket_value("discord_code_label.png", (0, 0, 400, 200), bot.extract_code,
                                     bot.CODE_BOX_OFFSETS)
        self.assertEqual(code, "1122")
        self.assertEqual(self.clicks, [2])
        self.assertEqual(self.drags, [])
        self.assertLessEqual(abs(self.moves[0][0] - 186), 1)

    def test_double_click_copies_the_whole_number_without_dragging(self):
        self.clipboard = ["06\u00a012\u00a036\u00a054\u00a085"]
        number = bot.copy_ticket_value("discord_number_label.png", (0, 0, 400, 200), bot.extract_phone,
                                       bot.NUMBER_BOX_OFFSETS)
        self.assertEqual(number, "06 12 36 54 85")
        self.assertEqual(self.clicks, [2])
        self.assertEqual(self.drags, [])

    def test_bad_copy_retries_with_another_double_click(self):
        self.clipboard = ["Number", "06 12 36 54 85"]
        number = bot.copy_ticket_value("discord_number_label.png", (0, 0, 400, 200), bot.extract_phone,
                                       bot.NUMBER_BOX_OFFSETS)
        self.assertEqual(number, "06 12 36 54 85")
        self.assertEqual(self.clicks, [2, 2])
        self.assertEqual(self.drags, [])

    def test_gives_up_with_empty_string(self):
        self.clipboard = ["36", "54"]
        number = bot.copy_ticket_value("discord_number_label.png", (0, 0, 400, 200), bot.extract_phone,
                                       bot.NUMBER_BOX_OFFSETS)
        self.assertEqual(number, "")


class TestWaitForClaim(unittest.TestCase):
    def test_returns_reject_once_claim_is_replaced(self):
        from unittest import mock
        polls = {"claim": 0}

        def fake_locate(name, **kwargs):
            if name == "discord_claim_btn.png":
                polls["claim"] += 1
                return Point(100, 200) if polls["claim"] <= 2 else None
            if name == "discord_reject_btn.png":
                return Point(220, 200) if polls["claim"] > 2 else None
            return None

        with mock.patch.object(bot, "locate_element", fake_locate), \
             mock.patch.object(bot, "wait_for_screen_settle", lambda *a, **k: True):
            self.assertEqual(bot.wait_for_claim_to_register(Point(100, 200), timeout=2), Point(220, 200))

    def test_none_when_claim_never_goes_away(self):
        from unittest import mock
        with mock.patch.object(bot, "locate_element",
                               lambda name, **k: Point(100, 200) if name == "discord_claim_btn.png" else None):
            self.assertIsNone(bot.wait_for_claim_to_register(Point(100, 200), timeout=0.3))


class TestNotificationOpensTicket(unittest.TestCase):
    def test_clicks_the_toast_and_waits_for_claim(self):
        from unittest import mock
        clicked = []
        with mock.patch.object(bot, "locate_element",
                               lambda name, **k: Point(1200, 760) if name == "notif_new_ticket_purple.png" else None), \
             mock.patch.object(bot, "human_click", lambda x, y, **k: clicked.append((x, y))), \
             mock.patch.object(bot, "wait_for_window", lambda *a, **k: True), \
             mock.patch.object(bot, "wait_for_element", lambda *a, **k: Point(100, 200)):
            self.assertTrue(bot.open_ticket_from_notification())
        self.assertEqual(clicked, [(1200, 760)])

    def test_nothing_happens_without_a_toast(self):
        from unittest import mock
        with mock.patch.object(bot, "locate_element", lambda *a, **k: None), \
             mock.patch.object(bot, "human_click", lambda *a, **k: self.fail("should not click")):
            self.assertFalse(bot.open_ticket_from_notification())


class TestResetCycleFromManagePayments(unittest.TestCase):
    def test_clicks_add_payment_directly_when_mobile_phone_is_listed(self):
        from unittest import mock
        visible = {"itunes_add_payment_btn.png", "itunes_mobile_phone_verified.png",
                   "itunes_mobile_carrier_icon.png", "itunes_phone_input.png"}
        clicked = []
        found = lambda name, **k: Point(1, 1) if name in visible else None
        with mock.patch.object(bot, "locate_element", found), \
             mock.patch.object(bot, "wait_for_element", found), \
             mock.patch.object(bot, "click_element", lambda name, **k: clicked.append(name) or Point(1, 1)), \
             mock.patch.object(bot, "switch_to_itunes", lambda: None), \
             mock.patch.object(bot, "human_pause", lambda *a, **k: None):
            bot.run_itunes_reset_cycle(return_to_discord=False)
        self.assertEqual(clicked, ["itunes_add_payment_btn.png", "itunes_mobile_carrier_icon.png"])


class TestVerificationLimit(unittest.TestCase):
    def test_from_command_line(self):
        from unittest import mock
        with mock.patch.object(sys, "argv", ["bot.py", "2"]):
            self.assertEqual(bot.ask_verification_limit(), 2)
        with mock.patch.object(sys, "argv", ["bot.py", "0"]):
            self.assertIsNone(bot.ask_verification_limit())

    def test_asks_until_a_number_or_blank(self):
        from unittest import mock
        with mock.patch.object(sys, "argv", ["bot.py"]), \
             mock.patch("builtins.input", side_effect=["abc", "3"]), \
             mock.patch("builtins.print"):
            self.assertEqual(bot.ask_verification_limit(), 3)
        with mock.patch.object(sys, "argv", ["bot.py"]), mock.patch("builtins.input", return_value=""):
            self.assertIsNone(bot.ask_verification_limit())


class TestWaitForDiscordUpdate(unittest.TestCase):
    def _frames(self, frames, then):
        frames = list(frames)
        return lambda region: frames.pop(0) if frames else then()

    def test_settles_once_screen_stops_changing(self):
        from unittest import mock
        with mock.patch.object(bot, "_grab", self._frames(["a", "b", "c"], lambda: "c")):
            self.assertTrue(bot.wait_for_screen_settle((0, 0, 1, 1), settle=0.05, timeout=1, interval=0.01))

    def test_does_not_settle_while_screen_keeps_changing(self):
        from unittest import mock
        counter = iter(range(10 ** 6))
        with mock.patch.object(bot, "_grab", lambda region: next(counter)):
            self.assertFalse(bot.wait_for_screen_settle((0, 0, 1, 1), settle=0.05, timeout=0.2, interval=0.01))

    def test_detects_change_after_click(self):
        from unittest import mock
        with mock.patch.object(bot, "_grab", self._frames(["a", "a"], lambda: "b")):
            self.assertTrue(bot.wait_for_screen_change((0, 0, 1, 1), "a", timeout=1, interval=0.01))
        with mock.patch.object(bot, "_grab", lambda region: "a"):
            self.assertFalse(bot.wait_for_screen_change((0, 0, 1, 1), "a", timeout=0.05, interval=0.01))


class TestActionMenuUsesNewestTicket(unittest.TestCase):
    def test_action_dropdown_is_searched_bottom_first(self):
        from unittest import mock
        calls = {}

        def fake_wait(image_name, **kwargs):
            calls[image_name] = kwargs
            return Point(100, 200)

        with mock.patch.object(bot, "wait_for_element", fake_wait), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "human_pause", lambda *a, **k: None), \
             mock.patch.object(bot, "human_click", lambda *a, **k: None), \
             mock.patch.object(bot, "click_and_wait_for_update", lambda *a, **k: None):
            self.assertTrue(bot.select_discord_action_menu_item("discord_menu_mark_verified.png"))
        self.assertTrue(calls["discord_action_dropdown.png"]["pick_bottom"])


@unittest.skipUnless(hasattr(sys.modules.get("cv2"), "matchTemplate"), "needs opencv")
class TestBestMatch(unittest.TestCase):
    """locate_element must return the best match, not the first lookalike in reading order."""

    def _screen_with(self, placements, size=(1440, 900), bg=(255, 255, 255)):
        from PIL import Image
        screen = Image.new("RGB", size, bg)
        for img, xy in placements:
            screen.paste(img, xy)
        return screen

    def _locate(self, screen, *args, **kwargs):
        from unittest import mock
        with mock.patch.object(bot.pyautogui, "screenshot", lambda region=None: screen if region is None else
                               screen.crop((region[0], region[1], region[0] + region[2], region[1] + region[3])),
                               create=True):
            return bot.locate_element(*args, **kwargs)

    def test_add_payment_button_beats_a_lookalike_higher_up(self):
        import numpy as np
        from PIL import Image
        button = Image.open(bot.img_path("itunes_add_payment_btn.png")).convert("RGB")
        rng = np.random.default_rng(0)
        noisy = np.clip(np.array(button, dtype=int) + rng.integers(-60, 60, (button.height, button.width, 3)), 0, 255)
        lookalike = Image.fromarray(noisy.astype("uint8"))
        screen = self._screen_with([(lookalike, (190, 360)), (button, (1056, 377))])
        loc = self._locate(screen, "itunes_add_payment_btn.png", confidence=0.5)
        self.assertEqual(loc, bot.Point(1056 + button.width // 2, 377 + button.height // 2))

    def test_pick_bottom_returns_the_lowest_copy(self):
        from PIL import Image
        reject = Image.open(bot.img_path("discord_reject_btn.png")).convert("RGB")
        screen = self._screen_with([(reject, (100, 100)), (reject, (100, 600))], bg=(49, 51, 56))
        loc = self._locate(screen, "discord_reject_btn.png", confidence=0.82, pick_bottom=True)
        self.assertEqual(loc, bot.Point(100 + reject.width // 2, 600 + reject.height // 2))

    def test_nothing_found_returns_none(self):
        screen = self._screen_with([])
        self.assertIsNone(self._locate(screen, "itunes_add_payment_btn.png", confidence=0.88))

    def test_missing_image_returns_none(self):
        from unittest import mock
        screen = self._screen_with([])
        with mock.patch("builtins.print"):
            self.assertIsNone(self._locate(screen, "does_not_exist.png"))


class TestSecondCodeIgnoresTheOldOne(unittest.TestCase):
    def test_waits_until_the_code_changes(self):
        from unittest import mock
        codes = ["1122", "1122", "4567"]
        with mock.patch.object(bot, "locate_element",
                               lambda name, **k: Point(100, 200) if name == "discord_mark_verified_btn.png" else None), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "wait_for_screen_settle", lambda *a, **k: True), \
             mock.patch.object(bot, "copy_ticket_value", lambda *a, **k: codes.pop(0)), \
             mock.patch.object(bot.time, "sleep", lambda s: None), \
             mock.patch("builtins.print"):
            self.assertEqual(bot.wait_for_user_code(timeout=5, previous_code="1122"), "4567")


if __name__ == "__main__":
    unittest.main()
