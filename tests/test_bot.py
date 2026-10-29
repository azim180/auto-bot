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


if __name__ == "__main__":
    unittest.main()
