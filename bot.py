import os
import re
import sys
import math
import time
import random
import ctypes
import collections
import tkinter as tk
import cv2
import numpy as np
import pyautogui

try:
    import pyperclip  # installed with pyautogui; talks to the Windows clipboard directly
except ImportError:
    pyperclip = None

Point = collections.namedtuple("Point", "x y")

# ==============================================================================
# CONFIGURATION (Windows display scaling 100%)
# ==============================================================================
pyautogui.FAILSAFE = True   # Slam mouse into any of the 4 screen corners to abort
pyautogui.PAUSE = 0.03      # Base pause; the human_* helpers add small randomized waits on top

IMAGES_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
CONFIDENCE = 0.84
# The "Add Payment Method" label left of the Add Payment button scores ~0.81 against it
ADD_PAYMENT_CONFIDENCE = 0.88

# 10-minute timer (600 seconds) for the iTunes keep-alive cycle
KEEP_ALIVE_INTERVAL = 600
# 2-minute timer (120 seconds) waiting for the user's verification code
CODE_WAIT_TIMEOUT = 120

# Fallback "the embed finished updating" rule: unchanged for this long
EMBED_SETTLE_SECONDS = 0.35
# Longest wait for Discord to react to a button click
EMBED_UPDATE_TIMEOUT = 8

# Inline-code box behind the Number / Code values, and where it sits relative to the
# label's center when it cannot be detected (measured on the 1440x900 ticket embed)
VALUE_BOX_RGB = (40, 41, 57)
NUMBER_BOX_OFFSETS = (38, 110)
CODE_BOX_OFFSETS = (31, 56)

# Where a Windows notification's X is, from the center of its "⋯ ✕" image or its Discord header
NOTIF_CLOSE_FROM_DOTS = (20, 0)
NOTIF_CLOSE_FROM_HEADER = (288, 0)

