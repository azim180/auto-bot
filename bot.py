import os
import re
import sys
import json
import math
import time
import random
import ctypes
import collections
import tkinter as tk


def _use_real_pixels():
    """
    Screenshots and clicks in real screen pixels at any display scaling, also after the scaling
    is changed while the bot runs (per-monitor DPI awareness). It must happen before pyautogui
    is imported, which would otherwise lock in the older mode that Windows rescales.
    """
    try:
        user32 = ctypes.windll.user32
    except AttributeError:
        return  # not Windows
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # per-monitor v2
            return
    except Exception:
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:  # per-monitor
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


_use_real_pixels()

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pyautogui  # noqa: E402

try:
    import pyperclip  # installed with pyautogui; talks to the Windows clipboard directly
except ImportError:
    pyperclip = None

Point = collections.namedtuple("Point", "x y")

# ==============================================================================
# CONFIGURATION (any screen resolution and Windows display scaling)
# ==============================================================================
pyautogui.FAILSAFE = True   # Slam mouse into any of the 4 screen corners to abort
pyautogui.PAUSE = 0.03      # Base pause; the human_* helpers add small randomized waits on top

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BOT_DIR, "images")
CONFIDENCE = 0.84
# The "Add Payment Method" label left of the Add Payment button scores ~0.81 against it
ADD_PAYMENT_CONFIDENCE = 0.88

# 10-minute timer (600 seconds) for the iTunes keep-alive cycle
KEEP_ALIVE_INTERVAL = 600
# 2-minute timer (120 seconds) waiting for the user's verification code
CODE_WAIT_TIMEOUT = 120
# While another claimed ticket is waiting its turn, the current user gets one try: no code within
# this long (1 minute), or a wrong code, and the ticket is failed so the next one can start
BUSY_CODE_TIMEOUT = 60

# Fallback "the embed finished updating" rule: unchanged for this long
EMBED_SETTLE_SECONDS = 0.35
# Longest wait for Discord to react to a button click
EMBED_UPDATE_TIMEOUT = 8

# Inline-code box behind the Number / Code values, and where it sits relative to the
# label's center when it cannot be detected (measured on the ticket embed at 100% size).
# The colour depends on Discord's theme: it is read again from every claimed ticket's number box.
VALUE_BOX_RGB = (40, 41, 57)
NUMBER_BOX_OFFSETS = (38, 110)
CODE_BOX_OFFSETS = (31, 56)

# The two Discord servers tickets come from, each with a #code-farm. Each has its own icon in
# Discord's server list and its own new-ticket notification (server 1: green cash icon, blue/black
# notification; server 2: grey cash icon, purple notification). Every ticket remembers its server,
# so the bot can go back to it after claiming a ticket in the other one.
SERVERS = {
    "server 1 (green cash)": {"icon": "discord_server1_icon.png", "notification": "notif_new_ticket_blue.png"},
    "server 2 (grey cash)": {"icon": "discord_server2_icon.png", "notification": "notif_new_ticket_purple.png"},
}
# The two icons look alike from afar; only a close match is taken as one of them
SERVER_ICON_CONFIDENCE = 0.85

# Where a Windows notification's X is, from the center of its "⋯ ✕" image or its Discord header
NOTIF_CLOSE_FROM_DOTS = (20, 0)
NOTIF_CLOSE_FROM_HEADER = (288, 0)

# Backup click spots for when a button's image is not found. These were measured on a 1440x900
# screen at 100% scaling and are only used there; on any screen the bot also remembers where it
# last saw each button (in learned_spots.json) and uses that instead.
MEASURED_SPOTS = {
    "1440x900@100": {
        "taskbar_discord_right": (561, 878),
        "taskbar_itunes": (870, 878),
        "itunes_menu_account": (225, 53),
        "itunes_manage_payments": (1020, 288),
        "itunes_mobile_carrier": (730, 281),
        "itunes_phone_input_box": (535, 330),
        "itunes_submit_phone": (1207, 737),
        "itunes_enter_code_box": (535, 253),
        "itunes_didnt_get_code": (601, 299),
        "itunes_submit_code": (1221, 375),
    },
}
# Where the taskbar icons are searched on that same 1440x900 screen (elsewhere: the whole taskbar)
MEASURED_TASKBAR_REGIONS = {
    "1440x900@100": {"discord": (450, 845, 200, 55), "itunes": (750, 845, 200, 55)},
}
SPOTS_FILE = os.path.join(BOT_DIR, "learned_spots.json")

# The images were cropped at 100% display scaling. The screen resolution does not change how
# big buttons are drawn, but Windows display scaling and Discord's zoom do, so the bot measures
# each app's size from images that are always on screen while it is in front, and resizes the
# images to match.
UI_GROUPS = {"discord": "Discord", "itunes": "iTunes", "windows": "Taskbar/notifications"}
SCALE_ANCHORS = {
    "discord": ("discord_chat_input.png", "discord_claim_btn.png", "discord_action_dropdown.png"),
    "itunes": ("itunes_menu_account.png", "itunes_phone_input.png", "itunes_add_payment_btn.png",
               "itunes_submit_btn.png"),
    "windows": ("taskbar_discord_right.png", "taskbar_itunes.png"),
}
# Discord's zoom levels (Ctrl +/-), tried on top of the display scaling, nearest first
ZOOM_STEPS = (1.0, 0.9, 1.1, 0.8, 1.25, 0.75, 1.5, 0.67, 1.75, 0.5, 2.0)
# A resized image never matches quite as well as one cropped at that size
SCALED_CONFIDENCE_DROP = 0.03
# A size is only adopted when one of its app's anchor images matches at least this well there
SCALE_ADOPT_CONFIDENCE = 0.85
CALIBRATION_RETRY_SECONDS = 30
MAX_CALIBRATION_SEARCHES = 3  # then it stays at the display scaling
# An app whose images have not matched clearly for this long is checked again (zoom changed?)
RECHECK_SECONDS = 20

# Track the last time the iTunes Account -> Manage Payments -> Mobile Carrier cycle ran
last_itunes_cycle_time = time.time()
# The server Discord is showing, as far as the bot knows (it changes it itself: notifications, icons)
current_server = None


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def img_path(filename):
    return os.path.join(IMAGES_DIR, filename)


def screen_size():
    try:
        return tuple(pyautogui.size())
    except Exception:
        return (1440, 900)


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def display_scale():
    """The main screen's Windows display scaling right now (1.0 = 100%)."""
    try:
        user32, shcore = ctypes.windll.user32, ctypes.windll.shcore
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.MonitorFromPoint.argtypes = [_POINT, ctypes.c_uint]
        shcore.GetDpiForMonitor.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        monitor = user32.MonitorFromPoint(_POINT(0, 0), 1)  # the primary monitor
        dpi_x, dpi_y = ctypes.c_uint(), ctypes.c_uint()
        if shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0 and dpi_x.value:
            return dpi_x.value / 96.0
    except Exception:
        pass
    try:
        # Windows before 8.1: the scaling the user signed in with
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def screen_key():
    """This screen's resolution and display scaling, like "1920x1080@100"."""
    return "%dx%d@%d" % (*screen_size(), round(display_scale() * 100))


def taskbar_region(app):
    """Where to look for an app's taskbar icon: the measured area on 1440x900, else the whole taskbar."""
    region = MEASURED_TASKBAR_REGIONS.get(screen_key(), {}).get(app)
    if region:
        return region
    screen_w, screen_h = screen_size()
    height = min(screen_h, px(60, "windows"))
    return (0, screen_h - height, screen_w, height)


# ------------------------------------------------------------------------------
# Backup click spots: measured ones on 1440x900, plus where each button was last seen
# ------------------------------------------------------------------------------
_spots = None


