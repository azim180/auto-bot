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

# cv2 stub (opencv-python)
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
        from collections import namedtuple
        from PIL import Image

        line = Image.open(bot.img_path("discord_server_returning_warn.png")).convert("RGB")
        if not warn_visible:
            bg = line.getpixel((95, 8))
            for x in range(80, line.width):
                for y in range(line.height):
                    line.putpixel((x, y), bg)
        screen = Image.new("RGB", (400, 200), line.getpixel((95, 8)))
        screen.paste(line, (100, 50))

        Box = namedtuple("Box", "left top width height")
        bot.pyautogui.locateOnScreen = lambda *a, **k: Box(100, 50, 80, 17)
        bot.pyautogui.screenshot = lambda region: screen.crop(
            (region[0], region[1], region[0] + region[2], region[1] + region[3]))
        return bot.has_returning_user_warning((0, 0, 400, 200))

    def test_check_and_warning_is_special_case(self):
        self.assertTrue(self._run(warn_visible=True))

    def test_check_only_is_normal_ticket(self):
        self.assertFalse(self._run(warn_visible=False))

    def test_server_line_not_found(self):
        bot.pyautogui.locateOnScreen = lambda *a, **k: None
        self.assertFalse(bot.has_returning_user_warning((0, 0, 400, 200)))


class TestValueChecks(unittest.TestCase):
    def test_phone_numbers(self):
        for text in ("0612345678", "+33 6 12 34 56 78", "06 12 34 56 78"):
            self.assertTrue(bot.looks_like_phone(text), text)
        for text in ("", "Number", "Number -> 0612345678", "12"):
            self.assertFalse(bot.looks_like_phone(text), text)

    def test_codes(self):
        for text in ("1234", "123456"):
            self.assertTrue(bot.looks_like_code(text), text)
        for text in ("", "12", "5 seconds ago", "Code"):
            self.assertFalse(bot.looks_like_code(text), text)


Point = __import__("collections").namedtuple("Point", "x y")


class TestCopyValueDoubleClick(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        self.clicks = []
        self.clipboard = []
        self._patchers = [
            mock.patch.object(bot, "human_pause", lambda *a, **k: None),
            mock.patch.object(bot, "wait_for_element", lambda *a, **k: Point(100, 200)),
            mock.patch.object(bot, "set_clipboard_text", lambda text: None),
            mock.patch.object(bot, "get_clipboard_text", lambda: self.clipboard.pop(0) if self.clipboard else ""),
            mock.patch.object(bot.pyautogui, "click", lambda *a, **k: self.clicks.append(k.get("clicks", 1))),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_double_clicks_the_number(self):
        self.clipboard = ["06 12 34 56 78"]
        result = bot.copy_value_next_to_label("discord_number_label.png", is_valid=bot.looks_like_phone)
        self.assertEqual(result, "06 12 34 56 78")
        self.assertEqual(self.clicks, [2])

    def test_retries_when_copied_text_is_not_a_number(self):
        self.clipboard = ["Number", "0612345678"]
        result = bot.copy_value_next_to_label("discord_number_label.png", is_valid=bot.looks_like_phone)
        self.assertEqual(result, "0612345678")
        self.assertEqual(self.clicks, [2, 2])


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


if __name__ == "__main__":
    unittest.main()
