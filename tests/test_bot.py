"""
Unit tests for bot.py — covers pure logic and configuration only.
Screen-dependent functions are tested against synthetic screenshots built from the images.
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
import tempfile

# Never write the real learned_spots.json, and start as a measured 100% screen
bot.SPOTS_FILE = os.path.join(tempfile.mkdtemp(), "learned_spots.json")
bot.scale_confirmed.update(bot.UI_GROUPS)


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

    def test_measured_spots_keys_present(self):
        expected = {
            "taskbar_discord_right", "taskbar_itunes",
            "itunes_menu_account", "itunes_manage_payments",
            "itunes_mobile_carrier", "itunes_phone_input_box",
            "itunes_submit_phone", "itunes_enter_code_box",
            "itunes_didnt_get_code", "itunes_submit_code",
        }
        self.assertEqual(expected, set(bot.MEASURED_SPOTS["1440x900@100"].keys()))

    def test_measured_spots_and_regions_fit_their_screen(self):
        for key, spots in list(bot.MEASURED_SPOTS.items()) + list(bot.MEASURED_TASKBAR_REGIONS.items()):
            width, height = (int(n) for n in key.split("@")[0].split("x"))
            for name, value in spots.items():
                corners = [value[:2]] if len(value) == 2 else [value[:2], (value[0] + value[2], value[1] + value[3])]
                for x, y in corners:
                    self.assertTrue(0 < x <= width and 0 < y <= height, f"{key} {name} {(x, y)} is off screen")

    def test_every_image_belongs_to_an_app(self):
        for name in os.listdir(bot.IMAGES_DIR):
            if name.endswith(".png"):
                self.assertIn(name.split("_")[0], ("discord", "itunes", "notif", "taskbar"), name)


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
        bot_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot.py")
        with open(bot_py, encoding="utf-8") as f:
            source = f.read()
        names = set(re.findall(r'"([a-z0-9_]+\.png)"', source)) - {"debug_dropdown.png"}
        self.assertTrue(names)
        missing = sorted(n for n in names if not os.path.isfile(bot.img_path(n)))
        self.assertEqual(missing, [])


class TestImageFilesExist(unittest.TestCase):
    """The taskbar and menu images that switching windows depends on must exist in images/."""
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


TIMESTAMP_BOX_RGB = (54, 54, 60)  # Discord's "17 seconds ago" highlight, measured from a screenshot


def _ticket_row(box_left=150, box_right=222, y=120, box_rgb=None):
    """A Discord embed row: embed background with the grey value box and some 'text' inside it."""
    from PIL import Image
    img = Image.new("RGB", (400, 200), (36, 36, 41))
    for x in range(box_left, box_right + 1):
        for yy in range(y - 6, y + 7):
            img.putpixel((x, yy), box_rgb or bot.VALUE_BOX_RGB)
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

    def test_timer_highlight_is_not_a_code_box(self):
        from unittest import mock
        timer_row = _ticket_row(box_rgb=TIMESTAMP_BOX_RGB)
        with mock.patch.object(bot.pyautogui, "screenshot", _fake_screenshot(timer_row), create=True):
            self.assertIsNone(bot.find_value_box(Point(111, 120)))

    def test_returns_none_without_a_box(self):
        from unittest import mock
        from PIL import Image
        plain = Image.new("RGB", (400, 200), (36, 36, 41))
        with mock.patch.object(bot.pyautogui, "screenshot", _fake_screenshot(plain), create=True):
            self.assertIsNone(bot.find_value_box(Point(111, 120)))


class TestOtherDiscordTheme(unittest.TestCase):
    """Another Discord theme draws the value boxes in another colour: it is read from the number box."""
    THEMED_BOX = (52, 44, 38)

    def setUp(self):
        from unittest import mock
        patcher = mock.patch.object(bot, "value_box_rgb", bot.VALUE_BOX_RGB)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _on(self, row, fn):
        from unittest import mock
        with mock.patch.object(bot.pyautogui, "screenshot", _fake_screenshot(row), create=True), \
             mock.patch("builtins.print"):
            return fn()

    def test_the_code_box_is_found_after_reading_the_colour_from_the_number_box(self):
        themed = _ticket_row(box_rgb=self.THEMED_BOX)
        self.assertIsNone(self._on(themed, lambda: bot.find_value_box(Point(111, 120))))
        self._on(themed, lambda: bot.learn_value_box_color(Point(111, 120)))
        self.assertEqual(bot.value_box_rgb, self.THEMED_BOX)
        self.assertEqual(self._on(themed, lambda: bot.find_value_box(Point(111, 120))), (150, 222))

    def test_the_timer_is_still_not_taken_for_the_code(self):
        self._on(_ticket_row(box_rgb=self.THEMED_BOX), lambda: bot.learn_value_box_color(Point(111, 120)))
        timer_row = _ticket_row(box_rgb=TIMESTAMP_BOX_RGB)
        self.assertIsNone(self._on(timer_row, lambda: bot.find_value_box(Point(111, 120))))

    def test_nothing_learned_without_a_box(self):
        from PIL import Image
        plain = Image.new("RGB", (400, 200), (36, 36, 41))
        self._on(plain, lambda: bot.learn_value_box_color(Point(111, 120)))
        self.assertEqual(bot.value_box_rgb, bot.VALUE_BOX_RGB)

    def test_the_console_says_what_is_there(self):
        text = self._on(_ticket_row(box_rgb=self.THEMED_BOX), lambda: bot.describe_value_row(Point(111, 120)))
        self.assertIn(str(self.THEMED_BOX), text)


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
        self.assertEqual(self.clicks, [2, 1])  # double-click, then a click to clear the selection
        self.assertEqual(self.drags, [])
        self.assertLessEqual(abs(self.moves[0][0] - 186), 1)

    def test_double_click_copies_the_whole_number_without_dragging(self):
        self.clipboard = ["06\u00a012\u00a036\u00a054\u00a085"]
        number = bot.copy_ticket_value("discord_number_label.png", (0, 0, 400, 200), bot.extract_phone,
                                       bot.NUMBER_BOX_OFFSETS)
        self.assertEqual(number, "06 12 36 54 85")
        self.assertEqual(self.clicks, [2, 1])  # double-click, then a click to clear the selection
        self.assertEqual(self.drags, [])

    def test_bad_copy_retries_with_another_double_click(self):
        self.clipboard = ["Number", "06 12 36 54 85"]
        number = bot.copy_ticket_value("discord_number_label.png", (0, 0, 400, 200), bot.extract_phone,
                                       bot.NUMBER_BOX_OFFSETS)
        self.assertEqual(number, "06 12 36 54 85")
        self.assertEqual(self.clicks, [2, 1, 2, 1])
        self.assertEqual(self.drags, [])

    def test_code_is_not_clicked_while_the_timer_shows(self):
        from unittest import mock
        with mock.patch.object(bot, "find_value_box", lambda label: None):
            code = bot.copy_ticket_value("discord_code_label.png", (0, 0, 400, 200), bot.extract_code,
                                         bot.CODE_BOX_OFFSETS, require_box=True)
        self.assertEqual(code, "")
        self.assertEqual(self.clicks, [])

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
    def test_shared_screenshot_gives_the_same_answer(self):
        from PIL import Image
        button = Image.open(bot.img_path("itunes_add_payment_btn.png")).convert("RGB")
        screen = self._screen_with([(button, (1056, 377))])
        self.assertEqual(bot.locate_element("itunes_add_payment_btn.png", confidence=0.88, screen=screen),
                         self._locate(screen, "itunes_add_payment_btn.png", confidence=0.88))
        self.assertEqual(bot.locate_element("itunes_add_payment_btn.png", confidence=0.88, screen=screen,
                                            region=(1000, 300, 300, 200)),
                         bot.Point(1056 + button.width // 2, 377 + button.height // 2))

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

    def test_a_variant_cropped_on_another_pc_is_used_too(self):
        from PIL import Image
        # On the 1080p PC iTunes draws this link a few pixels wider: the 1440x900 crop scores 0.72 there
        variant = Image.open(bot.img_path("itunes_didnt_get_code_link@1080p.png")).convert("RGB")
        screen = Image.new("RGB", (1920, 1080), (255, 255, 255))
        screen.paste(variant, (693, 279))
        loc = bot.locate_element("itunes_didnt_get_code_link.png", confidence=0.80, screen=screen)
        self.assertEqual(loc, Point(693 + variant.width // 2, 279 + variant.height // 2))
        self.assertEqual(bot._variants("itunes_submit_btn.png"), ["itunes_submit_btn.png"])

    def test_nothing_found_returns_none(self):
        screen = self._screen_with([])
        self.assertIsNone(self._locate(screen, "itunes_add_payment_btn.png", confidence=0.88))

    def test_missing_image_returns_none(self):
        from unittest import mock
        screen = self._screen_with([])
        with mock.patch("builtins.print"):
            self.assertIsNone(self._locate(screen, "does_not_exist.png"))


class TestClipboard(unittest.TestCase):
    def test_uses_pyperclip_when_available(self):
        from unittest import mock
        fake = mock.Mock()
        fake.paste.return_value = "06 12 36 54 85"
        with mock.patch.object(bot, "pyperclip", fake):
            self.assertEqual(bot.get_clipboard_text(), "06 12 36 54 85")
            bot.set_clipboard_text("1122")
        fake.copy.assert_called_once_with("1122")

    def test_falls_back_when_pyperclip_fails(self):
        from unittest import mock
        fake = mock.Mock()
        fake.paste.side_effect = RuntimeError("clipboard busy")
        with mock.patch.object(bot, "pyperclip", fake):
            self.assertEqual(bot.get_clipboard_text(), "")  # the tkinter stub's clipboard is empty


FAKE_TICKET = types.SimpleNamespace(region=lambda: (0, 0, 400, 300), scrolled=0, back_to_bottom=lambda: None)


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
            self.assertEqual(bot.wait_for_user_code(FAKE_TICKET, timeout=5, previous_code="1122"), "4567")

    def test_waits_while_the_timer_shows_then_takes_the_code(self):
        from unittest import mock
        codes = ["", "", "1246"]  # "" = no code box yet (timer showing), so nothing was clicked
        with mock.patch.object(bot, "locate_element",
                               lambda name, **k: Point(100, 200) if name == "discord_mark_verified_btn.png" else None), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "wait_for_screen_settle", lambda *a, **k: True), \
             mock.patch.object(bot, "copy_ticket_value", lambda *a, **k: codes.pop(0)), \
             mock.patch.object(bot.time, "sleep", lambda s: None), \
             mock.patch("builtins.print"):
            self.assertEqual(bot.wait_for_user_code(FAKE_TICKET, timeout=5, previous_code="1122"), "1246")


@unittest.skipUnless(hasattr(sys.modules.get("cv2"), "matchTemplate"), "needs opencv")
class TestCloseNotifications(unittest.TestCase):
    """Notifications covering iTunes' Submit are closed by their X, also when they keep coming."""

    def _run(self, frames):
        from unittest import mock
        frames, clicks = list(frames), []
        last = frames[-1]
        with mock.patch.object(bot, "grab_screen", lambda: frames.pop(0) if frames else last), \
             mock.patch.object(bot, "wait_for_screen_settle", lambda *a, **k: True), \
             mock.patch.object(bot, "human_click", lambda x, y, **k: clicks.append((x, y))), \
             mock.patch.object(bot, "human_pause", lambda *a, **k: None), \
             mock.patch("builtins.print"):
            closed = bot.close_notifications()
        return closed, clicks

    def _screen(self, *placements):
        from PIL import Image
        screen = Image.new("RGB", (1440, 900), (43, 43, 43))
        for name, xy in placements:
            screen.paste(Image.open(bot.img_path(name)).convert("RGB"), xy)
        return screen

    def test_clicks_the_x_of_a_notification(self):
        from PIL import Image
        dots = Image.open(bot.img_path("notif_close_btn.png"))
        closed, clicks = self._run([self._screen(("notif_close_btn.png", (1346, 688))), self._screen()])
        self.assertEqual(closed, 1)
        self.assertEqual(clicks, [(1346 + dots.width // 2 + 20, 688 + dots.height // 2)])

    def test_uses_the_header_when_the_x_is_hidden(self):
        from PIL import Image
        header = Image.open(bot.img_path("notif_discord_header.png"))
        closed, clicks = self._run([self._screen(("notif_discord_header.png", (1072, 687))), self._screen()])
        self.assertEqual(closed, 1)
        self.assertEqual(clicks, [(1072 + header.width // 2 + 288, 687 + header.height // 2)])

    def test_keeps_closing_while_new_ones_pop_up(self):
        two = self._screen(("notif_close_btn.png", (1346, 688)), ("notif_close_btn.png", (1346, 500)))
        one = self._screen(("notif_close_btn.png", (1346, 500)))
        closed, clicks = self._run([two, one, self._screen()])
        self.assertEqual(closed, 2)

    def test_nothing_to_close(self):
        self.assertEqual(self._run([self._screen()]), (0, []))


class TestClickItunesSubmit(unittest.TestCase):
    def _run(self, found, notifications, discord_in_front, spot=None):
        from unittest import mock
        calls = []
        with mock.patch.object(bot, "close_notifications", lambda: calls.append("close")), \
             mock.patch.object(bot, "wait_for_element", lambda name, **k: found.pop(0)), \
             mock.patch.object(bot, "find_notification", lambda screen=None: notifications.pop(0)), \
             mock.patch.object(bot, "human_move", lambda x, y, **k: calls.append(("move", x, y))), \
             mock.patch.object(bot.pyautogui, "click", lambda *a, **k: calls.append("click")), \
             mock.patch.object(bot, "human_pause", lambda *a, **k: None), \
             mock.patch.object(bot, "wait_for_window", lambda name, timeout=4: discord_in_front.pop(0)), \
             mock.patch.object(bot, "get_active_window_title", lambda: "iTunes"), \
             mock.patch.object(bot, "switch_to_itunes", lambda: calls.append("back to iTunes")), \
             mock.patch.object(bot, "spot", lambda name: spot), \
             mock.patch.object(bot, "remember_spot", lambda *a: None), \
             mock.patch("builtins.print"):
            return bot.click_itunes_submit("itunes_submit_phone"), calls

    def test_single_click_when_nothing_gets_in_the_way(self):
        ok, calls = self._run([Point(5, 6)], [None], [False])
        self.assertTrue(ok)
        self.assertEqual(calls, ["close", ("move", 5, 6), "click"])

    def test_goes_back_to_itunes_when_a_notification_caught_the_click(self):
        ok, calls = self._run([Point(5, 6), Point(5, 6)], [None, None], [True, False])
        self.assertTrue(ok)
        self.assertEqual(calls, ["close", ("move", 5, 6), "click", "back to iTunes", "close", ("move", 5, 6), "click"])

    def test_closes_the_next_notification_instead_of_giving_up(self):
        # Submit hidden under a notification that slid in after the first one was closed
        ok, calls = self._run([None, Point(5, 6)], ["toast", None], [False])
        self.assertTrue(ok)
        self.assertEqual(calls, ["close", "close", ("move", 5, 6), "click"])

    def test_does_not_click_when_a_notification_slid_in_during_the_move(self):
        ok, calls = self._run([Point(5, 6), Point(5, 6)], ["toast", None], [False])
        self.assertTrue(ok)
        self.assertEqual(calls, ["close", ("move", 5, 6), "close", ("move", 5, 6), "click"])

    def test_remembered_spot_only_when_no_notification_is_showing(self):
        ok, calls = self._run([None], [None, None], [False], spot=(1207, 737))
        self.assertTrue(ok)
        self.assertEqual(calls, ["close", ("move", 1207, 737), "click"])

    def test_gives_up_without_a_spot(self):
        ok, calls = self._run([None, None], [None, None], [], spot=None)
        self.assertFalse(ok)
        self.assertNotIn("click", calls)


class _Desktop:
    """
    iTunes with its Submit button, and Windows notifications in the corner that come one after
    another: closing one makes the next slide in from the right `arrive_after` seconds later.
    Time only moves when the bot waits, moves the mouse or pauses.
    """
    TOAST_XY = (1061, 676)    # covers the lower part of Submit, like the user's screenshot
    SUBMIT_XY = (1150, 668)

    def __init__(self, waiting, arrive_after=0.15, slide=0.3, arm_on_move=False):
        from PIL import Image

        def img(name):
            return Image.open(bot.img_path(name)).convert("RGB")

        self.toast = Image.new("RGB", (362, 150), (43, 43, 43))
        self.toast.paste(img("notif_discord_header.png"), (11, 11))
        self.toast.paste(img("notif_close_btn.png"), (285, 12))
        self.submit = img("itunes_submit_btn.png")
        self.now, self.mouse = 1000.0, (0, 0)
        self.toasts = [-1e9]                  # start times; the first one is already showing
        self.waiting, self.arrive_after, self.slide = waiting, arrive_after, slide
        self.arm_on_move = arm_on_move
        self.discord_front = self.submitted = False
        self.body_clicks = self.closed = 0

    def _toast_x(self, start):
        progress = min(1.0, max(0.0, (self.now - start) / self.slide))
        return int(self.TOAST_XY[0] + (1 - progress) * 380)

    def frame(self, region=None):
        from PIL import Image
        screen = Image.new("RGB", (1440, 900), (250, 250, 250))
        screen.paste(self.submit, self.SUBMIT_XY)
        for start in self.toasts:
            if self.now >= start:
                screen.paste(self.toast, (self._toast_x(start), self.TOAST_XY[1]))
        if region is None:
            return screen
        return screen.crop((region[0], region[1], region[0] + region[2], region[1] + region[3]))

    def sleep(self, seconds):
        self.now += seconds

    def move(self, x, y, **kwargs):
        sx, sy = self.SUBMIT_XY
        if self.arm_on_move and sx <= x <= sx + self.submit.width and sy <= y <= sy + self.submit.height:
            self.arm_on_move = False
            self.toasts.append(self.now + 0.05)  # pops up while the mouse is on its way
        self.now += 0.2
        self.mouse = (x, y)

    def click(self, *args, **kwargs):
        x, y = min(self.mouse[0], 1439), min(self.mouse[1], 899)  # Windows keeps the mouse on screen
        for start in [s for s in self.toasts if self.now >= s]:
            tx, ty = self._toast_x(start), self.TOAST_XY[1]
            if abs(x - (tx + 336)) <= 8 and abs(y - (ty + 21)) <= 8:
                self.toasts.remove(start)
                self.closed += 1
                if self.waiting:
                    self.waiting -= 1
                    self.toasts.append(self.now + self.arrive_after)
                return
            if tx <= x < tx + 362 and ty <= y < ty + 150:
                self.toasts.remove(start)
                self.body_clicks += 1
                self.discord_front = True  # clicking a notification opens Discord
                return
        sx, sy = self.SUBMIT_XY
        if sx <= x <= sx + self.submit.width and sy <= y <= sy + self.submit.height:
            self.submitted = True

    def patches(self, spot):
        from unittest import mock
        fake_time = types.SimpleNamespace(time=lambda: self.now, sleep=self.sleep)
        return [
            mock.patch.object(bot, "time", fake_time),
            mock.patch.object(bot.pyautogui, "screenshot", self.frame, create=True),
            mock.patch.object(bot.pyautogui, "size", lambda: (1440, 900), create=True),
            mock.patch.object(bot.pyautogui, "click", self.click, create=True),
            mock.patch.object(bot, "human_move", self.move),
            mock.patch.object(bot, "human_pause", lambda low=0.06, high=0.15: self.sleep(low)),
            mock.patch.object(bot, "get_active_window_title", lambda: "Discord" if self.discord_front else "iTunes"),
            mock.patch.object(bot, "wait_for_window",
                              lambda name, timeout=4: self.discord_front == (name == "Discord")),
            mock.patch.object(bot, "switch_to_itunes", lambda: setattr(self, "discord_front", False)),
            mock.patch.object(bot, "spot", lambda name: spot),
            mock.patch.object(bot, "remember_spot", lambda *a: None),
            mock.patch("builtins.print"),
        ]


@unittest.skipUnless(hasattr(sys.modules.get("cv2"), "matchTemplate"), "needs opencv")
class TestSubmitWhileNotificationsKeepComing(unittest.TestCase):
    """
    Regression: a notification covered iTunes' Submit, the bot closed it, and the next one slid in
    over Submit. The bot then gave up ("Could not find iTunes' Submit button") on screens without
    a backup spot, or clicked the backup spot - the notification - which opened Discord.
    """

    def _submit(self, desktop, spot=None):
        import contextlib
        with contextlib.ExitStack() as stack:
            for patch in desktop.patches(spot):
                stack.enter_context(patch)
            return bot.click_itunes_submit("itunes_submit_phone")

    def _check(self, desktop, spot=None):
        self.assertTrue(self._submit(desktop, spot))
        self.assertTrue(desktop.submitted)
        self.assertEqual(desktop.body_clicks, 0, "clicked a notification (opens Discord)")

    def test_three_notifications_in_a_row_without_a_backup_spot(self):
        desktop = _Desktop(waiting=2)
        self._check(desktop)
        self.assertEqual(desktop.closed, 3)

    def test_three_notifications_in_a_row_with_a_backup_spot(self):
        self._check(_Desktop(waiting=2), spot=(1204, 686))

    def test_slow_notifications_still_get_closed(self):
        self._check(_Desktop(waiting=2, arrive_after=1.0, slide=0.5))

    def test_next_notification_slides_in_just_after_the_corner_looked_clear(self):
        for arrive_after in (0.25, 0.3, 0.32, 0.35, 0.4, 0.45):
            for slide in (0.15, 0.3):
                with self.subTest(arrive_after=arrive_after, slide=slide):
                    for spot in (None, (1204, 686)):
                        self._check(_Desktop(waiting=1, arrive_after=arrive_after, slide=slide), spot)

    def test_notification_popping_up_while_the_mouse_moves_to_submit(self):
        desktop = _Desktop(waiting=0, arm_on_move=True)
        self._check(desktop)
        self.assertEqual(desktop.closed, 2)


class TestBackupSpots(unittest.TestCase):
    """Measured spots on 1440x900 at 100%; on any screen, where each button was last seen."""

    def setUp(self):
        from unittest import mock
        self.patches = [mock.patch.object(bot, "SPOTS_FILE", os.path.join(tempfile.mkdtemp(), "learned_spots.json")),
                        mock.patch.object(bot, "_spots", None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _on(self, size, fn, scale=1.0, extra=()):
        import contextlib
        from unittest import mock
        bot._spots = None
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(bot.pyautogui, "size", lambda: size, create=True))
            stack.enter_context(mock.patch.object(bot, "display_scale", lambda: scale))
            stack.enter_context(mock.patch.object(bot, "watch_screen", lambda: False))
            for p in extra:
                stack.enter_context(p)
            return fn()

    def test_measured_spots_only_on_1440x900_at_100(self):
        self.assertEqual(self._on((1440, 900), lambda: bot.spot("itunes_submit_phone")), (1207, 737))
        self.assertIsNone(self._on((1920, 1080), lambda: bot.spot("itunes_submit_phone")))
        self.assertIsNone(self._on((1440, 900), lambda: bot.spot("itunes_submit_phone"), scale=1.25))

    def test_found_buttons_are_remembered_for_this_screen(self):
        def learn_then_restart():
            bot.remember_spot("itunes_submit_phone", (1500, 800))
            bot._spots = None
            return bot.spot("itunes_submit_phone")
        self.assertEqual(self._on((1920, 1080), learn_then_restart), (1500, 800))
        self.assertIsNone(self._on((2560, 1440), lambda: bot.spot("itunes_submit_phone")))

    def test_click_element_uses_the_remembered_spot_when_the_image_is_missed(self):
        from unittest import mock
        clicks = []

        def click_twice():
            with mock.patch.object(bot, "locate_element", lambda *a, **k: Point(300, 200)):
                bot.click_element("itunes_manage_payments_link.png", spot_name="itunes_manage_payments")
            with mock.patch.object(bot, "locate_element", lambda *a, **k: None):
                bot.click_element("itunes_manage_payments_link.png", spot_name="itunes_manage_payments")

        self._on((1920, 1080), click_twice, extra=[
            mock.patch.object(bot, "human_click", lambda x, y, **k: clicks.append((x, y))),
            mock.patch("builtins.print"),
        ])
        self.assertEqual(clicks, [(300, 200), (300, 200)])

    def test_no_blind_click_when_the_taskbar_icon_was_never_seen(self):
        from unittest import mock
        self._on((1920, 1080), bot.switch_to_itunes, extra=[
            mock.patch.object(bot, "get_active_window_title", lambda: "Discord"),
            mock.patch.object(bot, "locate_element", lambda *a, **k: None),
            mock.patch.object(bot, "human_click", lambda *a, **k: self.fail("clicked a guessed spot")),
            mock.patch("builtins.print"),
        ])

    def test_taskbar_search_area(self):
        self.assertEqual(self._on((1440, 900), lambda: bot.taskbar_region("itunes")), (750, 845, 200, 55))
        self.assertEqual(self._on((1920, 1080), lambda: bot.taskbar_region("itunes")), (0, 1020, 1920, 60))


class TestBatchScripts(unittest.TestCase):
    """The .bat launchers must work on PCs where pip/python are not on PATH."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _read(self, name):
        with open(os.path.join(self.ROOT, name), "rb") as f:
            return f.read()

    def test_launchers_find_python_first_and_never_call_bare_pip_or_python(self):
        import re
        for name in ("install_requirements.bat", "start_bot.bat", "auto-pull.bat"):
            text = self._read(name).decode("ascii")
            self.assertIn('call "%~dp0find_python.bat"', text, name)
            for line in text.splitlines():
                self.assertIsNone(re.match(r"\s*(pip|python)\s", line, re.I), f"{name}: {line!r}")

    def test_installer_reports_failure_instead_of_success(self):
        text = self._read("install_requirements.bat").decode("ascii")
        self.assertIn("-m pip install -r requirements.txt\r\nif errorlevel 1 goto :failed", text)
        self.assertLess(text.index("goto :failed"), text.index("All packages installed!"))

    def test_batch_files_use_windows_line_endings(self):
        for name in ("find_python.bat", "install_requirements.bat", "start_bot.bat", "auto-pull.bat"):
            data = self._read(name)
            self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), f"{name} has Unix line endings")


@unittest.skipUnless(hasattr(sys.modules.get("cv2"), "matchTemplate"), "needs opencv")
class TestTicketTracking(unittest.TestCase):
    """The bot follows its own ticket by its number box, even after newer tickets push it up."""

    def _shot(self, screen):
        return lambda region=None: screen if region is None else screen.crop(
            (region[0], region[1], region[0] + region[2], region[1] + region[3]))

    def _number_box(self, screen, left, y, digits_seed):
        # grey value box with a digit-like pattern that differs per phone number
        import random as rnd
        rng = rnd.Random(digits_seed)
        for x in range(left, left + 73):
            for yy in range(y - 6, y + 7):
                screen.putpixel((x, yy), bot.VALUE_BOX_RGB)
        for x in range(left + 3, left + 70):
            for yy in range(y - 3, y + 4):
                if rng.random() < 0.35:
                    screen.putpixel((x, yy), (220, 220, 225))

    def _screen(self, boxes):
        from PIL import Image
        screen = Image.new("RGB", (1440, 900), (36, 36, 41))
        for left, y, seed in boxes:
            self._number_box(screen, left, y, seed)
        return screen

    def test_finds_its_own_ticket_after_a_new_one_pushes_it_up(self):
        from unittest import mock
        before = self._screen([(150, 700, "06 41 17 99 27")])
        with mock.patch.object(bot.pyautogui, "screenshot", self._shot(before), create=True):
            ticket = bot.Ticket(150, 222, 700)
        # a newer ticket (different number) arrives below and pushes ours up by 260px
        after = self._screen([(150, 440, "06 41 17 99 27"), (150, 700, "07 12 34 56 78")])
        with mock.patch.object(bot.pyautogui, "screenshot", self._shot(after), create=True), \
             mock.patch.object(bot, "get_active_window_title", lambda: "Discord"):
            self.assertEqual(ticket.find(), bot.Point(186, 440))
            region = ticket.region()
        self.assertTrue(region[1] <= 440 + 43 <= region[1] + region[3], "Code line must be inside the area")
        self.assertLess(region[1] + region[3], 700, "the newer ticket's lines must stay outside the area")


class TestTicketScrolling(unittest.TestCase):
    def test_scrolls_up_until_found_then_back_down(self):
        from unittest import mock
        scrolls = []
        found = [None, None, bot.Point(186, 120)]
        ticket = bot.Ticket.__new__(bot.Ticket)
        ticket.fingerprint, ticket.center, ticket.scrolled, ticket.server = object(), bot.Point(186, 500), 0, None
        with mock.patch.object(bot, "locate_template", lambda *a, **k: found.pop(0)), \
             mock.patch.object(bot, "get_active_window_title", lambda: "Discord"), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "human_move", lambda *a, **k: None), \
             mock.patch.object(bot, "human_pause", lambda *a, **k: None), \
             mock.patch.object(bot.pyautogui, "scroll", lambda n: scrolls.append(n)), \
             mock.patch.object(bot.time, "sleep", lambda s: None), \
             mock.patch("builtins.print"):
            self.assertEqual(ticket.find(), bot.Point(186, 120))
            self.assertEqual(ticket.scrolled, 6)
            self.assertEqual(scrolls, [120] * 6)
            ticket.back_to_bottom()
        self.assertEqual(scrolls[6:], [-120] * (6 + 15))
        self.assertEqual(ticket.scrolled, 0)


class TestUserLeft(unittest.TestCase):
    def test_code_wait_stops_when_the_user_left(self):
        from unittest import mock
        with mock.patch.object(bot, "locate_element",
                               lambda name, **k: Point(120, 160) if name == "discord_code_left.png" else None), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "copy_ticket_value", lambda *a, **k: self.fail("must not copy")), \
             mock.patch("builtins.print"):
            self.assertEqual(bot.wait_for_user_code(FAKE_TICKET, timeout=5), bot.USER_LEFT)

    def test_left_image_is_only_looked_for_in_this_tickets_area(self):
        from unittest import mock
        regions = []

        def fake_locate(name, **kwargs):
            if name == "discord_code_left.png":
                regions.append(kwargs.get("region"))
            return None

        codes = ["1246"]
        with mock.patch.object(bot, "locate_element", fake_locate), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot.time, "sleep", lambda s: None), \
             mock.patch("builtins.print"):
            bot.wait_for_user_code(FAKE_TICKET, timeout=0.05)
        self.assertTrue(regions and all(r == (0, 0, 400, 300) for r in regions))
        del codes


class TestActionMenuInTicketArea(unittest.TestCase):
    def test_action_is_searched_in_the_given_area_not_the_newest_ticket(self):
        from unittest import mock
        calls = {}

        def fake_wait(image_name, **kwargs):
            calls[image_name] = kwargs
            return Point(100, 200)

        with mock.patch.object(bot, "wait_for_element", fake_wait), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "human_click", lambda *a, **k: None), \
             mock.patch.object(bot, "click_and_wait_for_update", lambda *a, **k: None):
            bot.select_discord_action_menu_item("discord_menu_resend_code.png", region=(10, 20, 300, 200))
        self.assertEqual(calls["discord_action_dropdown.png"].get("region"), (10, 20, 300, 200))
        self.assertFalse(calls["discord_action_dropdown.png"].get("pick_bottom"))


@unittest.skipUnless(hasattr(sys.modules.get("cv2"), "matchTemplate"), "needs opencv")
class TestAnySize(unittest.TestCase):
    """Images cropped at 100% are still found when Windows scaling or Discord's zoom draws things bigger."""

    def setUp(self):
        self.saved = dict(bot.ui_scale), set(bot.scale_confirmed)

    def tearDown(self):
        bot.ui_scale.update(self.saved[0])
        bot.scale_confirmed.clear()
        bot.scale_confirmed.update(self.saved[1])
        bot._scaled_templates.clear()
        bot._last_calibration.clear()
        bot._calibration_searches.clear()

    def _screen(self, scale, *placements):
        """A 1920x1080 screen with the images drawn `scale` times bigger, smoothly like real scaling."""
        from PIL import Image
        screen = Image.new("RGB", (1920, 1080), (49, 51, 56))
        for name, xy in placements:
            image = Image.open(bot.img_path(name)).convert("RGB")
            size = (round(image.width * scale), round(image.height * scale))
            screen.paste(image.resize(size, Image.LANCZOS), xy)
        return screen

    def _unmeasured(self, group, display=1.0):
        from unittest import mock
        bot.scale_confirmed.discard(group)
        bot._last_calibration.pop(group, None)
        bot.ui_scale[group] = display
        return mock.patch.object(bot, "display_scale", lambda: display)

    def test_distances_follow_each_apps_size(self):
        bot.ui_scale.update(discord=1.25, windows=1.5)
        self.assertEqual(bot.px(20), 25)
        self.assertEqual(bot.px(20, "windows"), 30)
        self.assertEqual(bot.screen_area_around(500, 500, left=100, up=100, right=100, down=100), (375, 375, 250, 250))

    def test_finds_a_button_drawn_at_125_percent(self):
        screen = self._screen(1.25, ("discord_claim_btn.png", (800, 500)))
        bot.ui_scale["discord"] = 1.25
        loc = bot.locate_element("discord_claim_btn.png", screen=screen)
        self.assertIsNotNone(loc)
        self.assertLessEqual(abs(loc.x - (800 + 45)), 2)
        self.assertLessEqual(abs(loc.y - (500 + 19)), 2)
        self.assertIsNotNone(bot.locate_element("discord_claim_btn.png", screen=screen, pick_bottom=True))

    def test_measures_discord_zoom_from_what_is_on_screen(self):
        screen = self._screen(1.1, ("discord_chat_input.png", (400, 1000)), ("discord_claim_btn.png", (700, 600)))
        with self._unmeasured("discord"), mock_print():
            self.assertTrue(bot.calibrate_scale("discord", screen))
        self.assertEqual(bot.ui_scale["discord"], 1.1)
        self.assertIsNotNone(bot.locate_element("discord_claim_btn.png", screen=screen))

    def test_windows_scaling_is_tried_first(self):
        screen = self._screen(1.25, ("taskbar_discord_right.png", (600, 1030)), ("taskbar_itunes.png", (700, 1030)))
        with self._unmeasured("windows", display=1.25), mock_print():
            self.assertTrue(bot.calibrate_scale("windows", screen, search=False))
        self.assertEqual(bot.ui_scale["windows"], 1.25)

    def test_a_window_still_opening_is_not_taken_as_its_size(self):
        from unittest import mock
        # Windows draws a window that is being opened smaller for a moment
        opening = self._screen(0.9, ("discord_chat_input.png", (400, 1000)), ("discord_claim_btn.png", (700, 600)))
        opened = self._screen(1.0, ("discord_chat_input.png", (400, 1000)), ("discord_claim_btn.png", (700, 600)))
        with self._unmeasured("discord"), mock_print(), \
             mock.patch.object(bot, "wait_for_screen_settle", lambda *a, **k: True), \
             mock.patch.object(bot, "grab_screen", lambda: opened):
            self.assertTrue(bot.calibrate_scale("discord", opening))
        self.assertEqual(bot.ui_scale["discord"], 1.0)

    def test_nothing_is_adopted_from_a_screen_without_the_app(self):
        with self._unmeasured("itunes"), mock_print():
            self.assertFalse(bot.calibrate_scale("itunes", self._screen(1.0)))
        self.assertEqual(bot.ui_scale["itunes"], 1.0)
        self.assertNotIn("itunes", bot.scale_confirmed)

    def test_a_failed_search_waits_before_trying_again(self):
        from unittest import mock
        with self._unmeasured("itunes"), mock_print():
            bot.calibrate_scale("itunes", self._screen(1.0))
            with mock.patch.object(bot, "grab_screen", lambda: self.fail("searched again right away")):
                self.assertFalse(bot.calibrate_scale("itunes"))

    def test_gives_up_measuring_after_a_few_searches(self):
        from unittest import mock
        with self._unmeasured("itunes"), mock_print():
            for _ in range(bot.MAX_CALIBRATION_SEARCHES):
                bot._last_calibration.clear()
                self.assertFalse(bot.calibrate_scale("itunes", self._screen(1.0)))
            bot._last_calibration.clear()
            with mock.patch.object(bot, "grab_screen", lambda: self.fail("kept searching")):
                self.assertFalse(bot.calibrate_scale("itunes"))

    def test_a_clear_match_at_the_current_size_needs_no_measuring(self):
        screen = self._screen(1.0, ("itunes_submit_btn.png", (900, 700)))
        with self._unmeasured("itunes"), mock_print():
            self.assertIsNotNone(bot.locate_element("itunes_submit_btn.png", screen=screen))
        self.assertIn("itunes", bot.scale_confirmed)

    def test_startup_check_reports_the_screen(self):
        from unittest import mock
        printed = []
        with mock.patch.object(bot, "display_scale", lambda: 1.25), \
             mock.patch.object(bot.pyautogui, "size", lambda: (1920, 1080), create=True), \
             mock.patch.object(bot, "grab_screen", lambda: self._screen(1.0)), \
             mock.patch.object(bot, "_spots", {}), \
             mock.patch("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a)))):
            bot.startup_check()
        text = "\n".join(printed)
        self.assertIn("1920x1080", text)
        self.assertIn("125%", text)
        self.assertIn("not on screen yet", text)
        self.assertEqual(bot.ui_scale["discord"], 1.25)


class _Clock:
    """Fake time for the bot: only moves when the bot sleeps (or a test says so)."""

    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def patch(self):
        from unittest import mock
        return mock.patch.object(bot, "time", types.SimpleNamespace(time=self.time, sleep=self.sleep))


class _WorkState(unittest.TestCase):
    """Starts each test with no ticket in hand and no verification goal."""

    def setUp(self):
        from unittest import mock
        self.work = bot.Work()
        patcher = mock.patch.object(bot, "work", self.work)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestOneTryWhileAnotherTicketWaits(_WorkState):
    """With another claimed ticket waiting, the current user gets 1 minute and one code."""

    def _wait(self, claim_at=None, timeout=120):
        from unittest import mock
        clock = _Clock()

        def sweep():
            if claim_at is not None and clock.now - 1000 >= claim_at and not self.work.waiting:
                self.work.waiting.append("next ticket")

        with clock.patch(), \
             mock.patch.object(bot, "locate_element", lambda *a, **k: None), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "watch_screen", lambda: False), \
             mock.patch.object(bot, "claim_new_tickets", sweep), \
             mock.patch("builtins.print"):
            code = bot.wait_for_user_code(FAKE_TICKET, timeout=timeout)
        return code, clock.now - 1000

    def test_waits_the_full_two_minutes_when_nobody_else_waits(self):
        code, waited = self._wait()
        self.assertIsNone(code)
        self.assertGreaterEqual(waited, 120)

    def test_gives_up_after_one_minute_when_another_ticket_waits(self):
        self.work.waiting.append("next ticket")
        code, waited = self._wait()
        self.assertIsNone(code)
        self.assertTrue(60 <= waited < 62, waited)

    def test_ticket_claimed_after_the_first_minute_ends_the_wait_at_once(self):
        code, waited = self._wait(claim_at=90)
        self.assertIsNone(code)
        self.assertTrue(90 <= waited < 95, waited)

    def _verify_with_wrong_code(self):
        """verify_with_itunes where the user's first code is wrong. Returns (result, what happened)."""
        from unittest import mock
        done = []
        ticket = types.SimpleNamespace(
            choose_action=lambda item: done.append(item) or True,
            click_button=lambda image, what, **k: done.append(image) or True)
        outcomes = ["itunes_enter_code_input.png", "itunes_unable_to_verify_code.png", None]
        with mock.patch.object(bot, "switch_to_itunes", lambda: None), \
             mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "claim_from_notification", lambda screen=None: False), \
             mock.patch.object(bot, "wait_for_element", lambda name, **k: Point(500, 300)), \
             mock.patch.object(bot, "human_click", lambda *a, **k: None), \
             mock.patch.object(bot, "replace_field_text", lambda text: None), \
             mock.patch.object(bot, "human_scroll", lambda n: None), \
             mock.patch.object(bot, "remember_spot", lambda *a: None), \
             mock.patch.object(bot, "spot", lambda name: (580, 300)), \
             mock.patch.object(bot, "click_itunes_submit", lambda name: True), \
             mock.patch.object(bot, "wait_for_any", lambda *a, **k: outcomes.pop(0)), \
             mock.patch.object(bot, "wait_for_user_code", lambda *a, **k: "1234" if not done else None), \
             mock.patch.object(bot, "click_element", lambda name, **k: done.append(name) or Point(1, 1)), \
             mock.patch.object(bot, "run_itunes_reset_cycle", lambda **k: done.append("reset iTunes")), \
             mock.patch("builtins.print"):
            return bot.verify_with_itunes(ticket, "06 12 36 54 85"), done

    def test_wrong_code_fails_at_once_when_another_ticket_waits(self):
        self.work.waiting.append("next ticket")
        ok, done = self._verify_with_wrong_code()
        self.assertFalse(ok)
        self.assertIn("discord_failed_verification_btn.png", done)
        self.assertNotIn("discord_menu_resend_code.png", done)
        self.assertNotIn("itunes_didnt_get_code_link.png", done)
        self.assertEqual(done[-1], "reset iTunes")

    def test_wrong_code_gets_a_resend_when_nobody_else_waits(self):
        ok, done = self._verify_with_wrong_code()
        self.assertFalse(ok)
        self.assertIn("itunes_didnt_get_code_link.png", done)
        self.assertIn("discord_menu_resend_code.png", done)
        self.assertNotIn("discord_failed_verification_btn.png", done)


class TestClaimingNewTickets(_WorkState):
    def _sweep(self, new_tickets, claim_shows=True):
        from unittest import mock
        new_tickets = list(new_tickets)
        with mock.patch.object(bot, "switch_to_discord", lambda: None), \
             mock.patch.object(bot, "locate_element", lambda name, **k: Point(300, 700) if claim_shows else None), \
             mock.patch.object(bot, "claim_ticket", lambda: new_tickets.pop(0) if new_tickets else None), \
             mock.patch("builtins.print"):
            return bot.claim_new_tickets()

    def test_claims_every_new_ticket_and_lines_them_up_oldest_first(self):
        self.work.waiting.append("A")
        # the newest ticket (lowest on screen) is claimed first
        self.assertEqual(self._sweep(["D", "C", "B"]), 3)
        self.assertEqual(list(self.work.waiting), ["A", "B", "C", "D"])

    def test_claims_no_more_than_the_verification_goal_needs(self):
        self.work.limit, self.work.verified, self.work.current = 3, 1, "current ticket"
        self._sweep(["C", "B", "A"])
        self.assertEqual(list(self.work.waiting), ["C"])

    def test_a_claim_that_does_not_go_through_is_not_retried_forever(self):
        self.assertEqual(self._sweep([None] * 50), 0)


class TestNewTicketWhileInItunes(_WorkState):
    """A new-ticket notification while working in iTunes: click it, claim, come back to iTunes."""
    SERVER_1, SERVER_2 = list(bot.SERVERS)

    def _run(self, toast, current="current ticket", back_to_itunes=True):
        from unittest import mock
        self.work.current = current
        steps = []
        with mock.patch.object(bot, "find_new_ticket_notification", lambda screen=None: toast), \
             mock.patch.object(bot, "current_server", self.SERVER_1), \
             mock.patch.object(bot, "human_click", lambda x, y, **k: steps.append(("click", x, y))), \
             mock.patch.object(bot, "wait_for_window", lambda name, timeout=4: True), \
             mock.patch.object(bot, "wait_for_element", lambda name, **k: Point(300, 700)), \
             mock.patch.object(bot, "claim_new_tickets", lambda: steps.append(("claim in", bot.current_server))), \
             mock.patch.object(bot, "switch_to_itunes", lambda: steps.append("back to iTunes")), \
             mock.patch("builtins.print"):
            return bot.claim_from_notification(back_to_itunes=back_to_itunes), steps

    def test_claims_then_goes_back_to_itunes(self):
        went, steps = self._run((Point(1300, 750), self.SERVER_2))
        self.assertTrue(went)
        self.assertEqual(steps, [("click", 1300, 750), ("claim in", self.SERVER_2), "back to iTunes"])

    def test_from_discord_it_stays_there(self):
        # waiting for a code in Discord: the current ticket itself goes back to its server
        went, steps = self._run((Point(1300, 750), self.SERVER_2), back_to_itunes=False)
        self.assertTrue(went)
        self.assertEqual(steps, [("click", 1300, 750), ("claim in", self.SERVER_2)])

    def test_nothing_happens_without_a_notification(self):
        self.assertEqual(self._run(None), (False, []))

    def test_left_alone_when_no_ticket_is_being_worked_on(self):
        self.assertEqual(self._run((Point(1300, 750), self.SERVER_2), current=None), (False, []))

    def test_itunes_wait_carries_on_after_claiming(self):
        from unittest import mock
        clock = _Clock()
        claims = [True]

        def claim(screen=None):
            if claims:
                clock.now += 5  # the trip to Discord and back
                return claims.pop()
            return False

        # iTunes shows the code form 12s in: past the 10s timeout, but 5s of it were spent claiming
        with clock.patch(), \
             mock.patch.object(bot, "grab_screen", lambda: None), \
             mock.patch.object(bot, "locate_element", lambda name, **k: Point(1, 1) if clock.now - 1000 >= 12 else None), \
             mock.patch.object(bot, "claim_from_notification", claim):
            self.assertEqual(bot.wait_for_any([("itunes_enter_code_input.png", 0.8)], timeout=10, watch_tickets=True),
                             "itunes_enter_code_input.png")


@unittest.skipUnless(hasattr(sys.modules.get("cv2"), "matchTemplate"), "needs opencv")
class TestChangingTheScreenWhileRunning(unittest.TestCase):
    def setUp(self):
        self.saved = dict(bot.ui_scale), set(bot.scale_confirmed), bot._screen_seen

    def tearDown(self):
        bot.ui_scale.update(self.saved[0])
        bot.scale_confirmed.clear()
        bot.scale_confirmed.update(self.saved[1])
        bot._screen_seen = self.saved[2]
        bot._spots = None
        for cache in (bot._scaled_templates, bot._last_calibration, bot._calibration_searches, bot._last_seen_ok):
            cache.clear()

    def test_new_resolution_or_scaling_is_noticed_and_everything_measured_again(self):
        from unittest import mock
        with mock.patch.object(bot.pyautogui, "size", lambda: (1440, 900), create=True), \
             mock.patch.object(bot, "display_scale", lambda: 1.0):
            bot._screen_seen = None
            self.assertFalse(bot.watch_screen())
        with mock.patch.object(bot.pyautogui, "size", lambda: (1920, 1080), create=True), \
             mock.patch.object(bot, "display_scale", lambda: 1.25), \
             mock.patch("builtins.print"):
            self.assertTrue(bot.watch_screen())
            self.assertFalse(bot.watch_screen())
        self.assertEqual(bot.scale_confirmed, set())
        self.assertEqual(bot.ui_scale["discord"], 1.25)
        self.assertIsNone(bot._spots)

    def test_discord_zoom_change_is_noticed(self):
        from unittest import mock
        from PIL import Image
        screen = Image.new("RGB", (1920, 1080), (49, 51, 56))
        for name, xy in (("discord_chat_input.png", (400, 1000)), ("discord_claim_btn.png", (700, 600))):
            image = Image.open(bot.img_path(name)).convert("RGB")
            screen.paste(image.resize((round(image.width * 1.1), round(image.height * 1.1)), Image.LANCZOS), xy)
        bot.ui_scale["discord"] = 1.0
        bot.scale_confirmed.add("discord")
        bot._last_seen_ok["discord"] = 0  # its images have not matched for a long time
        with mock.patch.object(bot, "display_scale", lambda: 1.0), mock.patch("builtins.print"):
            self.assertTrue(bot.recheck_scale("discord", screen))
        self.assertEqual(bot.ui_scale["discord"], 1.1)

    def test_no_extra_work_while_the_images_keep_matching(self):
        from unittest import mock
        bot.scale_confirmed.add("discord")
        bot._last_seen_ok["discord"] = bot.time.time()
        with mock.patch.object(bot, "grab_screen", lambda: self.fail("checked again too soon")):
            self.assertTrue(bot.recheck_scale("discord"))


@unittest.skipUnless(hasattr(sys.modules.get("cv2"), "matchTemplate"), "needs opencv")
class TestTwoServers(unittest.TestCase):
    """Tickets come from two servers; each ticket remembers its own and the bot goes back to it."""
    SERVER_1, SERVER_2 = list(bot.SERVERS)

    def _image(self, name):
        from PIL import Image
        return Image.open(bot.img_path(name)).convert("RGB")

    def _sidebar(self, bar_next_to=None, bar_height=32):
        """Discord's server list: server 1's icon, then server 2's; a white bar marks the open one."""
        from PIL import Image, ImageDraw
        screen = Image.new("RGB", (1440, 900), (49, 51, 56))
        draw = ImageDraw.Draw(screen)
        draw.rectangle((0, 0, 71, 899), fill=(18, 18, 20))
        centers = {self.SERVER_1: (36, 120), self.SERVER_2: (36, 170)}
        for server, (cx, cy) in centers.items():
            draw.rounded_rectangle((cx - 15, cy - 15, cx + 15, cy + 15), radius=8, fill=(240, 240, 240))
            icon = self._image(bot.SERVERS[server]["icon"])
            screen.paste(icon, (cx - icon.width // 2, cy - icon.height // 2))
        if bar_next_to:
            cy = centers[bar_next_to][1]
            draw.rectangle((0, cy - bar_height // 2, 3, cy + bar_height // 2), fill=(242, 243, 245))
        return screen, centers

    def test_notification_colour_tells_the_server(self):
        from PIL import Image
        for server in (self.SERVER_1, self.SERVER_2):
            screen = Image.new("RGB", (1440, 900), (40, 40, 40))
            screen.paste(self._image(bot.SERVERS[server]["notification"]), (1100, 760))
            loc, found = bot.find_new_ticket_notification(screen)
            self.assertEqual(found, server)

    def test_the_two_icons_are_never_mixed_up(self):
        from PIL import Image
        for server, other in ((self.SERVER_1, self.SERVER_2), (self.SERVER_2, self.SERVER_1)):
            screen = Image.new("RGB", (400, 300), (18, 18, 20))
            screen.paste(self._image(bot.SERVERS[other]["icon"]), (100, 100))
            self.assertIsNone(bot.locate_element(bot.SERVERS[server]["icon"],
                                                 confidence=bot.SERVER_ICON_CONFIDENCE, screen=screen))
            self.assertIsNotNone(bot.locate_element(bot.SERVERS[other]["icon"],
                                                    confidence=bot.SERVER_ICON_CONFIDENCE, screen=screen))

    def test_the_open_server_is_the_one_with_the_white_bar(self):
        for server in (self.SERVER_1, self.SERVER_2):
            screen, _ = self._sidebar(bar_next_to=server)
            self.assertEqual(bot.shown_server(screen), server)
        self.assertIsNone(bot.shown_server(self._sidebar()[0]))
        # a short bar only means unread messages (or the mouse is over it), not that it is open
        self.assertIsNone(bot.shown_server(self._sidebar(bar_next_to=self.SERVER_1, bar_height=8)[0]))

    def test_goes_to_a_server_by_clicking_its_icon_only_when_needed(self):
        from unittest import mock
        screen, centers = self._sidebar()
        clicks = []
        with mock.patch.object(bot.pyautogui, "screenshot", lambda region=None: screen if region is None else
                               screen.crop((region[0], region[1], region[0] + region[2], region[1] + region[3])),
                               create=True), \
             mock.patch.object(bot, "current_server", self.SERVER_1), \
             mock.patch.object(bot, "human_click", lambda x, y, **k: clicks.append((x, y))), \
             mock.patch.object(bot, "wait_for_screen_settle", lambda *a, **k: True), \
             mock.patch("builtins.print"):
            self.assertTrue(bot.go_to_server(self.SERVER_1))
            self.assertEqual(clicks, [])
            self.assertTrue(bot.go_to_server(self.SERVER_2))
            self.assertEqual(bot.current_server, self.SERVER_2)
        self.assertEqual(len(clicks), 1)
        self.assertLessEqual(abs(clicks[0][0] - centers[self.SERVER_2][0]), 2)
        self.assertLessEqual(abs(clicks[0][1] - centers[self.SERVER_2][1]), 2)

    def _find(self, ticket_server, tracked, shown, found):
        from unittest import mock
        ticket = bot.Ticket.__new__(bot.Ticket)
        ticket.fingerprint, ticket.center, ticket.scrolled, ticket.server = object(), Point(400, 500), 0, ticket_server
        trips = []
        with mock.patch.object(bot, "current_server", tracked), \
             mock.patch.object(bot, "get_active_window_title", lambda: "Discord"), \
             mock.patch.object(bot, "go_to_server", lambda s, force=False: trips.append((s, force)) or True), \
             mock.patch.object(bot, "shown_server", lambda screen=None: shown), \
             mock.patch.object(bot, "locate_template", lambda *a, **k: found.pop(0) if found else None), \
             mock.patch.object(bot, "human_move", lambda *a, **k: None), \
             mock.patch.object(bot, "human_pause", lambda *a, **k: None), \
             mock.patch.object(bot.time, "sleep", lambda s: None), \
             mock.patch("builtins.print"):
            return ticket.find(), trips

    def test_ticket_takes_the_bot_back_to_its_server(self):
        loc, trips = self._find(self.SERVER_1, tracked=self.SERVER_2, shown=None, found=[Point(400, 300)])
        self.assertEqual(loc, Point(400, 300))
        self.assertEqual(trips, [(self.SERVER_1, False)])

    def test_ticket_notices_discord_shows_the_other_server(self):
        loc, trips = self._find(self.SERVER_1, tracked=self.SERVER_1, shown=self.SERVER_2,
                                found=[None, Point(400, 300)])
        self.assertEqual(loc, Point(400, 300))
        self.assertEqual(trips, [(self.SERVER_1, False), (self.SERVER_1, True)])

    def test_ticket_without_a_server_works_as_before(self):
        loc, trips = self._find(None, tracked=None, shown=None, found=[Point(400, 300)])
        self.assertEqual(loc, Point(400, 300))
        self.assertEqual(trips, [(None, False)])

    def test_claimed_ticket_remembers_the_server_it_was_claimed_in(self):
        from unittest import mock
        found = {"discord_claim_btn.png": [Point(300, 700), Point(300, 700)], "discord_number_label.png": [Point(200, 600)]}
        with mock.patch.object(bot, "current_server", self.SERVER_2), \
             mock.patch.object(bot, "locate_element", lambda name, **k: (found.get(name) or [None]).pop(0)), \
             mock.patch.object(bot, "wait_for_element", lambda name, **k: (found.get(name) or [None]).pop(0)), \
             mock.patch.object(bot, "wait_for_screen_settle", lambda *a, **k: True), \
             mock.patch.object(bot, "has_returning_user_warning", lambda region: False), \
             mock.patch.object(bot, "human_click", lambda *a, **k: None), \
             mock.patch.object(bot, "wait_for_claim_to_register", lambda loc: Point(300, 700)), \
             mock.patch.object(bot, "find_value_box", lambda label: (238, 310)), \
             mock.patch.object(bot, "grab_bgr", lambda region: object()), \
             mock.patch.object(bot.Ticket, "has_user_left", lambda self: False), \
             mock.patch("builtins.print"):
            ticket = bot.claim_ticket()
        self.assertEqual(ticket.server, self.SERVER_2)


class TestDisplayScale(unittest.TestCase):
    """The scaling is read live from the main monitor, so a change while the bot runs is seen."""

    def _windll(self, monitor_dpi=None, system_dpi=None):
        import ctypes

        def get_dpi_for_monitor(monitor, kind, dpi_x, dpi_y):
            if monitor_dpi is None:
                raise OSError("no shcore")
            dpi_x._obj.value = dpi_y._obj.value = monitor_dpi
            return 0

        def get_dpi_for_system():
            if system_dpi is None:
                raise OSError("no GetDpiForSystem")
            return system_dpi

        def monitor_from_point(point, flags):
            return 12345

        # plain functions, so the bot can set ctypes' restype/argtypes on them like on the real ones
        user32 = types.SimpleNamespace(MonitorFromPoint=monitor_from_point, GetDpiForSystem=get_dpi_for_system)
        shcore = types.SimpleNamespace(GetDpiForMonitor=get_dpi_for_monitor)
        from unittest import mock
        return mock.patch.object(ctypes, "windll", types.SimpleNamespace(user32=user32, shcore=shcore), create=True)

    def test_reads_the_monitor_scaling_now(self):
        with self._windll(monitor_dpi=120, system_dpi=96):
            self.assertEqual(bot.display_scale(), 1.25)
        with self._windll(monitor_dpi=144, system_dpi=96):
            self.assertEqual(bot.display_scale(), 1.5)

    def test_older_windows_and_other_systems(self):
        with self._windll(monitor_dpi=None, system_dpi=120):
            self.assertEqual(bot.display_scale(), 1.25)
        with self._windll():
            self.assertEqual(bot.display_scale(), 1.0)


def mock_print():
    from unittest import mock
    return mock.patch("builtins.print")


if __name__ == "__main__":
    unittest.main()