# Screen resolutions the bot can run on, chosen at startup. Each has its own images in
# images/<name>/; an image missing there is borrowed from images/1440x900/ (at 100% display
# scaling Discord and iTunes draw their buttons the same size on any screen).
# "coords" are blind fallback clicks for when an image is not found. They were measured on
# 1440x900 only, so other resolutions click only what they actually find on screen.
BASE_PROFILE = "1440x900"
PROFILES = {
    "1440x900": {
        "taskbar_discord_region": (450, 845, 200, 55),
        "taskbar_itunes_region": (750, 845, 200, 55),
        "coords": {
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
    },
    "1920x1080": {
        "taskbar_discord_region": None,  # None = search the whole taskbar
        "taskbar_itunes_region": None,
        "coords": {},
    },
}
profile_name = BASE_PROFILE
PROFILE = PROFILES[BASE_PROFILE]

# Track the last time the iTunes Account -> Manage Payments -> Mobile Carrier cycle ran
last_itunes_cycle_time = time.time()


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def img_path(filename):
    """The active resolution's copy of an image, or the 1440x900 one if it has none."""
    own = os.path.join(IMAGES_ROOT, profile_name, filename)
    if profile_name == BASE_PROFILE or os.path.exists(own):
        return own
    return os.path.join(IMAGES_ROOT, BASE_PROFILE, filename)


def select_profile(name):
    global profile_name, PROFILE
    profile_name, PROFILE = name, PROFILES[name]
    _templates.clear()


def coord(name):
    """Measured fallback click spot for the active resolution, or None if there is none."""
    return PROFILE["coords"].get(name)


def screen_size():
    try:
        return tuple(pyautogui.size())
    except Exception:
        return (1440, 900)


def taskbar_region(key):
    region = PROFILE[key]
    if region:
        return region
    screen_w, screen_h = screen_size()
    return (0, screen_h - 60, screen_w, 60)


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
    try:
        screen_w, screen_h = pyautogui.size()
    except Exception:
        screen_w, screen_h = 1440, 900
    x0, y0 = max(0, int(x) - left), max(0, int(y) - up)
    x1, y1 = min(screen_w, int(x) + right), min(screen_h, int(y) + down)
    return (x0, y0, max(1, x1 - x0), max(1, y1 - y0))


_templates = {}


def _load_template(image_name):
    if image_name not in _templates:
        path = img_path(image_name)
        if os.path.exists(path):
            # imdecode instead of imread so folders with non-ASCII names still work
            _templates[image_name] = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        else:
            print(f"[WARN] Missing image: images/{profile_name}/{image_name}")
            _templates[image_name] = None
    return _templates[image_name]


def grab_screen():
    """One full screenshot that several locate_element(..., screen=...) calls can share."""
    try:
        return pyautogui.screenshot()
    except Exception:
        return None


def _match_scores(image_name, region=None, screen=None):
    """Template-matches an image against the screen (or `region`): (scores, x0, y0, w, h) or None."""
    template = _load_template(image_name)
    if template is None:
        return None
    if screen is not None:
        shot = screen.crop((region[0], region[1], region[0] + region[2], region[1] + region[3])) if region else screen
    else:
        shot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
    haystack = cv2.cvtColor(np.array(shot.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = template.shape[:2]
    if haystack.shape[0] < h or haystack.shape[1] < w:
        return None
    scores = np.nan_to_num(cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED), nan=0.0, posinf=0.0, neginf=0.0)
    x0, y0 = (int(region[0]), int(region[1])) if region else (0, 0)
    return scores, x0, y0, w, h


def locate_box(image_name, confidence=CONFIDENCE, region=None, screen=None):
    """(left, top, width, height) of the best match on screen, or None below `confidence`."""
    try:
        found = _match_scores(image_name, region, screen)
    except Exception:
        return None
    if found is None:
        return None
    scores, x0, y0, w, h = found
    _, best, _, (x, y) = cv2.minMaxLoc(scores)
    if best < confidence:
        return None
    return (x0 + int(x), y0 + int(y), w, h)


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
    scores, x0, y0, w, h = found
    ys, xs = np.where(scores >= confidence)
    if len(ys) == 0:
        return None
    # Best-scoring spot within the lowest match (matches spread over a few pixels)
    lowest = ys >= ys.max() - h // 2
    i = int(np.argmax(scores[ys[lowest], xs[lowest]]))
    x, y = int(xs[lowest][i]), int(ys[lowest][i])
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


def wait_for_any(candidates, timeout=15):
    """Waits for the first of several (image, confidence) pairs to appear; returns its image name."""
    start = time.time()
    while time.time() - start < timeout:
        screen = grab_screen()
        for image_name, confidence in candidates:
            if locate_element(image_name, confidence=confidence, screen=screen):
                return image_name
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


def click_element(image_name, confidence=CONFIDENCE, region=None, pick_bottom=False, fallback_coord=None, timeout=0):
    """Finds (waiting up to `timeout`s) and clicks an image, or uses fallback_coord if provided."""
    if timeout:
        loc = wait_for_element(image_name, timeout=timeout, confidence=confidence, pick_bottom=pick_bottom, region=region)
    else:
        loc = locate_element(image_name, confidence=confidence, region=region, pick_bottom=pick_bottom)
    if loc:
        human_click(loc.x, loc.y)
        return loc
    if fallback_coord:
        print(f"[INFO] Using 1440x900 fallback coordinate {fallback_coord} for {image_name}")
        human_click(*fallback_coord)
        return fallback_coord
    return None


def replace_field_text(text):
    """Clears the focused input and pastes `text`."""
    human_hotkey("ctrl", "a")
    human_press("backspace")
    set_clipboard_text(text)
    human_hotkey("ctrl", "v")
    human_pause(0.08, 0.15)


def copy_selection(timeout=1.5):
    """Presses Ctrl+C, then waits for the text to actually land on the clipboard."""
    human_hotkey("ctrl", "c")
    start = time.time()
    while time.time() - start < timeout:
        text = get_clipboard_text().strip()
        if text:
            return text
        time.sleep(0.05)
    return ""


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


def switch_to_discord():
    """Brings the Right Discord instance to the foreground without minimizing it."""
    title = get_active_window_title()
    if "Discord" in title or locate_element("discord_chat_input.png", confidence=0.80):
        return
    print("[SWITCH] Clicking Right Discord icon on taskbar...")
    loc = locate_element("taskbar_discord_right.png", confidence=0.80, region=taskbar_region("taskbar_discord_region"))
    target = loc or coord("taskbar_discord_right")
    if not target:
        print("[WARN] Could not find the Discord icon on the taskbar")
        return
    human_click(*target)
    if not wait_for_window("Discord"):
        print("[WARN] Discord window did not come to the front")
    human_pause(0.12, 0.25)  # let it repaint


def switch_to_itunes():
    """Brings iTunes to the foreground from minimized/background state."""
    title = get_active_window_title()
    if "iTunes" in title or locate_element("itunes_menu_account.png", confidence=0.82):
        return
    print("[SWITCH] Clicking iTunes icon on taskbar...")
    loc = locate_element("taskbar_itunes.png", confidence=0.80, region=taskbar_region("taskbar_itunes_region"))
    target = loc or coord("taskbar_itunes")
    if not target:
        print("[WARN] Could not find the iTunes icon on the taskbar")
        return
    human_click(*target)
    if not wait_for_window("iTunes"):
        print("[WARN] iTunes window did not come to the front")
    human_pause(0.15, 0.3)  # let it repaint


def notification_area():
    """Bottom-right quarter of the screen, where Windows notifications pop up and stack."""
    try:
        screen_w, screen_h = pyautogui.size()
    except Exception:
        screen_w, screen_h = 1440, 900
    return (screen_w // 2, screen_h // 2, screen_w - screen_w // 2, screen_h - screen_h // 2)


def open_ticket_from_notification(screen=None):
    """Clicks a new-ticket Windows notification to jump to its channel. True if a Claim button shows up."""
    toast_area = notification_area()
    for image_name in ("notif_new_ticket_blue.png", "notif_new_ticket_purple.png"):
        loc = locate_element(image_name, confidence=0.80, region=toast_area, screen=screen)
        if not loc:
            continue
        print("[NOTIFY] New ticket notification - opening its channel...")
        human_click(loc.x, loc.y)
        wait_for_window("Discord")
        if wait_for_element("discord_claim_btn.png", timeout=6, confidence=CONFIDENCE, pick_bottom=True):
            return True
        print("[NOTIFY] Channel opened but no Claim button showed up")
        return False
    return False


def close_notifications(max_rounds=5):
    """
    Closes Windows notifications in the bottom-right corner by their X, again while new ones
    keep popping up. Returns how many were closed.
    """
    area = notification_area()
    closed = 0
    for _ in range(max_rounds):
        screen = grab_screen()
        loc = locate_element("notif_close_btn.png", confidence=0.80, region=area, screen=screen)
        if loc:
            target = (loc.x + NOTIF_CLOSE_FROM_DOTS[0], loc.y + NOTIF_CLOSE_FROM_DOTS[1])
        else:
            # The X may only show on hover; it always sits at the same spot on the toast's top row
            header = locate_element("notif_discord_header.png", confidence=0.80, region=area, screen=screen)
            if not header:
                break
            target = (header.x + NOTIF_CLOSE_FROM_HEADER[0], header.y + NOTIF_CLOSE_FROM_HEADER[1])
        human_click(*target, jitter=1)
        closed += 1
        human_pause(0.3, 0.45)  # let it slide away before looking again
    if closed:
        print(f"[NOTIFY] Closed {closed} notification(s) that could cover iTunes")
    return closed


def click_itunes_submit(fallback_coord):
    """
    Clicks iTunes' Submit. A Windows notification can pop up right over it, so notifications are
    closed first; if one still caught the click (that brings Discord to the front), go back to
    iTunes and try again.
    """
    for _ in range(3):
        close_notifications()
        if not click_element("itunes_submit_btn.png", confidence=0.82, fallback_coord=fallback_coord, timeout=3):
            print("[WARN] Could not find iTunes' Submit button")
            return False
        if not wait_for_window("Discord", timeout=0.5):
            return True
        print("[WARN] A notification caught the Submit click and opened Discord; going back to iTunes...")
        switch_to_itunes()
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
            click_element("itunes_menu_account.png", fallback_coord=coord("itunes_menu_account"))
            if not click_element("itunes_menu_view_account.png", timeout=4):
                # Fallback: View My Account is ~70px below Account menu
                account = coord("itunes_menu_account")
                if account:
                    human_click(account[0] + 20, account[1] + 72)

        if wait_for_element("itunes_manage_payments_link.png", timeout=10):
            print("[ITUNES CYCLE] Clicking Manage Payments...")
            click_element("itunes_manage_payments_link.png", fallback_coord=coord("itunes_manage_payments"))

        # Manage Payments shows either the existing list ("Add Payment") or the payment-type picker
        page = wait_for_any([("itunes_add_payment_btn.png", ADD_PAYMENT_CONFIDENCE), ("itunes_mobile_carrier_icon.png", CONFIDENCE)], timeout=10)
        if page == "itunes_add_payment_btn.png":
            print("[ITUNES CYCLE] Clicking Add Payment...")
            click_element("itunes_add_payment_btn.png", confidence=ADD_PAYMENT_CONFIDENCE)

    # Select Mobile Carrier icon, then wait for the phone form to load
    if wait_for_element("itunes_mobile_carrier_icon.png", timeout=10):
        print("[ITUNES CYCLE] Selecting Mobile Carrier icon...")
        click_element("itunes_mobile_carrier_icon.png", fallback_coord=coord("itunes_mobile_carrier"))
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
def find_value_box(label):
    """Returns (left, right) of the grey inline-code box to the right of a `Label →`, or None."""
    probe_y = int(label.y) - 5  # top padding row of the box: solid colour, no text
    x0 = int(label.x)
    try:
        raw = pyautogui.screenshot(region=(x0, probe_y, 260, 1)).convert("RGB").tobytes()
    except Exception:
        return None
    br, bg, bb = VALUE_BOX_RGB
    run_start = None
    for i in range(len(raw) // 3):
        r, g, b = raw[3 * i:3 * i + 3]
        inside = abs(r - br) <= 6 and abs(g - bg) <= 6 and abs(b - bb) <= 8
        if inside and run_start is None:
            run_start = i
        elif not inside and run_start is not None:
            if i - run_start >= 10:
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
            box = (label.x + default_offsets[0], label.x + default_offsets[1])
        left, right, y = box[0], box[1], label.y

        set_clipboard_text("")
        human_click((left + right) / 2, y, clicks=2, jitter=1)
        copied = copy_selection()
        value = extract(copied)
        if value:
            return value

        print(f"[WARN] Copied {copied!r}, which is not a valid value (try {attempt}/2)")
        human_pause(0.1, 0.2)
    return ""


def select_discord_action_menu_item(menu_item_img):
    """Clicks the Action dropdown on the newest ticket and selects the specified option."""
    switch_to_discord()
    print(f"[DISCORD] Opening Action dropdown for {menu_item_img}...")
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


def wait_for_user_code(timeout=CODE_WAIT_TIMEOUT, previous_code=None):
    """
    Waits up to `timeout` seconds (2 minutes) for the user to submit their verification code.
    Watches for either the Windows notification (`notif_code_submitted.png`) or
    the Discord embed updating to show `Mark as Verified` (`discord_mark_verified_btn.png`).
    `previous_code` (the rejected one) is ignored while it is still showing on the ticket.
    """
    print(f"[WAIT] Waiting up to {timeout}s for user to submit verification code...")
    start = time.time()
    told_old_code = told_no_box = False

    while time.time() - start < timeout:
        screen = grab_screen()
        # 1. Check if Windows notification popped up showing "Submitted code:"
        if locate_element("notif_code_submitted.png", confidence=0.80, screen=screen):
            print("[DETECTED] Code submission notification seen!")
            switch_to_discord()

        # 2. Periodically check Discord embed directly (every ~4s) so we never miss a code
        if int(time.time() - start) % 4 == 0:
            switch_to_discord()

        # When a user submits a code, the green "Mark as Verified" button appears on the embed
        mark_loc = locate_element("discord_mark_verified_btn.png", confidence=0.82, pick_bottom=True, screen=screen)
        if mark_loc:
            wait_for_screen_settle(screen_area_around(mark_loc.x, mark_loc.y), settle=0.2, timeout=2, interval=0.05)
            # Only read the Code from the ticket this button belongs to
            code_region = screen_area_around(mark_loc.x, mark_loc.y, left=200, up=160, right=250, down=0)
            code = copy_ticket_value("discord_code_label.png", code_region, extract_code, CODE_BOX_OFFSETS,
                                     require_box=True)
            if not code and not told_no_box:
                print("[WAIT] Code is not in its box yet (timer showing); waiting for the 4-digit code...")
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

        time.sleep(0.2)

    print("[TIMEOUT] 2 minutes elapsed without a valid code submission.")
    return None


def has_returning_user_warning(embed_region):
    """True only when the Server line shows ✅ followed by ⚠️; ✅ alone is a normal ticket."""
    box = locate_box("discord_server_line.png", confidence=0.83, region=embed_region)
    if not box:
        return False
    left, top, width, height = box
    # ⚠️ is too small a part of the line for template matching to tell apart, so count
    # its yellow pixels in the strip just right of the ✅ instead.
    strip = (left + width, max(0, top - 2), 20, height + 4)
    try:
        raw = pyautogui.screenshot(region=strip).convert("RGB").tobytes()
    except Exception:
        return False
    yellow = sum(1 for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3]) if r > 180 and g > 140 and b < 90)
    return yellow >= 8


# ==============================================================================
# MAIN TICKET WORKFLOW
# ==============================================================================
def process_ticket():
    """Handles a single Discord verification ticket from Claim to completion. True when verified."""
    switch_to_discord()

    claim_loc = locate_element("discord_claim_btn.png", confidence=CONFIDENCE, pick_bottom=True)
    if not claim_loc:
        return False

    # A freshly posted ticket may still be drawing; wait until it is still, then find Claim again
    wait_for_screen_settle(screen_area_around(claim_loc.x, claim_loc.y), settle=0.2, timeout=2, interval=0.05)
    claim_loc = locate_element("discord_claim_btn.png", confidence=CONFIDENCE, pick_bottom=True)
    if not claim_loc:
        return False

    # Check if the newest ticket has the special returning-user warning: Server -> ✅ ⚠️
    embed_region = (max(0, int(claim_loc.x - 120)), max(0, int(claim_loc.y - 160)), 350, 160)
    is_returning_user = has_returning_user_warning(embed_region)

    # Click Claim, then wait until the embed shows Claim -> @you and the Resend Code / Reject buttons
    print("[TICKET] Clicking Claim button...")
    human_click(claim_loc.x, claim_loc.y)
    anchor = wait_for_claim_to_register(claim_loc)
    if anchor is None:
        print("[WARN] Claim did not go through (Claim button still there). Skipping this ticket.")
        return False
    print("[TICKET] Claimed - ticket updated.")

    # SPECIAL CASE: Server -> ✅ ⚠️ (Claim -> Action -> Mark as Verified immediately)
    if is_returning_user:
        print("[SPECIAL CASE] Returning user (✅ ⚠️) detected! Marking as Verified via Action menu...")
        select_discord_action_menu_item("discord_menu_mark_verified.png")
        return False

    # Copy the phone number as-is (leading 0 and spaces are fine, iTunes strips spaces automatically)
    number_region = screen_area_around(anchor.x, anchor.y, left=250, up=170, right=250, down=0)
    phone_number = copy_ticket_value("discord_number_label.png", number_region, extract_phone, NUMBER_BOX_OFFSETS)
    if not phone_number:
        print("[WARN] Could not copy a valid phone number. Leaving this ticket for a human.")
        return False
    print(f"[TICKET] Copied phone number: '{phone_number}'")

    # Switch to iTunes
    switch_to_itunes()

    # Ensure iTunes is on the Add Payment -> Mobile Carrier (+33) screen
    if not wait_for_element("itunes_phone_input.png", timeout=2, confidence=0.80):
        run_itunes_reset_cycle(return_to_discord=False)

    # Click inside the +33 phone number field and paste as-is
    phone_loc = wait_for_element("itunes_phone_input.png", timeout=8, confidence=0.80)
    phone_field = (phone_loc.x + 80, phone_loc.y) if phone_loc else coord("itunes_phone_input_box")
    if not phone_field:
        print("[WARN] Could not find iTunes' phone number field. Leaving this ticket for a human.")
        return False
    human_click(*phone_field)
    replace_field_text(phone_number)

    # Scroll down and click Submit
    human_scroll(-5)
    click_itunes_submit(coord("itunes_submit_phone"))

    print("[ITUNES] Waiting for iTunes to send the code...")
    result = wait_for_any([
        ("itunes_unable_to_send_code.png", 0.80),
        ("itunes_enter_code_input.png", 0.80),
    ], timeout=15)

    # CHECK 1: Did "Unable to Send Code" popup appear?
    if result == "itunes_unable_to_send_code.png":
        print("[ERROR POPUP] 'Unable to Send Code' detected! Resetting iTunes and rejecting ticket...")
        click_element("itunes_popup_ok_btn.png", confidence=0.80, timeout=3)
        run_itunes_reset_cycle(return_to_discord=True)

        # In Discord: click Reject directly if visible; if user submitted code, click Action -> Reject
        reject_loc = wait_for_element("discord_reject_btn.png", timeout=3, confidence=0.82, pick_bottom=True)
        if reject_loc:
            click_and_wait_for_update(reject_loc.x, reject_loc.y, "Reject")
        else:
            select_discord_action_menu_item("discord_menu_reject.png")
        return False

    # CHECK 2: Did iTunes reach the "Enter the verification code" screen?
    if result is None:
        print("[WARN] Did not reach code entry screen. Resetting iTunes...")
        run_itunes_reset_cycle(return_to_discord=True)
        return False

    # Up to 2 attempts to receive and verify the 4-digit SMS code
    previous_code = None
    for attempt in (1, 2):
        code = wait_for_user_code(timeout=CODE_WAIT_TIMEOUT, previous_code=previous_code)

        # If user did not submit a code within 2 minutes:
        if not code:
            print(f"[TIMEOUT] No code submitted on attempt {attempt}. Failing verification...")
            select_discord_action_menu_item("discord_menu_failed_verification.png")
            run_itunes_reset_cycle(return_to_discord=True)
            return False

        # Switch to iTunes, enter the code, and click Submit
        switch_to_itunes()
        code_box = wait_for_element("itunes_enter_code_input.png", timeout=4, confidence=0.80)
        code_field = (code_box.x + 30, code_box.y) if code_box else coord("itunes_enter_code_box")
        if not code_field:
            print("[WARN] Could not find iTunes' code field. Leaving this ticket for a human.")
            return False
        human_click(*code_field)
        replace_field_text(code)

        click_itunes_submit(coord("itunes_submit_code"))

        print("[ITUNES] Waiting for iTunes to check the code...")
        outcome = wait_for_any([
            ("itunes_unable_to_verify_code.png", 0.80),
            ("itunes_billing_issue_banner.png", 0.75),
            ("itunes_mobile_phone_verified.png", 0.80),
        ], timeout=15)

        # OUTCOME A: "Unable to Verify Code" popup (Wrong code entered)
        if outcome == "itunes_unable_to_verify_code.png":
            print(f"[WRONG CODE] 'Unable to Verify Code' on attempt {attempt}!")
            click_element("itunes_popup_ok_btn.png", confidence=0.80, timeout=3)

            if attempt == 1:
                # 1st wrong code: click "Didn't get a verification code?" in iTunes
                print("[RETRY] Clicking 'Didn't get a verification code?' in iTunes...")
                click_element("itunes_didnt_get_code_link.png", confidence=0.80, fallback_coord=coord("itunes_didnt_get_code"), timeout=4)

                # After a code was submitted the ticket only offers Resend Code inside the Action menu
                switch_to_discord()
                print("[RETRY] Clicking Action -> Resend Code in Discord...")
                if select_discord_action_menu_item("discord_menu_resend_code.png"):
                    print("[RETRY] Resend Code clicked! Waiting 2 more minutes for the 2nd code...")
                else:
                    resend_loc = wait_for_element("discord_resend_available.png", timeout=3, confidence=0.85, pick_bottom=True)
                    if resend_loc:
                        click_and_wait_for_update(resend_loc.x, resend_loc.y, "Resend Code")
                        print("[RETRY] Clicked the Resend Code button! Waiting 2 more minutes for the 2nd code...")
                    else:
                        print("[WARN] Could not click Resend Code; still waiting for a new code")
                previous_code = code
                continue
            else:
                # 2nd wrong code: click Failed Verification in Discord and reset iTunes
                print("[FAILED] 2nd wrong code! Clicking Failed Verification and resetting iTunes...")
                switch_to_discord()
                failed_loc = wait_for_element("discord_failed_verification_btn.png", timeout=3, confidence=0.82, pick_bottom=True)
                if failed_loc:
                    click_and_wait_for_update(failed_loc.x, failed_loc.y, "Failed Verification")
                else:
                    select_discord_action_menu_item("discord_menu_failed_verification.png")
                run_itunes_reset_cycle(return_to_discord=True)
                return False

        # OUTCOME B: Red "Billing issue" banner in iTunes
        if outcome == "itunes_billing_issue_banner.png":
            print("[BILLING ISSUE] Billing issue banner detected in iTunes!")
            run_itunes_reset_cycle(return_to_discord=True)
            select_discord_action_menu_item("discord_menu_billing_issue.png")
            return False

        # OUTCOME C: Success! Manage Payments shows Mobile Phone added
        if outcome == "itunes_mobile_phone_verified.png":
            print("[SUCCESS] Mobile Phone added in Manage Payments! Marking the ticket as verified...")
            switch_to_discord()

            # Click Mark as Verified button directly (Action menu only used for ✅⚠️ case)
            verified_loc = wait_for_element("discord_mark_verified_btn.png", timeout=8, confidence=0.82, pick_bottom=True)
            if verified_loc:
                click_and_wait_for_update(verified_loc.x, verified_loc.y, "Mark as Verified")
            else:
                print("[WARN] Mark as Verified button not found")
            return True

        print(f"[WARN] iTunes showed no result after the code on attempt {attempt}")

    return False


# ==============================================================================
# MAIN LOOP
# ==============================================================================
def _cli_args():
    return [arg.strip() for arg in sys.argv[1:]]


def ask_resolution():
    """Which images/<resolution> folder to use: `python bot.py 1920x1080`, or asked at startup."""
    names = list(PROFILES)
    for arg in _cli_args():
        if arg in PROFILES:
            return arg
    detected = "%dx%d" % screen_size()
    default = detected if detected in PROFILES else BASE_PROFILE
    print("Screen resolution:")
    for i, name in enumerate(names, 1):
        print(f"  {i}) {name}" + ("   <- this screen" if name == detected else ""))
    while True:
        try:
            answer = input(f"Choose 1-{len(names)} (Enter = {default}): ").strip()
        except EOFError:
            return default
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(names):
            return names[int(answer) - 1]
        if answer in PROFILES:
            return answer
        print(f"Please type a number from 1 to {len(names)}, or just press Enter.")


def describe_profile():
    own_dir = os.path.join(IMAGES_ROOT, profile_name)
    own = [f for f in os.listdir(own_dir) if f.endswith(".png")] if os.path.isdir(own_dir) else []
    note = "" if profile_name == BASE_PROFILE else f", the rest borrowed from {BASE_PROFILE}"
    print(f"[SETUP] Resolution {profile_name}: {len(own)} image(s) of its own{note}.")
    detected = "%dx%d" % screen_size()
    if detected != profile_name:
        print(f"[WARN] This screen is {detected}, not {profile_name}; images and click spots may not line up.")


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
    print("  DISCORD <-> ITUNES VISUAL AUTOMATION BOT (display scaling 100%)")
    print("  Safety Abort: Slam mouse into ANY of the 4 screen corners.")
    print("==================================================================")
    select_profile(ask_resolution())
    describe_profile()
    limit = ask_verification_limit()
    print(f"[SETUP] Will stop after {limit} verification(s)." if limit else "[SETUP] No limit - runs until you close it.")
    print("Starting in 3 seconds...")
    time.sleep(3)

    verified = 0
    last_itunes_cycle_time = time.time()
    switch_to_discord()

    while True:
        # 1. Check if 10 minutes (600s) have elapsed since the last iTunes cycle
        elapsed = time.time() - last_itunes_cycle_time
        if elapsed >= KEEP_ALIVE_INTERVAL:
            print("[10-MIN TIMER] 10 minutes reached! Running iTunes keep-alive cycle...")
            run_itunes_reset_cycle(return_to_discord=True)

        # 2. A new-ticket notification takes the bot straight to that ticket's channel
        screen = grab_screen()
        if open_ticket_from_notification(screen):
            screen = None

        # 3. Claim and handle the newest ticket on screen
        if locate_element("discord_claim_btn.png", confidence=CONFIDENCE, pick_bottom=True, screen=screen):
            if process_ticket():
                verified += 1
                print(f"[COMPLETE] Verified {verified}" + (f"/{limit}" if limit else "") + ".")
                if limit and verified >= limit:
                    send_done_message()
                    print("[COMPLETE] Verification goal reached. Bot is now exiting.")
                    sys.exit(0)
                # Get iTunes back to the Mobile Carrier form so the next ticket starts right away
                run_itunes_reset_cycle(return_to_discord=True)
            print("[WAIT] Ticket finished. Watching Discord for the next ticket...")

        human_pause(0.15, 0.3)


if __name__ == "__main__":
    main()