def _read_spots_file():
    try:
        with open(SPOTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _known_spots():
    global _spots
    if _spots is None:
        _spots = {name: tuple(xy) for name, xy in MEASURED_SPOTS.get(screen_key(), {}).items()}
        try:
            learned = _read_spots_file().get(screen_key(), {})
            _spots.update({name: (int(xy[0]), int(xy[1])) for name, xy in learned.items()})
        except Exception:
            pass
    return _spots


def spot(name):
    """Backup click spot for `name` on this screen, or None if it was never seen here."""
    return _known_spots().get(name) if name else None


def remember_spot(name, loc):
    """Remembers where a button was found, so it can still be clicked if its image is missed later."""
    if not name or not loc:
        return
    spots = _known_spots()
    xy = (int(loc[0]), int(loc[1]))
    old = spots.get(name)
    if old and abs(old[0] - xy[0]) <= 3 and abs(old[1] - xy[1]) <= 3:
        return
    spots[name] = xy
    try:
        data = _read_spots_file()
        data.setdefault(screen_key(), {})[name] = list(xy)
        with open(SPOTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass


def get_active_window_title():
    """Returns the title of the currently active foreground window on Windows."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""


def get_clipboard_text():
    """Reads current text from the Windows clipboard."""
    if pyperclip:
        try:
            return pyperclip.paste() or ""
        except Exception:
            pass
    try:
        r = tk.Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        return text
    except Exception:
        return ""


def set_clipboard_text(text):
    """Writes text directly to the Windows clipboard ("" empties it)."""
    if pyperclip:
        try:
            pyperclip.copy(text)
            return
        except Exception:
            pass
    try:
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
    except Exception as e:
        print(f"[WARN] Clipboard write error: {e}")


def extract_phone(text):
    """Returns the phone number found in copied text (spaces kept), or "" if there is none."""
    # Discord separates the digit groups with non-breaking spaces; turn every kind of
    # space into a plain one and drop zero-width characters before matching
    text = re.sub(r"[​-‍⁠﻿]", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    for match in re.findall(r"\+?\d[\d \-.]*\d", text):
        if 8 <= len(re.sub(r"\D", "", match)) <= 15:
            return match.strip()
    return ""


def extract_code(text):
    match = re.search(r"(?<!\d)\d{4,8}(?!\d)", text)
    return match.group(0) if match else ""


def screen_area_around(x, y, left=120, up=220, right=260, down=40):
    """Screen area around a point on Discord; the distances are at 100% size."""
    try:
        screen_w, screen_h = pyautogui.size()
    except Exception:
        screen_w, screen_h = 1440, 900
    x0, y0 = max(0, int(x) - px(left)), max(0, int(y) - px(up))
    x1, y1 = min(screen_w, int(x) + px(right)), min(screen_h, int(y) + px(down))
    return (x0, y0, max(1, x1 - x0), max(1, y1 - y0))


# ==============================================================================
# FINDING IMAGES ON SCREEN (at whatever size each app is drawn)
# ==============================================================================
ui_scale = dict.fromkeys(UI_GROUPS, 1.0)  # how big each app is drawn, relative to the images
scale_confirmed = set()                    # apps whose size has been measured
_last_calibration = {}
_calibration_searches = collections.Counter()
_last_seen_ok = {}                         # when each app's images last matched clearly
_screen_seen = None                        # screen_key() the sizes were measured on
_templates = {}
_scaled_templates = {}


def group_of(image_name):
    """Which app an image belongs to; its size follows that app's zoom."""
    for group in ("discord", "itunes"):
        if image_name.startswith(group + "_"):
            return group
    return "windows"  # notif_* and taskbar_*


def px(n, group="discord"):
    """A distance measured at 100% size, at the size `group`'s app is drawn now."""
    return int(round(n * ui_scale[group]))


def reset_ui_scale():
    """Starts every app at Windows' display scaling until it is measured."""
    base = round(display_scale(), 3)
    for group in UI_GROUPS:
        ui_scale[group] = base
    scale_confirmed.clear()
    _last_calibration.clear()
    _calibration_searches.clear()
    _last_seen_ok.clear()
    _scaled_templates.clear()


def watch_screen():
    """
    Notices when the resolution or display scaling was changed while the bot runs: every app is
    then measured again, and the backup click spots of the new screen are used. True if it changed.
    """
    global _screen_seen, _spots
    key = screen_key()
    if _screen_seen is None:
        _screen_seen = key
    if key == _screen_seen:
        return False
    print(f"[SCREEN] Changed from {_screen_seen} to {key} - measuring every app again...")
    _screen_seen = key
    _spots = None
    reset_ui_scale()
    return True


def _load_template(image_name):
    if image_name not in _templates:
        path = img_path(image_name)
        if os.path.exists(path):
            # imdecode instead of imread so folders with non-ASCII names still work
            _templates[image_name] = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        else:
            print(f"[WARN] Missing image: images/{image_name}")
            _templates[image_name] = None
    return _templates[image_name]


def _bgr(image):
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _soften(img, scale):
    """Gray and slightly blurred: text drawn at another size then still matches a resized image."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    k = max(3, int(round(2 * scale)) | 1)
    return cv2.GaussianBlur(gray, (k, k), 0)


def _template_at(image_name, scale):
    """The image resized to `scale` (and softened); exactly as cropped at 100%."""
    key = (image_name, scale)
    if key not in _scaled_templates:
        template = _load_template(image_name)
        if template is not None and scale != 1.0:
            h, w = template.shape[:2]
            size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
            interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
            template = _soften(cv2.resize(template, size, interpolation=interpolation), scale)
        _scaled_templates[key] = template
    return _scaled_templates[key]


def _threshold(confidence, scale):
    return confidence - SCALED_CONFIDENCE_DROP if scale != 1.0 else confidence


def grab_screen():
    """One full screenshot that several locate_element(..., screen=...) calls can share."""
    try:
        return pyautogui.screenshot()
    except Exception:
        return None


_variant_names = {}


def _variants(image_name):
    """
    The image, plus look-alikes cropped on another PC (images/<name>@<anything>.png): text can be
    drawn a pixel wider there, enough to miss with the first crop.
    """
    if image_name not in _variant_names:
        stem = image_name[:-len(".png")]
        try:
            extra = sorted(f for f in os.listdir(IMAGES_DIR) if f.startswith(stem + "@") and f.endswith(".png"))
        except OSError:
            extra = []
        _variant_names[image_name] = [image_name] + extra
    return _variant_names[image_name]


def _match_scores(image_name, region=None, screen=None):
    """
    Template-matches an image (the best of its variants), at its app's current size, against the
    screen (or `region`): (scores, x0, y0, w, h, scale) or None.
    """
    scale = ui_scale[group_of(image_name)]
    names = _variants(image_name)
    if len(names) > 1 and screen is None:
        screen = grab_screen()  # one screenshot for all of them
    best = None
    for name in names:
        found = _match(_template_at(name, scale), region, screen, soften=scale if scale != 1.0 else None)
        if found is not None and (best is None or found[0].max() > best[0].max()):
            best = found
    return None if best is None else best + (scale,)


def _match(template, region=None, screen=None, soften=None):
    if template is None:
        return None
    if screen is not None:
        shot = screen.crop((region[0], region[1], region[0] + region[2], region[1] + region[3])) if region else screen
    else:
        shot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
    haystack = _bgr(shot)
    if soften:
        haystack = _soften(haystack, soften)
    h, w = template.shape[:2]
    if haystack.shape[0] < h or haystack.shape[1] < w:
        return None
    scores = np.nan_to_num(cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED), nan=0.0, posinf=0.0, neginf=0.0)
    x0, y0 = (int(region[0]), int(region[1])) if region else (0, 0)
    return scores, x0, y0, w, h


def _best_score(template, haystack):
    if template is None or haystack.shape[0] < template.shape[0] or haystack.shape[1] < template.shape[1]:
        return 0.0
    scores = np.nan_to_num(cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED), nan=0.0, posinf=0.0, neginf=0.0)
    return float(scores.max())


def _scale_candidates():
    """Display scaling first, then Discord's zoom steps on top of it."""
    base, candidates = display_scale(), []
    for zoom in ZOOM_STEPS:
        scale = round(base * zoom, 3)
        if scale not in candidates and 0.4 <= scale <= 3.0:
            candidates.append(scale)
    return candidates


def _anchor_score(group, scale, haystack, half=False, enough=1.0):
    """How well `group`'s best anchor image matches `haystack` at `scale` (stops once it is `enough`)."""
    best = 0.0
    size = scale / 2 if half else scale
    if size != 1.0:
        haystack = _soften(haystack, size)
    for name in SCALE_ANCHORS[group]:
        best = max(best, _best_score(_template_at(name, size), haystack))
        if best >= enough:
            break
    return best


def _still_screen():
    """
    A screenshot once the screen stopped changing. A window that is being opened (from the
    taskbar) is drawn smaller for a moment, which must not be measured as its size.
    """
    wait_for_screen_settle(None, settle=0.2, timeout=1.5, interval=0.05)
    return grab_screen()


def calibrate_scale(group, screen=None, search=True):
    """
    Measures how big `group`'s app is drawn, from images that are always on screen while it is in
    front: first at Windows' display scaling, then (with `search`) at Discord's zoom steps.
    True once the size is known. A search is tried at most every CALIBRATION_RETRY_SECONDS, and
    only MAX_CALIBRATION_SEARCHES times.
    """
    if group in scale_confirmed:
        return True
    if search:
        if _calibration_searches[group] >= MAX_CALIBRATION_SEARCHES:
            return False
        if time.time() - _last_calibration.get(group, -CALIBRATION_RETRY_SECONDS) < CALIBRATION_RETRY_SECONDS:
            return False
        _last_calibration[group] = time.time()
    screen = screen if screen is not None else _still_screen()
    if screen is None:
        return False
    haystack = _bgr(screen)
    candidates = _scale_candidates()
    expected = candidates[0]
    enough = _threshold(CONFIDENCE, expected)
    if _anchor_score(group, expected, haystack, enough=enough) >= enough:
        return _adopt_scale(group, expected)
    if not search:
        return False
    # Rank the other sizes on a half-size screenshot (4x faster), then check the best two properly
    small = cv2.resize(haystack, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    ranked = sorted(candidates[1:], key=lambda s: _anchor_score(group, s, small, half=True), reverse=True)
    best_score, best_scale = max((_anchor_score(group, s, haystack), s) for s in ranked[:2]) if ranked else (0, None)
    if best_score >= SCALE_ADOPT_CONFIDENCE:
        # Only a size seen twice is taken (a window still opening looks smaller at first)
        again = _still_screen()
        haystack = _bgr(again) if again is not None else haystack
        if _anchor_score(group, expected, haystack, enough=enough) >= enough:
            return _adopt_scale(group, expected)
        if _anchor_score(group, best_scale, haystack) >= SCALE_ADOPT_CONFIDENCE:
            return _adopt_scale(group, best_scale)
    _calibration_searches[group] += 1
    if _calibration_searches[group] == MAX_CALIBRATION_SEARCHES:
        print(f"[SCALE] Could not measure {UI_GROUPS[group]}'s size; keeping {ui_scale[group]:.0%}.")
    return False


def _note_match(image_name, score, scale):
    """A clear match at an app's current size proves that size is right: no need to measure it."""
    if score < 0.9:
        return
    group = group_of(image_name)
    _last_seen_ok[group] = time.time()
    if group not in scale_confirmed:
        _adopt_scale(group, scale)


def recheck_scale(group, screen=None):
    """
    Call while `group`'s app is in front. Measures it if that was not done yet; and when its
    images have not matched clearly for RECHECK_SECONDS (Discord's zoom may have been changed),
    checks its anchor images at the size it was measured at, and measures it again if they no
    longer match there. True while the size is known.
    """
    if group not in scale_confirmed:
        return calibrate_scale(group, screen)
    now = time.time()
    if now - _last_seen_ok.get(group, now) < RECHECK_SECONDS:
        return True
    _last_seen_ok[group] = now  # at most one check per RECHECK_SECONDS
    screen = screen if screen is not None else grab_screen()
    if screen is None:
        return True
    scale = ui_scale[group]
    enough = _threshold(CONFIDENCE, scale)
    if _anchor_score(group, scale, _bgr(screen), enough=enough) >= enough:
        return True
    # Look again once the screen is still: the window may have been opening a moment ago
    again = _still_screen()
    screen = again if again is not None else screen
    if _anchor_score(group, scale, _bgr(screen), enough=enough) >= enough:
        return True
    print(f"[SCALE] {UI_GROUPS[group]} no longer looks {scale:.0%} big - measuring it again...")
    scale_confirmed.discard(group)
    _calibration_searches[group] = 0
    _last_calibration.pop(group, None)
    return calibrate_scale(group, screen)


def _adopt_scale(group, scale):
    if ui_scale[group] != scale:
        _scaled_templates.clear()
    ui_scale[group] = scale
    scale_confirmed.add(group)
    _last_seen_ok[group] = time.time()
    print(f"[SCALE] {UI_GROUPS[group]} is drawn at {scale:.0%} size; images are matched at that size.")
    return True


def locate_box(image_name, confidence=CONFIDENCE, region=None, screen=None):
    """(left, top, width, height) of the best match on screen, or None below `confidence`."""
    try:
        found = _match_scores(image_name, region, screen)
    except Exception:
        return None
    if found is None:
        return None
    scores, x0, y0, w, h, scale = found
    _, best, _, (x, y) = cv2.minMaxLoc(scores)
    if best < _threshold(confidence, scale):
        return None
    _note_match(image_name, best, scale)
    return (x0 + int(x), y0 + int(y), w, h)


def locate_template(template, confidence, region=None, screen=None):
    """Center of the best match of an in-memory BGR image on screen, or None below `confidence`."""
    try:
        found = _match(template, region, screen)
    except Exception:
        return None
    if found is None:
        return None
    scores, x0, y0, w, h = found
    _, best, _, (x, y) = cv2.minMaxLoc(scores)
    return Point(x0 + int(x) + w // 2, y0 + int(y) + h // 2) if best >= confidence else None


def grab_bgr(region):
    try:
        return _bgr(pyautogui.screenshot(region=region))
    except Exception:
        return None


def locate_element(image_name, confidence=CONFIDENCE, region=None, pick_bottom=False, screen=None):
    """
    Finds an image on screen and returns the center of the BEST match. (pyautogui returns the
    first match above `confidence` in reading order, so a lookalike higher up the screen - like
    the "Add Payment Method" label next to the Add Payment button - could win.)
    If pick_bottom=True, picks the lowest match instead (newest Discord message).
    """
    if not pick_bottom:
        box = locate_box(image_name, confidence=confidence, region=region, screen=screen)
        return Point(box[0] + box[2] // 2, box[1] + box[3] // 2) if box else None
    try:
        found = _match_scores(image_name, region, screen)
    except Exception:
        return None
    if found is None:
        return None
    scores, x0, y0, w, h, scale = found
    ys, xs = np.where(scores >= _threshold(confidence, scale))
    if len(ys) == 0:
        return None
    # Best-scoring spot within the lowest match (matches spread over a few pixels)
    lowest = ys >= ys.max() - h // 2
    i = int(np.argmax(scores[ys[lowest], xs[lowest]]))
    x, y = int(xs[lowest][i]), int(ys[lowest][i])
    _note_match(image_name, float(scores[y, x]), scale)
    return Point(x0 + x + w // 2, y0 + y + h // 2)


def wait_for_element(image_name, timeout=10, confidence=CONFIDENCE, pick_bottom=False, region=None):
    """Waits up to `timeout` seconds for an image to appear and returns its center."""
    start = time.time()
    while time.time() - start < timeout:
        loc = locate_element(image_name, confidence=confidence, region=region, pick_bottom=pick_bottom)
        if loc:
            return loc
        time.sleep(0.1)
    return None


def wait_for_any(candidates, timeout=15, watch_tickets=False):
    """
    Waits for the first of several (image, confidence) pairs to appear; returns its image name.
    With `watch_tickets` (waiting in iTunes during a ticket), a new-ticket notification is claimed
    first and the wait carries on, with the time that took added to it.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        screen = grab_screen()
        for image_name, confidence in candidates:
            if locate_element(image_name, confidence=confidence, screen=screen):
                return image_name
        if watch_tickets:
            began = time.time()
            if claim_from_notification(screen):
                deadline += time.time() - began
                continue
        time.sleep(0.1)
    return None


# ==============================================================================
# HUMAN-LIKE INPUT
# ==============================================================================
def human_pause(low=0.06, high=0.15):
    time.sleep(random.uniform(low, high))


def human_move(x, y, jitter=2):
    """Glides to (x, y) with easing at a distance-based speed, landing a pixel or two off-center."""
    tx = int(x) + random.randint(-jitter, jitter)
    ty = int(y) + random.randint(-(jitter // 2), jitter // 2)
    try:
        cx, cy = pyautogui.position()
        distance = math.hypot(tx - cx, ty - cy)
    except Exception:
        distance = 500
    duration = min(0.35, 0.08 + distance / 4000) * random.uniform(0.9, 1.1)
    pyautogui.moveTo(tx, ty, duration=duration, tween=pyautogui.easeOutQuad)
    human_pause(0.02, 0.06)


def human_click(x, y, clicks=1, jitter=2):
    human_move(x, y, jitter=jitter)
    pyautogui.click(clicks=clicks, interval=random.uniform(0.06, 0.09))
    human_pause(0.05, 0.12)


def human_hotkey(*keys):
    pyautogui.hotkey(*keys, interval=random.uniform(0.02, 0.04))
    human_pause(0.04, 0.09)


def human_press(key):
    pyautogui.press(key)
    human_pause(0.03, 0.08)


def human_type(text):
    for ch in text:
        pyautogui.write(ch)
        time.sleep(random.uniform(0.03, 0.07))


def human_scroll(notches):
    """Scrolls one wheel notch at a time (120 units each); negative scrolls down."""
    step = -120 if notches < 0 else 120
    for _ in range(abs(notches)):
        pyautogui.scroll(step)
        time.sleep(random.uniform(0.02, 0.04))
    human_pause(0.12, 0.22)


def click_element(image_name, confidence=CONFIDENCE, region=None, pick_bottom=False, spot_name=None, timeout=0):
    """
    Finds (waiting up to `timeout`s) and clicks an image. With `spot_name`, where it was found is
    remembered, and if it is not found the remembered (or measured) spot is clicked instead.
    """
    if timeout:
        loc = wait_for_element(image_name, timeout=timeout, confidence=confidence, pick_bottom=pick_bottom, region=region)
    else:
        loc = locate_element(image_name, confidence=confidence, region=region, pick_bottom=pick_bottom)
    if loc:
        remember_spot(spot_name, loc)
        human_click(loc.x, loc.y)
        return loc
    backup = spot(spot_name)
    if backup:
        print(f"[INFO] {image_name} not found; clicking where it was before {backup}")
        human_click(*backup)
        return backup
    return None


def emptied_clipboard():
    """
    Empties the clipboard before copying. Returns what is still on it: normally "", but another
    program can keep it, and that old text (say the previous ticket's number) must not be taken
    for what is copied next.
    """
    set_clipboard_text("")
    return get_clipboard_text().strip()


def copy_selection(timeout=1.5, old=""):
    """Presses Ctrl+C, then waits for the copied text (not `old`, what was there before) on the clipboard."""
    human_hotkey("ctrl", "c")
    start = time.time()
    while time.time() - start < timeout:
        text = get_clipboard_text().strip()
        if text and text != old:
            return text
        time.sleep(0.05)
    return ""


def replace_field_text(text):
    """
    Clears the focused input and pastes `text`, then reads the field back (select all, copy) to make
    sure it holds `text` - not, say, the previous ticket's number. False if it still does not after
    a second paste; True also when the field cannot be read back.
    """
    wanted = re.sub(r"\D", "", text).lstrip("0")
    for attempt in (1, 2):
        human_hotkey("ctrl", "a")
        human_press("backspace")
        set_clipboard_text(text)
        human_hotkey("ctrl", "v")
        human_pause(0.08, 0.15)
        old = emptied_clipboard()
        human_hotkey("ctrl", "a")
        shown = copy_selection(timeout=0.8, old=old)
        human_press("end")  # unselect
        if not shown or not wanted or re.sub(r"\D", "", shown).lstrip("0") == wanted:
            return True
        print(f"[WARN] The field shows {shown!r} instead of {text!r} - pasting again (try {attempt}/2)")
    return False


# ==============================================================================
# WAITING FOR DISCORD TO UPDATE
# ==============================================================================
def _grab(region):
    try:
        return pyautogui.screenshot(region=region).tobytes()
    except Exception:
        return None


def wait_for_screen_change(region, before, timeout=EMBED_UPDATE_TIMEOUT, interval=0.1):
    start = time.time()
    while time.time() - start < timeout:
        now = _grab(region)
        if now is not None and now != before:
            return True
        time.sleep(interval)
    return False


def wait_for_screen_settle(region, settle=EMBED_SETTLE_SECONDS, timeout=EMBED_UPDATE_TIMEOUT, interval=0.1):
    """Waits until `region` has looked the same for `settle` seconds (Discord finished re-rendering)."""
    start = last_change = time.time()
    last = _grab(region)
    while time.time() - start < timeout:
        time.sleep(interval)
        now = _grab(region)
        if now != last:
            last, last_change = now, time.time()
        elif time.time() - last_change >= settle:
            return True
    return False


def click_and_wait_for_update(x, y, what, region=None):
    """Clicks a Discord button, then waits for the embed to react and finish updating."""
    region = region or screen_area_around(x, y)
    human_move(x, y)
    # Let the hover highlight finish so it is not mistaken for Discord's reply
    wait_for_screen_settle(region, settle=0.1, timeout=0.6, interval=0.04)
    before = _grab(region)
    pyautogui.click()
    if not wait_for_screen_change(region, before):
        print(f"[WARN] Discord did not react to {what} within {EMBED_UPDATE_TIMEOUT}s")
    elif not wait_for_screen_settle(region):
        print(f"[WARN] Discord kept changing after {what}; continuing anyway")


def wait_for_claim_to_register(claim_loc, timeout=EMBED_UPDATE_TIMEOUT):
    """
    After clicking Claim: waits until the Claim button is gone and Reject has appeared.
    Returns Reject's position (the old Claim spot if Reject was never seen),
    or None if the Claim button never went away.
    """
    area = screen_area_around(claim_loc.x, claim_loc.y, left=150, up=80, right=300, down=80)
    start = time.time()
    while time.time() - start < timeout:
        if locate_element("discord_claim_btn.png", confidence=CONFIDENCE, region=area) is None:
            reject = locate_element("discord_reject_btn.png", confidence=0.82, region=area)
            if reject:
                # The new buttons are in; give the embed text a moment to finish drawing
                wait_for_screen_settle(screen_area_around(reject.x, reject.y), settle=0.15, timeout=1.2, interval=0.05)
                return reject
        time.sleep(0.08)
    # The hovered Claim button can fall under the strict threshold, so double-check loosely
    if locate_element("discord_claim_btn.png", confidence=0.70, region=area):
        return None
    print("[WARN] Claim went through but the Reject button was not seen; continuing")
    return claim_loc


# ==============================================================================
# WINDOW SWITCHING (Right Discord Icon & iTunes)
# ==============================================================================
def wait_for_window(name, timeout=4):
    start = time.time()
    while time.time() - start < timeout:
        if name in get_active_window_title():
            return True
        time.sleep(0.05)
    return False


def _click_taskbar_icon(app, image_name, spot_name):
    """Clicks an app's taskbar icon. False if it cannot be found."""
    recheck_scale("windows")
    loc = locate_element(image_name, confidence=0.80, region=taskbar_region(app))
    if loc:
        remember_spot(spot_name, loc)
    target = loc or spot(spot_name)
    if not target:
        return False
    human_click(*target)
    return True


def switch_to_discord():
    """Brings the Right Discord instance to the foreground without minimizing it."""
    watch_screen()
    title = get_active_window_title()
    if "Discord" in title or locate_element("discord_chat_input.png", confidence=0.80):
        recheck_scale("discord")
        return
    print("[SWITCH] Clicking Right Discord icon on taskbar...")
    if not _click_taskbar_icon("discord", "taskbar_discord_right.png", "taskbar_discord_right"):
        print("[WARN] Could not find the Discord icon on the taskbar")
        return
    if not wait_for_window("Discord"):
        print("[WARN] Discord window did not come to the front")
    human_pause(0.12, 0.25)  # let it repaint
    recheck_scale("discord")


def switch_to_itunes():
    """Brings iTunes to the foreground from minimized/background state."""
    watch_screen()
    title = get_active_window_title()
    if "iTunes" in title or locate_element("itunes_menu_account.png", confidence=0.82):
        recheck_scale("itunes")
        return
    print("[SWITCH] Clicking iTunes icon on taskbar...")
    if not _click_taskbar_icon("itunes", "taskbar_itunes.png", "taskbar_itunes"):
        print("[WARN] Could not find the iTunes icon on the taskbar")
        return
    if not wait_for_window("iTunes"):
        print("[WARN] iTunes window did not come to the front")
    human_pause(0.15, 0.3)  # let it repaint
    recheck_scale("itunes")


# ==============================================================================
# DISCORD SERVERS (tickets come from two)
# ==============================================================================
def shown_server(screen=None):
    """
    Which of the two servers Discord is showing, from the white bar Discord draws left of the open
    server's icon in the server list. None if it cannot tell.
    """
    screen = screen if screen is not None else grab_screen()
    if screen is None:
        return None
    for server, images in SERVERS.items():
        box = locate_box(images["icon"], confidence=SERVER_ICON_CONFIDENCE, screen=screen)
        if box and _has_open_server_bar(screen, box):
            return server
    return None


def _has_open_server_bar(screen, box):
    """True if a tall white bar (the open server's) is left of the icon whose inner part is at `box`."""
    left, top, width, height = box
    cx, cy = left + width // 2, top + height // 2
    half = px(16)  # half the whole icon, which is bigger than the inner part that was found
    x0, x1 = max(0, cx - half - px(24)), max(0, cx - half)
    y0, y1 = max(0, cy - half), cy + half
    if x1 <= x0:
        return False
    strip = np.array(screen.crop((x0, y0, x1, y1)).convert("RGB"))
    white_per_column = (strip.min(axis=2) >= 180).sum(axis=0)
    # open: about as tall as the icon; hovered: half as tall; unread: a dot
    return int(white_per_column.max()) >= 0.65 * (y1 - y0)


def go_to_server(server, force=False):
    """
    Makes Discord show `server`'s channel by clicking its icon in the server list, unless the bot
    knows it is already there. False if its icon cannot be found.
    """
    global current_server
    if server is None or (server == current_server and not force):
        return True
    loc = locate_element(SERVERS[server]["icon"], confidence=SERVER_ICON_CONFIDENCE)
    if not loc:
        print(f"[WARN] Could not find {server}'s icon in Discord's server list")
        return False
    print(f"[SERVER] Going to {server}...")
    human_click(loc.x, loc.y)
    current_server = server
    screen_w, screen_h = screen_size()
    chat = (int(loc.x), 0, max(1, screen_w - int(loc.x)), screen_h)
    wait_for_screen_settle(chat, settle=0.3, timeout=3)  # the channel finished loading
    return True


def learn_current_server():
    """At startup: which server Discord is showing. If it cannot tell, it opens server 1."""
    global current_server
    current_server = shown_server()
    if current_server:
        print(f"[SERVER] Discord is showing {current_server}.")
    elif not go_to_server(next(iter(SERVERS)), force=True):
        print("[WARN] Server icons not found: tickets are only followed within the server on screen.")


def notification_area():
    """Bottom-right quarter of the screen, where Windows notifications pop up and stack."""
    try:
        screen_w, screen_h = pyautogui.size()
    except Exception:
        screen_w, screen_h = 1440, 900
    return (screen_w // 2, screen_h // 2, screen_w - screen_w // 2, screen_h - screen_h // 2)


def find_new_ticket_notification(screen=None):
    """(where, server) of a new-ticket Windows notification that is showing, or None."""
    toast_area = notification_area()
    for server, images in SERVERS.items():
        loc = locate_element(images["notification"], confidence=0.80, region=toast_area, screen=screen)
        if loc:
            return loc, server
    return None


def open_ticket_from_notification(screen=None):
    """Clicks a new-ticket Windows notification to jump to its channel. True if a Claim button shows up."""
    global current_server
    found = find_new_ticket_notification(screen)
    if not found:
        return False
    loc, server = found
    print(f"[NOTIFY] New ticket notification from {server} - opening its channel...")
    human_click(loc.x, loc.y)
    current_server = server  # the notification opens that server's #code-farm
    wait_for_window("Discord")
    if wait_for_element("discord_claim_btn.png", timeout=6, confidence=CONFIDENCE, pick_bottom=True):
        return True
    print("[NOTIFY] Channel opened but no Claim button showed up")
    return False


def claim_from_notification(screen=None, back_to_itunes=True):
    """
    While a ticket is being worked on: if a new-ticket notification shows up, click it (that opens
    its server's channel), claim the new ticket, and come back to iTunes (or, from Discord, let the
    current ticket take the bot back to its own server). True if it did; the caller then carries
    on where it left off.
    """
    if work.current is None or not work.can_claim() or not find_new_ticket_notification(screen):
        return False
    print("[NOTIFY] New ticket while busy with another - claiming it first...")
    if open_ticket_from_notification(screen):
        claim_new_tickets()
    if back_to_itunes:
        print("[NOTIFY] Back to iTunes to carry on with the current ticket...")
        switch_to_itunes()
    return True


def find_notification(screen=None):
    """Where to click to close the Windows notification showing in the corner, or None if there is none."""
    area = notification_area()
    screen = screen if screen is not None else grab_screen()
    loc = locate_element("notif_close_btn.png", confidence=0.80, region=area, screen=screen)
    if loc:
        return (loc.x + px(NOTIF_CLOSE_FROM_DOTS[0], "windows"), loc.y + px(NOTIF_CLOSE_FROM_DOTS[1], "windows"))
    # The X may only show on hover; it always sits at the same spot on the toast's top row
    header = locate_element("notif_discord_header.png", confidence=0.80, region=area, screen=screen)
    if header:
        return (header.x + px(NOTIF_CLOSE_FROM_HEADER[0], "windows"), header.y + px(NOTIF_CLOSE_FROM_HEADER[1], "windows"))
    return None


def close_notifications(max_rounds=6):
    """
    Closes Windows notifications in the bottom-right corner by their X, one after another while
    new ones keep sliding in. Returns how many were closed.
    """
    area = notification_area()
    closed = 0
    for _ in range(max_rounds):
        # Notifications slide in, and the rest move up when one closes: look once it is still,
        # or the X is clicked where it was a moment ago (that opens Discord instead)
        wait_for_screen_settle(area, settle=0.25, timeout=2, interval=0.05)
        target = find_notification()
        if not target:
            break
        human_click(*target, jitter=1)
        closed += 1
    if closed:
        print(f"[NOTIFY] Closed {closed} notification(s) that could cover iTunes")
    return closed


def click_itunes_submit(spot_name):
    """
    Clicks iTunes' Submit. Windows notifications pop up over it, often several in a row, so they
    are closed first and the click only happens while none is showing (one that slides in while
    the mouse is on its way is closed too). If one still caught the click, which brings Discord to
    the front, go back to iTunes and try again.
    """
    misses = 0
    for _ in range(8):
        claim_from_notification()  # a new ticket's notification is clicked, not closed
        close_notifications()
        loc = wait_for_element("itunes_submit_btn.png", timeout=1.5, confidence=0.82)
        if loc:
            remember_spot(spot_name, loc)
        elif find_notification():
            continue  # another notification slid in over it: close that one too
        elif "Discord" in get_active_window_title():
            switch_to_itunes()
            continue
        else:
            misses += 1
            loc = spot(spot_name)
            if not loc:
                if misses < 2:
                    continue
                print("[WARN] Could not find iTunes' Submit button")
                return False
            print(f"[INFO] Submit button not seen; clicking where it was before {loc}")
        human_move(*loc, jitter=1)
        if find_notification():
            continue  # one popped up while the mouse was on its way
        pyautogui.click()
        human_pause(0.05, 0.12)
        if not wait_for_window("Discord", timeout=0.5):
            return True
        print("[WARN] A notification caught the Submit click and opened Discord; going back to iTunes...")
        switch_to_itunes()
    print("[WARN] Notifications kept covering iTunes' Submit button")
    return False


# ==============================================================================
# ITUNES NAVIGATION & RESET CYCLE (Resets 10-Minute Timer to 0)
# ==============================================================================
def run_itunes_reset_cycle(return_to_discord=True):
    """
    Navigates iTunes to the Mobile Carrier Add Payment form and resets the 10-minute timer:
    Manage Payments -> Add Payment directly if it is already open (even with a Mobile Phone listed),
    otherwise Account -> View My Account -> Manage Payments -> (Add Payment) -> Mobile Carrier icon.
    """
    global last_itunes_cycle_time
    print("[ITUNES CYCLE] Resetting iTunes to Mobile Carrier Add Payment screen...")
    switch_to_itunes()

    # Dismiss any leftover popup first
    if locate_element("itunes_popup_ok_btn.png", confidence=0.82):
        click_element("itunes_popup_ok_btn.png", confidence=0.82)
        human_pause(0.3, 0.5)

    if locate_element("itunes_add_payment_btn.png", confidence=ADD_PAYMENT_CONFIDENCE):
        print("[ITUNES CYCLE] Already on Manage Payments - clicking Add Payment...")
        click_element("itunes_add_payment_btn.png", confidence=ADD_PAYMENT_CONFIDENCE)
    else:
        if not wait_for_element("itunes_account_settings_header.png", timeout=1.5, confidence=0.82):
            print("[ITUNES CYCLE] Clicking Account -> View My Account...")
            account = click_element("itunes_menu_account.png", spot_name="itunes_menu_account")
            if not click_element("itunes_menu_view_account.png", timeout=4) and account:
                # Fallback: View My Account is ~70px below Account menu
                human_click(account[0] + px(20, "itunes"), account[1] + px(72, "itunes"))

        if wait_for_element("itunes_manage_payments_link.png", timeout=10):
            print("[ITUNES CYCLE] Clicking Manage Payments...")
            click_element("itunes_manage_payments_link.png", spot_name="itunes_manage_payments")

        # Manage Payments shows either the existing list ("Add Payment") or the payment-type picker
        page = wait_for_any([("itunes_add_payment_btn.png", ADD_PAYMENT_CONFIDENCE), ("itunes_mobile_carrier_icon.png", CONFIDENCE)],
                            timeout=10, watch_tickets=True)
        if page == "itunes_add_payment_btn.png":
            print("[ITUNES CYCLE] Clicking Add Payment...")
            click_element("itunes_add_payment_btn.png", confidence=ADD_PAYMENT_CONFIDENCE)

    # Select Mobile Carrier icon, then wait for the phone form to load
    if wait_for_element("itunes_mobile_carrier_icon.png", timeout=10):
        print("[ITUNES CYCLE] Selecting Mobile Carrier icon...")
        click_element("itunes_mobile_carrier_icon.png", spot_name="itunes_mobile_carrier")
        wait_for_element("itunes_phone_input.png", timeout=8, confidence=0.80)
    else:
        print("[WARN] Mobile Carrier option did not show up")

    # Reset the 10-minute timer to 0 because the full cycle just completed!
    last_itunes_cycle_time = time.time()
    print("[TIMER] 10-minute keep-alive timer reset to 0:00.")

    if return_to_discord:
        switch_to_discord()


# ==============================================================================
# DISCORD TEXT EXTRACTION & ACTIONS
# ==============================================================================
value_box_rgb = VALUE_BOX_RGB  # the box colour in this Discord's theme


def _value_row(label, length=260):
    """The pixels of the row through the top padding of the box right of a `Label →` (solid, no text)."""
    try:
        raw = pyautogui.screenshot(region=(int(label.x), int(label.y) - px(5), px(length), 1)).convert("RGB").tobytes()
    except Exception:
        return []
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]


def _color_runs(pixels, min_length):
    """(start, end, colour) of each stretch of one colour (within a few shades) at least `min_length` long."""
    runs, start = [], 0
    for i in range(1, len(pixels) + 1):
        if i == len(pixels) or max(abs(a - b) for a, b in zip(pixels[i], pixels[start])) > 3:
            if i - start >= min_length:
                runs.append((start, i - 1, pixels[start]))
            start = i
    return runs


def learn_value_box_color(number_label):
    """
    Reads the colour of the box behind values from the phone number's box, which is always there.
    Discord themes draw it in different colours; the Code's 4 digits are only copied from a box of
    this colour (not from the "17 seconds ago" timer, which is highlighted in another colour).
    """
    global value_box_rgb
    row = _value_row(number_label, length=130)
    if not row:
        return
    background = row[0]
    for start, end, colour in _color_runs(row, px(20)):
        if start <= px(60) and max(abs(a - b) for a, b in zip(colour, background)) > 6:
            if colour != value_box_rgb:
                print(f"[THEME] Discord draws the value boxes in {colour} here (was looking for {value_box_rgb}).")
                value_box_rgb = colour
            return


def describe_value_row(label):
    """What is right of a `Label →`, for the console when its box is not found."""
    runs = _color_runs(_value_row(label), 3)
    return ", ".join(f"{colour} x{end - start + 1}" for start, end, colour in runs) or "nothing readable"


def find_value_box(label):
    """Returns (left, right) of the grey inline-code box to the right of a `Label →`, or None."""
    x0 = int(label.x)
    br, bg, bb = value_box_rgb
    run_start = None
    for i, (r, g, b) in enumerate(_value_row(label) + [(-99, -99, -99)]):
        inside = abs(r - br) <= 6 and abs(g - bg) <= 6 and abs(b - bb) <= 8
        if inside and run_start is None:
            run_start = i
        elif not inside and run_start is not None:
            if i - run_start >= px(10):
                return (x0 + run_start, x0 + i - 1)
            run_start = None
    return None


def copy_ticket_value(label_img, region, extract, default_offsets, require_box=False):
    """
    Finds `Number →` / `Code →` inside `region` (the ticket being handled), double-clicks
    the value in its box and copies it. With `require_box`, nothing is clicked unless the
    value's grey code box is there (after a resend the Code shows a "17 seconds ago" timer).
    Returns the cleaned value, or "" if nothing valid could be copied.
    """
    copied = ""
    for attempt in (1, 2):
        label = wait_for_element(label_img, timeout=3, confidence=0.82, pick_bottom=True, region=region)
        if not label:
            print(f"[WARN] Could not find {label_img} on the ticket")
            return ""
        box = find_value_box(label)
        if box is None:
            if require_box:
                return ""
            box = (label.x + px(default_offsets[0]), label.x + px(default_offsets[1]))
        left, right, y = box[0], box[1], label.y

        old = emptied_clipboard()
        human_click((left + right) / 2, y, clicks=2, jitter=1)
        copied = copy_selection(old=old)
        human_click(label.x, label.y, jitter=1)  # clear the blue text selection
        value = extract(copied)
        if value:
            return value

        print(f"[WARN] Copied {copied!r}, which is not a valid value (try {attempt}/2)")
        human_pause(0.1, 0.2)
    return ""


def select_discord_action_menu_item(menu_item_img, region=None):
    """Clicks the Action dropdown (in `region`, else on the newest ticket) and selects the option."""
    switch_to_discord()
    print(f"[DISCORD] Opening Action dropdown for {menu_item_img}...")
    if region:
        action_loc = wait_for_element("discord_action_dropdown.png", timeout=8, confidence=0.80, region=region)
    else:
        action_loc = wait_for_element("discord_action_dropdown.png", timeout=8, confidence=0.80, pick_bottom=True)
    if not action_loc:
        print("[WARN] Could not find Action dropdown button")
        return False
    human_click(action_loc.x, action_loc.y)

    loc = wait_for_element(menu_item_img, timeout=5, confidence=0.78)
    if loc:
        click_and_wait_for_update(loc.x, loc.y, menu_item_img, region=screen_area_around(action_loc.x, action_loc.y))
        return True

    debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_dropdown.png")
    try:
        pyautogui.screenshot(debug_path)
        print(f"[WARN] Could not find {menu_item_img} in dropdown menu. Screenshot saved: {debug_path}")
    except Exception:
        print(f"[WARN] Could not find {menu_item_img} in dropdown menu")
    human_press("escape")  # close the open dropdown
    return False


def wait_for_user_code(ticket, timeout=CODE_WAIT_TIMEOUT, previous_code=None):
    """
    Waits up to `timeout` seconds (2 minutes) for the user to submit their verification code on
    `ticket`: its "Mark as Verified" button appears and the Code shows 4 digits in its box.
    While another claimed ticket is waiting, gives up after BUSY_CODE_TIMEOUT (1 minute) instead.
    New tickets that show up meanwhile are claimed right away.
    `previous_code` (the rejected one) is ignored while it is still showing on the ticket.
    Returns the code, None on timeout, or USER_LEFT when the Code shows "❌Left".
    """
    busy = " (1 minute while another ticket is waiting)" if work.waiting else ""
    print(f"[WAIT] Waiting up to {timeout}s{busy} for user to submit verification code...")
    start = time.time()
    last_sweep = 0.0
    told_old_code = told_no_box = False

    while time.time() - start < timeout:
        if work.waiting and time.time() - start >= BUSY_CODE_TIMEOUT:
            print(f"[BUSY] No code within {BUSY_CODE_TIMEOUT}s and another ticket is waiting - failing this one.")
            return None
        watch_screen()
        screen = grab_screen()
        # 1. Check if Windows notification popped up showing "Submitted code:"
        if locate_element("notif_code_submitted.png", confidence=0.80, screen=screen):
            print("[DETECTED] Code submission notification seen!")
            switch_to_discord()
        # A new ticket's notification (it may be in the other server): claim it, then come back
        claim_from_notification(screen, back_to_itunes=False)

        # 2. Periodically check Discord embed directly (every ~4s) so we never miss a code
        if int(time.time() - start) % 4 == 0:
            switch_to_discord()

        # Newer tickets may have pushed this one up: find it, then look only at its own lines
        region = ticket.region()
        if region is None:
            time.sleep(0.5)
            continue
        if locate_element("discord_code_left.png", confidence=0.85, region=region):
            return USER_LEFT

        # When a user submits a code, the green "Mark as Verified" button appears on the embed
        mark_loc = locate_element("discord_mark_verified_btn.png", confidence=0.82, region=region)
        if mark_loc:
            wait_for_screen_settle(screen_area_around(mark_loc.x, mark_loc.y), settle=0.2, timeout=2, interval=0.05)
            code = copy_ticket_value("discord_code_label.png", region, extract_code, CODE_BOX_OFFSETS,
                                     require_box=True)
            if not code and not told_no_box:
                print("[WAIT] Code is not in its box yet (timer showing); waiting for the 4-digit code...")
                label = locate_element("discord_code_label.png", confidence=0.82, region=region, pick_bottom=True)
                if label:
                    print(f"[WAIT] (Looking for a box in {value_box_rgb}; right of Code there is: {describe_value_row(label)})")
                told_no_box = True
            if code and code == previous_code:
                if not told_old_code:
                    print(f"[WAIT] Ticket still shows the old code {code}; waiting for the new one...")
                    told_old_code = True
                time.sleep(1.5)
                continue
            if code:
                print(f"[CODE COPIED] Extracted verification code: {code}")
                return code

        # New tickets show up at the bottom of the chat: claim them right away (less often while
        # the chat is scrolled up to this ticket, since going down and back up takes a moment)
        if work.can_claim() and time.time() - last_sweep >= (10 if ticket.scrolled else 3):
            last_sweep = time.time()
            ticket.back_to_bottom()
            claim_new_tickets()
            continue

        time.sleep(0.2)

    print(f"[TIMEOUT] {timeout}s elapsed without a valid code submission.")
    return None


def has_returning_user_warning(embed_region):
    """True only when the Server line shows ✅ followed by ⚠️; ✅ alone is a normal ticket."""
    box = locate_box("discord_server_line.png", confidence=0.83, region=embed_region)
    if not box:
        return False
    left, top, width, height = box
    # ⚠️ is too small a part of the line for template matching to tell apart, so count
    # its yellow pixels in the strip just right of the ✅ instead.
    strip = (left + width, max(0, top - px(2)), px(20), height + px(4))
    try:
        raw = pyautogui.screenshot(region=strip).convert("RGB").tobytes()
    except Exception:
        return False
    yellow = sum(1 for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3]) if r > 180 and g > 140 and b < 90)
    return yellow >= max(4, round(8 * ui_scale["discord"] ** 2))


# ==============================================================================
# FOLLOWING ONE TICKET
# ==============================================================================
USER_LEFT = "user left"
# The ticket's lines and buttons, measured (at 100% size) from the center of its phone-number box:
# Code label ~43px below, buttons ~81px, Action ~115px. The next ticket's lines start ~200px further down.
TICKET_AREA = dict(left=220, up=40, right=330, down=175)


class Ticket:
    """
    A claimed ticket. Newer tickets push it up the chat or off screen, so it is found again by a
    snapshot of its phone-number box, and its buttons are only looked for right there. It also
    remembers its server, and goes back there when the bot was in the other one.
    """

    def __init__(self, left, right, y, server=None):
        self.fingerprint = grab_bgr((int(left), int(y) - px(6), int(right - left) + 1, px(13)))
        self.center = Point(int(left + right) // 2, int(y))
        self.scrolled = 0  # wheel notches the chat was scrolled up to keep the ticket in view
        self.server = server

    def find(self):
        """Where the ticket's number box is now: in its server, scrolling up if newer messages hid it."""
        if self.fingerprint is None:
            return None
        if "Discord" not in get_active_window_title():
            switch_to_discord()
        go_to_server(self.server)
        checked_server = told = False
        for _ in range(8):
            loc = locate_template(self.fingerprint, 0.93)
            if loc:
                self.center = loc
                return loc
            if self.server and not checked_server:
                checked_server = True
                shown = shown_server()
                if shown and shown != self.server:  # not where the bot thought: go to the right one
                    go_to_server(self.server, force=True)
                    continue
            if not told:
                told = True
                print("[TICKET] Newer messages pushed the ticket out of view - scrolling up to it...")
            human_move(self.center.x, screen_size()[1] // 2)
            for _ in range(3):
                pyautogui.scroll(120)
                time.sleep(random.uniform(0.02, 0.05))
            self.scrolled += 3
            human_pause(0.25, 0.4)
        # Last try: maybe Discord was showing the other server without the bot being able to tell
        if self.server and go_to_server(self.server, force=True):
            loc = locate_template(self.fingerprint, 0.93)
            if loc:
                self.center, self.scrolled = loc, 0
                return loc
        print("[WARN] Lost track of the ticket")
        return None

    def region(self):
        """Screen area holding this ticket's Code line and buttons (not the next ticket's)."""
        loc = self.find()
        return screen_area_around(loc.x, loc.y, **TICKET_AREA) if loc else None

    def has_user_left(self):
        region = self.region()
        return bool(region and locate_element("discord_code_left.png", confidence=0.85, region=region))

    def click_button(self, image_name, what, confidence=0.82, timeout=3):
        """Clicks one of this ticket's buttons. False if it is not there."""
        switch_to_discord()
        region = self.region()
        loc = region and wait_for_element(image_name, timeout=timeout, confidence=confidence, region=region)
        if not loc:
            return False
        click_and_wait_for_update(loc.x, loc.y, what)
        return True

    def choose_action(self, menu_item_img):
        """Action -> `menu_item_img` on this ticket. False if it could not be done."""
        switch_to_discord()
        region = self.region()
        if not region:
            print(f"[WARN] Could not find the ticket to choose {menu_item_img}")
            return False
        return select_discord_action_menu_item(menu_item_img, region=region)

    def back_to_bottom(self):
        """Scrolls the chat back down if it was scrolled up to follow this ticket."""
        if not self.scrolled:
            return
        switch_to_discord()
        human_move(self.center.x, screen_size()[1] // 2)
        for _ in range(self.scrolled + 15):
            pyautogui.scroll(-120)
            time.sleep(random.uniform(0.01, 0.03))
        self.scrolled = 0
        human_pause(0.2, 0.35)


# ==============================================================================
# MAIN TICKET WORKFLOW
# ==============================================================================
class Work:
    """The ticket being worked on, the claimed ones waiting their turn, and the verification goal."""

    def __init__(self, limit=None):
        self.limit = limit          # stop after this many verifications (None = no limit)
        self.verified = 0
        self.current = None         # the Ticket being worked on
        self.waiting = collections.deque()  # claimed Tickets, oldest first

    def can_claim(self):
        """False once the tickets in hand are enough to reach the verification goal."""
        if self.limit is None:
            return True
        return self.verified + len(self.waiting) + (self.current is not None) < self.limit


work = Work()


def claim_ticket():
    """
    Claims the newest unclaimed ticket on screen. Returns it as a Ticket to work on, or None if
    there is nothing (more) to do for it: not claimed, ✅⚠️ marked verified, user gone, no number.
    """
    claim_loc = locate_element("discord_claim_btn.png", confidence=CONFIDENCE, pick_bottom=True)
    if not claim_loc:
        return None

    # A freshly posted ticket may still be drawing; wait until it is still, then find Claim again
    wait_for_screen_settle(screen_area_around(claim_loc.x, claim_loc.y), settle=0.2, timeout=2, interval=0.05)
    claim_loc = locate_element("discord_claim_btn.png", confidence=CONFIDENCE, pick_bottom=True)
    if not claim_loc:
        return None

    # Check if the newest ticket has the special returning-user warning: Server -> ✅ ⚠️
    embed_region = (max(0, int(claim_loc.x) - px(120)), max(0, int(claim_loc.y) - px(160)), px(350), px(160))
    is_returning_user = has_returning_user_warning(embed_region)

    # Click Claim, then wait until the embed shows Claim -> @you and the Resend Code / Reject buttons
    print("[TICKET] Clicking Claim button...")
    human_click(claim_loc.x, claim_loc.y)
    anchor = wait_for_claim_to_register(claim_loc)
    if anchor is None:
        print("[WARN] Claim did not go through (Claim button still there). Skipping this ticket.")
        return None
    print("[TICKET] Claimed - ticket updated.")

    # SPECIAL CASE: Server -> ✅ ⚠️ (Claim -> Action -> Mark as Verified immediately)
    if is_returning_user:
        print("[SPECIAL CASE] Returning user (✅ ⚠️) detected! Marking as Verified via Action menu...")
        select_discord_action_menu_item("discord_menu_mark_verified.png",
                                        region=screen_area_around(anchor.x, anchor.y, left=250, up=60, right=300, down=80))
        return None

    # Remember this ticket by its number box (before the copy selects it), so it can be found again
    number_region = screen_area_around(anchor.x, anchor.y, left=250, up=170, right=250, down=0)
    number_label = wait_for_element("discord_number_label.png", timeout=3, confidence=0.82, pick_bottom=True,
                                    region=number_region)
    if not number_label:
        print("[WARN] Could not find the ticket's Number. Leaving this ticket for a human.")
        return None
    learn_value_box_color(number_label)
    box = find_value_box(number_label) or (number_label.x + px(NUMBER_BOX_OFFSETS[0]), number_label.x + px(NUMBER_BOX_OFFSETS[1]))
    ticket = Ticket(box[0], box[1], number_label.y, server=current_server)

    if ticket.has_user_left():
        print("[LEFT] The user already left. Skipping this ticket.")
        return None
    return ticket


def claim_new_tickets():
    """
    Claims every unclaimed ticket showing in Discord right away (newest first), and puts them in
    line to be worked on, oldest first. Returns how many were put in line.
    """
    switch_to_discord()
    first = len(work.waiting)
    for _ in range(6):  # a Claim that does not go through stays on screen: don't keep trying it
        if not work.can_claim() or not locate_element("discord_claim_btn.png", confidence=CONFIDENCE, pick_bottom=True):
            break
        ticket = claim_ticket()
        if ticket:
            work.waiting.insert(first, ticket)  # older ones (claimed later) go in front
    added = len(work.waiting) - first
    if added and work.current is not None:
        print(f"[QUEUE] {len(work.waiting)} claimed ticket(s) waiting for their turn.")
    return added


def work_on_ticket(ticket):
    """Copies a claimed ticket's phone number and verifies it with iTunes. True when verified."""
    work.current = ticket
    try:
        region = ticket.region()
        if region is None:
            print("[WARN] Could not find the ticket again. Leaving it for a human.")
            return False
        if locate_element("discord_code_left.png", confidence=0.85, region=region):
            print("[LEFT] The user left before their turn. Skipping this ticket.")
            return False

        # Copy the phone number as-is (leading 0 and spaces are fine, iTunes strips spaces automatically)
        phone_number = copy_ticket_value("discord_number_label.png", region, extract_phone, NUMBER_BOX_OFFSETS)
        if not phone_number:
            print("[WARN] Could not copy a valid phone number. Leaving this ticket for a human.")
            return False
        print(f"[TICKET] Copied phone number: '{phone_number}'")
        return verify_with_itunes(ticket, phone_number)
    finally:
        work.current = None
        ticket.back_to_bottom()


def verify_with_itunes(ticket, phone_number):
    """iTunes part of a claimed ticket: phone number, the user's code, then the Discord outcome."""
    # Switch to iTunes
    switch_to_itunes()
    claim_from_notification()

    # Ensure iTunes is on the Add Payment -> Mobile Carrier (+33) screen
    if not wait_for_element("itunes_phone_input.png", timeout=2, confidence=0.80):
        run_itunes_reset_cycle(return_to_discord=False)

    # Click inside the +33 phone number field and paste as-is
    phone_loc = wait_for_element("itunes_phone_input.png", timeout=8, confidence=0.80)
    if phone_loc:
        remember_spot("itunes_phone_input_box", (phone_loc.x + px(80, "itunes"), phone_loc.y))
    phone_field = spot("itunes_phone_input_box")  # just found there, or where it was last time
    if not phone_field:
        print("[WARN] Could not find iTunes' phone number field. Leaving this ticket for a human.")
        return False
    human_click(*phone_field)
    if not replace_field_text(phone_number):
        print("[WARN] Could not get the phone number into iTunes. Leaving this ticket for a human.")
        return False

    # Scroll down and click Submit
    human_scroll(-5)
    click_itunes_submit("itunes_submit_phone")

    print("[ITUNES] Waiting for iTunes to send the code...")
    # (it moves on as soon as the page shows; some PCs/connections take a while to send the code)
    result = wait_for_any([
        ("itunes_unable_to_send_code.png", 0.80),
        ("itunes_enter_code_input.png", 0.80),
    ], timeout=30, watch_tickets=True)

    # CHECK 1: Did "Unable to Send Code" popup appear?
    if result == "itunes_unable_to_send_code.png":
        print("[ERROR POPUP] 'Unable to Send Code' detected! Resetting iTunes and rejecting ticket...")
        click_element("itunes_popup_ok_btn.png", confidence=0.80, timeout=3)
        run_itunes_reset_cycle(return_to_discord=True)

        # In Discord: click Reject directly if visible; if user submitted code, click Action -> Reject
        if not ticket.click_button("discord_reject_btn.png", "Reject"):
            ticket.choose_action("discord_menu_reject.png")
        return False

    # CHECK 2: Did iTunes reach the "Enter the verification code" screen?
    if result is None:
        print("[WARN] Did not reach code entry screen. Resetting iTunes...")
        run_itunes_reset_cycle(return_to_discord=True)
        return False

    # Up to 2 attempts to receive and verify the 4-digit SMS code
    previous_code = None
    for attempt in (1, 2):
        code = wait_for_user_code(ticket, timeout=CODE_WAIT_TIMEOUT, previous_code=previous_code)

        if code == USER_LEFT:
            print("[LEFT] The user left. Stopping this ticket, resetting iTunes and waiting for the next one.")
            run_itunes_reset_cycle(return_to_discord=True)
            return False

        # If user did not submit a code within 2 minutes:
        if not code:
            print(f"[TIMEOUT] No code submitted on attempt {attempt}. Failing verification...")
            ticket.choose_action("discord_menu_failed_verification.png")
            run_itunes_reset_cycle(return_to_discord=True)
            return False

        # Switch to iTunes, enter the code, and click Submit
        switch_to_itunes()
        claim_from_notification()
        code_box = wait_for_element("itunes_enter_code_input.png", timeout=4, confidence=0.80)
        if code_box:
            remember_spot("itunes_enter_code_box", (code_box.x + px(30, "itunes"), code_box.y))
        code_field = spot("itunes_enter_code_box")  # just found there, or where it was last time
        if not code_field:
            print("[WARN] Could not find iTunes' code field. Leaving this ticket for a human.")
            return False
        human_click(*code_field)
        if not replace_field_text(code):
            print("[WARN] Could not get the code into iTunes. Leaving this ticket for a human.")
            return False

        click_itunes_submit("itunes_submit_code")

        print("[ITUNES] Waiting for iTunes to check the code...")
        outcome = wait_for_any([
            ("itunes_unable_to_verify_code.png", 0.80),
            ("itunes_billing_issue_banner.png", 0.75),
            ("itunes_mobile_phone_verified.png", 0.80),
        ], timeout=15, watch_tickets=True)

        # OUTCOME A: "Unable to Verify Code" popup (Wrong code entered)
        if outcome == "itunes_unable_to_verify_code.png":
            print(f"[WRONG CODE] 'Unable to Verify Code' on attempt {attempt}!")
            click_element("itunes_popup_ok_btn.png", confidence=0.80, timeout=3)

            if attempt == 1 and not work.waiting:
                # 1st wrong code: click "Didn't get a verification code?" in iTunes
                print("[RETRY] Clicking 'Didn't get a verification code?' in iTunes...")
                click_element("itunes_didnt_get_code_link.png", confidence=0.80, spot_name="itunes_didnt_get_code", timeout=4)

                # After a code was submitted the ticket only offers Resend Code inside the Action menu
                switch_to_discord()
                print("[RETRY] Clicking Action -> Resend Code in Discord...")
                if ticket.choose_action("discord_menu_resend_code.png"):
                    print("[RETRY] Resend Code clicked! Waiting 2 more minutes for the 2nd code...")
                elif ticket.click_button("discord_resend_available.png", "Resend Code", confidence=0.85):
                    print("[RETRY] Clicked the Resend Code button! Waiting 2 more minutes for the 2nd code...")
                else:
                    print("[WARN] Could not click Resend Code; still waiting for a new code")
                previous_code = code
                continue
            else:
                # 2nd wrong code, or a wrong code while another ticket waits (one try only then):
                # click Failed Verification in Discord and reset iTunes
                if attempt == 1:
                    print("[FAILED] Wrong code and another ticket is waiting! Clicking Failed Verification...")
                else:
                    print("[FAILED] 2nd wrong code! Clicking Failed Verification and resetting iTunes...")
                if not ticket.click_button("discord_failed_verification_btn.png", "Failed Verification"):
                    ticket.choose_action("discord_menu_failed_verification.png")
                run_itunes_reset_cycle(return_to_discord=True)
                return False

        # OUTCOME B: Red "Billing issue" banner in iTunes
        if outcome == "itunes_billing_issue_banner.png":
            print("[BILLING ISSUE] Billing issue banner detected in iTunes!")
            run_itunes_reset_cycle(return_to_discord=True)
            ticket.choose_action("discord_menu_billing_issue.png")
            return False

        # OUTCOME C: Success! Manage Payments shows Mobile Phone added
        if outcome == "itunes_mobile_phone_verified.png":
            print("[SUCCESS] Mobile Phone added in Manage Payments! Marking the ticket as verified...")
            # Click Mark as Verified button directly (Action menu only used for ✅⚠️ case)
            if not ticket.click_button("discord_mark_verified_btn.png", "Mark as Verified", timeout=8):
                print("[WARN] Mark as Verified button not found")
            return True

        print(f"[WARN] iTunes showed no result after the code on attempt {attempt}")

    return False


# ==============================================================================
# MAIN LOOP
# ==============================================================================
def _cli_args():
    return [arg.strip() for arg in sys.argv[1:]]


def startup_check():
    """Says what the bot is working with, and measures how big each app on screen is drawn."""
    reset_ui_scale()
    screen_w, screen_h = screen_size()
    scale = display_scale()
    print(f"[SETUP] Screen {screen_w}x{screen_h}, Windows display scaling {scale:.0%}.")
    if abs(scale - 1.0) > 0.01:
        print("[SETUP] The images were cropped at 100%, so they are resized to match. If buttons are "
              "missed, 100% (Settings > System > Display > Scale) is the most reliable.")
    missing = [name for name in sorted(set(sum(SCALE_ANCHORS.values(), ()))) if not os.path.exists(img_path(name))]
    if missing:
        print(f"[WARN] Missing images in images/: {', '.join(missing)}")
    spots = _known_spots()
    print(f"[SETUP] Backup click spots for this screen: {len(spots)}" +
          ("" if spots else " yet (it remembers where it finds each button)."))
    screen = grab_screen()
    for group in UI_GROUPS:
        if not calibrate_scale(group, screen, search=(group == "windows")):
            print(f"[SCALE] {UI_GROUPS[group]} is not on screen yet; its size is measured as soon as it is.")


def ask_verification_limit():
    """How many verifications to do before stopping: `python bot.py 2`, or asked at startup. None = no limit."""
    for answer in _cli_args():
        if answer.isdigit():
            return int(answer) if int(answer) > 0 else None
    while True:
        try:
            answer = input("How many verifications before the bot stops? (1, 2, 3 ... or press Enter for no limit): ").strip()
        except EOFError:
            return None
        if not answer:
            return None
        if answer.isdigit() and int(answer) > 0:
            return int(answer)
        print("Please type a whole number like 1, 2 or 3, or just press Enter for no limit.")


def send_done_message():
    """Types "im the bot and done" in the current channel's chat bar."""
    switch_to_discord()
    if click_element("discord_chat_input.png", confidence=0.80, timeout=5):
        human_type("im the bot and done")
        human_pause(0.2, 0.4)
        human_press("enter")
        print("[FINISHED] Typed 'im the bot and done'.")
    else:
        print("[WARN] Could not find the chat bar to send the done message")


def main():
    global last_itunes_cycle_time
    print("==================================================================")
    print("  DISCORD <-> ITUNES VISUAL AUTOMATION BOT")
    print("  Safety Abort: Slam mouse into ANY of the 4 screen corners.")
    print("==================================================================")
    limit = ask_verification_limit()
    print(f"[SETUP] Will stop after {limit} verification(s)." if limit else "[SETUP] No limit - runs until you close it.")
    print("Starting in 3 seconds...")
    time.sleep(3)
    startup_check()

    work.limit = limit
    last_itunes_cycle_time = time.time()
    switch_to_discord()
    learn_current_server()

    while True:
        # 0. Resolution or display scaling changed? Then every app is measured again
        watch_screen()

        # 1. Check if 10 minutes (600s) have elapsed since the last iTunes cycle
        elapsed = time.time() - last_itunes_cycle_time
        if elapsed >= KEEP_ALIVE_INTERVAL:
            print("[10-MIN TIMER] 10 minutes reached! Running iTunes keep-alive cycle...")
            run_itunes_reset_cycle(return_to_discord=True)

        # 2. A new-ticket notification takes the bot straight to that ticket's channel
        screen = grab_screen()
        if open_ticket_from_notification(screen):
            screen = None

        # 3. Claim every ticket on screen, then work through the claimed ones, oldest first.
        #    Tickets that come in meanwhile are claimed right away and join the line.
        if locate_element("discord_claim_btn.png", confidence=CONFIDENCE, pick_bottom=True, screen=screen):
            claim_new_tickets()
        if work.waiting:
            while work.waiting:
                if len(work.waiting) > 1:
                    print(f"[QUEUE] Next ticket ({len(work.waiting) - 1} more waiting after it).")
                if work_on_ticket(work.waiting.popleft()):
                    work.verified += 1
                    print(f"[COMPLETE] Verified {work.verified}" + (f"/{limit}" if limit else "") + ".")
                    if limit and work.verified >= limit:
                        send_done_message()
                        print("[COMPLETE] Verification goal reached. Bot is now exiting.")
                        sys.exit(0)
                    # Get iTunes back to the Mobile Carrier form so the next ticket starts right away
                    run_itunes_reset_cycle(return_to_discord=True)
                claim_new_tickets()
            print("[WAIT] Ticket finished. Watching Discord for the next ticket...")
        elif "Discord" in get_active_window_title():
            recheck_scale("discord", screen)  # notices a Discord zoom change while idle

        human_pause(0.15, 0.3)


if __name__ == "__main__":
    main()
