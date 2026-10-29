import os
import re
import sys
import math
import time
import random
import ctypes
import tkinter as tk
import pyautogui

# ==============================================================================
# CONFIGURATION (1440 x 900 Resolution @ 100% Scale)
# ==============================================================================
pyautogui.FAILSAFE = True   # Slam mouse into any of the 4 screen corners to abort
pyautogui.PAUSE = 0.1       # Base pause; the human_* helpers add randomized waits on top

IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
CONFIDENCE = 0.84

# 10-minute timer (600 seconds) for the iTunes keep-alive cycle
KEEP_ALIVE_INTERVAL = 600
# 2-minute timer (120 seconds) waiting for the user's verification code
CODE_WAIT_TIMEOUT = 120

# A Discord embed counts as fully updated once it has looked the same for this long
EMBED_SETTLE_SECONDS = 1.2
# Longest wait for Discord to react to a button click
EMBED_UPDATE_TIMEOUT = 10

# Exact 1440x900 fallback coordinates (used if an element is slightly faded)
COORDS_1440x900 = {
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
}

# Track the last time the iTunes Account -> Manage Payments -> Mobile Carrier cycle ran
last_itunes_cycle_time = time.time()


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def img_path(filename):
    return os.path.join(IMG_DIR, filename)


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
    """Reads current text from the Windows clipboard using built-in tkinter."""
    try:
        r = tk.Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        return text
    except Exception:
        return ""


def set_clipboard_text(text):
    """Writes text directly to the Windows clipboard."""
    try:
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
    except Exception as e:
        print(f"[WARN] Clipboard write error: {e}")


def looks_like_phone(text):
    if re.search(r"[A-Za-z]", text):
        return False
    return 6 <= len(re.sub(r"\D", "", text)) <= 15


def looks_like_code(text):
    return re.fullmatch(r"\d{4,8}", text.strip()) is not None


def locate_element(image_name, confidence=CONFIDENCE, region=None, pick_bottom=False):
    """
    Finds an image on screen.
    If pick_bottom=True, picks the lowest match on screen (newest Discord message).
    """
    path = img_path(image_name)
    try:
        if pick_bottom:
            boxes = list(pyautogui.locateAllOnScreen(path, confidence=confidence, region=region))
            if boxes:
                bottom_box = max(boxes, key=lambda b: b.top)
                return pyautogui.center(bottom_box)
            return None
        else:
            return pyautogui.locateCenterOnScreen(path, confidence=confidence, region=region)
    except Exception:
        return None


def wait_for_element(image_name, timeout=10, confidence=CONFIDENCE, pick_bottom=False, region=None):
    """Waits up to `timeout` seconds for an image to appear and returns its center."""
    start = time.time()
    while time.time() - start < timeout:
        loc = locate_element(image_name, confidence=confidence, region=region, pick_bottom=pick_bottom)
        if loc:
            return loc
        time.sleep(0.4)
    return None


def wait_for_any(candidates, timeout=15):
    """Waits for the first of several (image, confidence) pairs to appear; returns its image name."""
    start = time.time()
    while time.time() - start < timeout:
        for image_name, confidence in candidates:
            if locate_element(image_name, confidence=confidence):
                return image_name
        time.sleep(0.4)
    return None


# ==============================================================================
# HUMAN-LIKE INPUT
# ==============================================================================
def human_pause(low=0.25, high=0.6):
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
    duration = min(0.9, 0.2 + distance / 2000) * random.uniform(0.85, 1.2)
    pyautogui.moveTo(tx, ty, duration=duration, tween=pyautogui.easeOutQuad)
    human_pause(0.08, 0.2)


def human_click(x, y, clicks=1, jitter=2):
    human_move(x, y, jitter=jitter)
    pyautogui.click(clicks=clicks, interval=random.uniform(0.08, 0.13))
    human_pause(0.2, 0.45)


def human_hotkey(*keys):
    pyautogui.hotkey(*keys, interval=random.uniform(0.04, 0.09))
    human_pause(0.15, 0.35)


def human_press(key):
    pyautogui.press(key)
    human_pause(0.12, 0.3)


def human_type(text):
    for ch in text:
        pyautogui.write(ch)
        time.sleep(random.uniform(0.05, 0.16))


def human_scroll(notches):
    """Scrolls one wheel notch at a time (120 units each); negative scrolls down."""
    step = -120 if notches < 0 else 120
    for _ in range(abs(notches)):
        pyautogui.scroll(step)
        time.sleep(random.uniform(0.06, 0.14))
    human_pause(0.4, 0.8)


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
    """Clears the focused input and pastes `text`, pausing between steps like a person."""
    human_hotkey("ctrl", "a")
    human_press("backspace")
    set_clipboard_text(text)
    human_pause(0.1, 0.25)
    human_hotkey("ctrl", "v")
    human_pause(0.3, 0.6)


def copy_selection(timeout=2.0):
    """Presses Ctrl+C, then waits for the text to actually land on the clipboard."""
    human_hotkey("ctrl", "c")
    start = time.time()
    while time.time() - start < timeout:
        text = get_clipboard_text().strip()
        if text:
            return text
        time.sleep(0.15)
    return ""


# ==============================================================================
# WAITING FOR DISCORD TO UPDATE
# ==============================================================================
def _grab(region):
    try:
        return pyautogui.screenshot(region=region).tobytes()
    except Exception:
        return None


def screen_area_around(x, y, left=120, up=220, right=260, down=40):
    # Kept tight below the button so the chat box's animated "is typing" dots stay outside it
    try:
        screen_w, screen_h = pyautogui.size()
    except Exception:
        screen_w, screen_h = 1440, 900
    x0, y0 = max(0, int(x) - left), max(0, int(y) - up)
    x1, y1 = min(screen_w, int(x) + right), min(screen_h, int(y) + down)
    return (x0, y0, x1 - x0, y1 - y0)


def wait_for_screen_change(region, before, timeout=EMBED_UPDATE_TIMEOUT, interval=0.25):
    start = time.time()
    while time.time() - start < timeout:
        now = _grab(region)
        if now is not None and now != before:
            return True
        time.sleep(interval)
    return False


def wait_for_screen_settle(region, settle=EMBED_SETTLE_SECONDS, timeout=EMBED_UPDATE_TIMEOUT, interval=0.25):
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
    wait_for_screen_settle(region, settle=0.4, timeout=2, interval=0.1)
    before = _grab(region)
    pyautogui.click()
    if not wait_for_screen_change(region, before):
        print(f"[WARN] Discord did not react to {what} within {EMBED_UPDATE_TIMEOUT}s")
    elif not wait_for_screen_settle(region):
        print(f"[WARN] Discord kept changing after {what}; continuing anyway")
    human_pause(0.3, 0.6)


# ==============================================================================
# WINDOW SWITCHING (Right Discord Icon & iTunes)
# ==============================================================================
def wait_for_window(name, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        if name in get_active_window_title():
            return True
        time.sleep(0.2)
    return False


def switch_to_discord():
    """Brings the Right Discord instance to the foreground without minimizing it."""
    title = get_active_window_title()
    if "Discord" in title or locate_element("discord_chat_input.png", confidence=0.80):
        return
    print("[SWITCH] Clicking Right Discord icon on taskbar...")
    # Look in the taskbar region (bottom 55 pixels of 1440x900 screen)
    loc = locate_element("taskbar_discord_right.png", confidence=0.80, region=(450, 845, 200, 55))
    human_click(*(loc or COORDS_1440x900["taskbar_discord_right"]))
    if not wait_for_window("Discord"):
        print("[WARN] Discord window did not come to the front")
    human_pause(0.5, 0.9)  # let it repaint


def switch_to_itunes():
    """Brings iTunes to the foreground from minimized/background state."""
    title = get_active_window_title()
    if "iTunes" in title or locate_element("itunes_menu_account.png", confidence=0.82):
        return
    print("[SWITCH] Clicking iTunes icon on taskbar...")
    loc = locate_element("taskbar_itunes.png", confidence=0.80, region=(750, 845, 200, 55))
    human_click(*(loc or COORDS_1440x900["taskbar_itunes"]))
    if not wait_for_window("iTunes"):
        print("[WARN] iTunes window did not come to the front")
    human_pause(0.6, 1.0)  # let it repaint


# ==============================================================================
# ITUNES NAVIGATION & RESET CYCLE (Resets 10-Minute Timer to 0)
# ==============================================================================
def run_itunes_reset_cycle(return_to_discord=True):
    """
    Navigates iTunes:
    Account (if not already on Account Settings) -> View My Account -> Manage Payments -> Mobile Carrier icon.
    Resets the 10-minute keep-alive timer back to 0:00.
    """
    global last_itunes_cycle_time
    print("[ITUNES CYCLE] Resetting iTunes to Mobile Carrier Add Payment screen...")
    switch_to_itunes()
    human_pause(0.5, 0.9)

    # Dismiss any leftover popup first
    if locate_element("itunes_popup_ok_btn.png", confidence=0.82):
        click_element("itunes_popup_ok_btn.png", confidence=0.82)
        human_pause(0.6, 1.0)

    # Step 2 rule: If not already on Account Settings, click Account -> View My Account...
    if not wait_for_element("itunes_account_settings_header.png", timeout=2, confidence=0.82):
        print("[ITUNES CYCLE] Clicking Account -> View My Account...")
        click_element("itunes_menu_account.png", fallback_coord=COORDS_1440x900["itunes_menu_account"])
        if not click_element("itunes_menu_view_account.png", timeout=4):
            # Fallback: View My Account is ~70px below Account menu
            human_click(COORDS_1440x900["itunes_menu_account"][0] + 20, COORDS_1440x900["itunes_menu_account"][1] + 72)

    # Click Manage Payments once the account page has loaded
    if wait_for_element("itunes_manage_payments_link.png", timeout=10):
        print("[ITUNES CYCLE] Clicking Manage Payments...")
        click_element("itunes_manage_payments_link.png", fallback_coord=COORDS_1440x900["itunes_manage_payments"])

    # Manage Payments shows either the existing list ("Add Payment") or the payment-type picker
    page = wait_for_any([("itunes_add_payment_btn.png", 0.82), ("itunes_mobile_carrier_icon.png", CONFIDENCE)], timeout=10)
    if page == "itunes_add_payment_btn.png":
        print("[ITUNES CYCLE] Clicking Add Payment...")
        click_element("itunes_add_payment_btn.png", confidence=0.82)

    # Select Mobile Carrier icon, then wait for the phone form to load
    if wait_for_element("itunes_mobile_carrier_icon.png", timeout=10):
        print("[ITUNES CYCLE] Selecting Mobile Carrier icon...")
        click_element("itunes_mobile_carrier_icon.png", fallback_coord=COORDS_1440x900["itunes_mobile_carrier"])
        wait_for_element("itunes_phone_input.png", timeout=8, confidence=0.80)

    # Reset the 10-minute timer to 0 because the full cycle just completed!
    last_itunes_cycle_time = time.time()
    print("[TIMER] 10-minute keep-alive timer reset to 0:00.")

    if return_to_discord:
        switch_to_discord()


# ==============================================================================
# DISCORD TEXT EXTRACTION & ACTIONS
# ==============================================================================
def copy_value_next_to_label(label_img, x_offset=65, is_valid=bool):
    """
    Finds `Number ->` or `Code ->` on the newest ticket embed, double-clicks the value
    to its right and copies it. Returns "" if nothing valid could be copied.
    """
    loc = None
    for attempt in (1, 2):
        loc = wait_for_element(label_img, timeout=8, confidence=0.82, pick_bottom=True)
        if not loc:
            print(f"[WARN] Could not find {label_img} on the ticket")
            return ""
        set_clipboard_text("")
        human_click(loc.x + x_offset, loc.y, clicks=2, jitter=1)
        copied = copy_selection()
        if is_valid(copied):
            return copied
        print(f"[WARN] Double-click copied '{copied}', which is not a valid value (try {attempt}/2)")
        human_pause(0.6, 1.0)

    # Last resort: drag across the value
    set_clipboard_text("")
    human_move(loc.x + 38, loc.y, jitter=0)
    pyautogui.dragTo(loc.x + 145, loc.y, duration=random.uniform(0.35, 0.55), button="left")
    human_pause(0.15, 0.3)
    copied = copy_selection()
    return copied if is_valid(copied) else ""


def select_discord_action_menu_item(menu_item_img):
    """Clicks the Action dropdown on the newest ticket and selects the specified option."""
    switch_to_discord()
    human_pause(0.3, 0.6)
    print(f"[DISCORD] Opening Action dropdown for {menu_item_img}...")
    action_loc = wait_for_element("discord_action_dropdown.png", timeout=8, confidence=0.80, pick_bottom=True)
    if not action_loc:
        print("[WARN] Could not find Action dropdown button")
        return False
    human_click(action_loc.x, action_loc.y)

    loc = wait_for_element(menu_item_img, timeout=6, confidence=0.78, pick_bottom=True)
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


def wait_for_user_code(timeout=CODE_WAIT_TIMEOUT):
    """
    Waits up to `timeout` seconds (2 minutes) for the user to submit their verification code.
    Watches for either the Windows notification (`notif_code_submitted.png`) or
    the Discord embed updating to show `Mark as Verified` (`discord_mark_verified_btn.png`).
    """
    print(f"[WAIT] Waiting up to {timeout}s for user to submit verification code...")
    start = time.time()

    while time.time() - start < timeout:
        # 1. Check if Windows notification popped up showing "Submitted code:"
        if locate_element("notif_code_submitted.png", confidence=0.80):
            print("[DETECTED] Code submission notification seen!")
            switch_to_discord()
            human_pause(0.8, 1.2)

        # 2. Periodically check Discord embed directly (every ~4s) so we never miss a code
        if int(time.time() - start) % 4 == 0:
            switch_to_discord()
            human_pause(0.4, 0.8)

        # When a user submits a code, the green "Mark as Verified" button appears on the embed
        mark_loc = locate_element("discord_mark_verified_btn.png", confidence=0.82, pick_bottom=True)
        if mark_loc:
            # Let the embed finish updating before reading the code from it
            wait_for_screen_settle(screen_area_around(mark_loc.x, mark_loc.y))
            raw_code = copy_value_next_to_label("discord_code_label.png", x_offset=55, is_valid=looks_like_code)
            if raw_code:
                digits = re.sub(r"\D", "", raw_code)
                print(f"[CODE COPIED] Extracted verification code: {digits}")
                return digits

        time.sleep(1.0)

    print("[TIMEOUT] 2 minutes elapsed without a valid code submission.")
    return None


def has_returning_user_warning(embed_region):
    """True only when the Server line shows ✅ followed by ⚠️; ✅ alone is a normal ticket."""
    try:
        box = pyautogui.locateOnScreen(img_path("discord_server_line.png"), confidence=0.83, region=embed_region)
    except Exception:
        box = None
    if not box:
        return False
    # ⚠️ is too small a part of the line for template matching to tell apart, so count
    # its yellow pixels in the strip just right of the ✅ instead.
    strip = (int(box.left + box.width), max(0, int(box.top) - 2), 20, int(box.height) + 4)
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
    """Handles a single Discord verification ticket from Claim to completion."""
    switch_to_discord()
    human_pause(0.3, 0.6)

    claim_loc = locate_element("discord_claim_btn.png", confidence=0.84, pick_bottom=True)
    if not claim_loc:
        return False

    # Let a freshly posted ticket finish rendering, then find its Claim button again
    wait_for_screen_settle(screen_area_around(claim_loc.x, claim_loc.y), timeout=5)
    claim_loc = locate_element("discord_claim_btn.png", confidence=0.84, pick_bottom=True)
    if not claim_loc:
        return False

    # Check if the newest ticket has the special returning-user warning: Server -> ✅ ⚠️
    embed_region = (max(0, int(claim_loc.x - 120)), max(0, int(claim_loc.y - 160)), 350, 160)
    is_returning_user = has_returning_user_warning(embed_region)

    # Click Claim and wait for Discord to finish updating the embed
    print("[TICKET] Clicking Claim button...")
    click_and_wait_for_update(claim_loc.x, claim_loc.y, "Claim")

    # SPECIAL CASE: Server -> ✅ ⚠️ (Claim -> Action -> Mark as Verified immediately)
    if is_returning_user:
        print("[SPECIAL CASE] Returning user (✅ ⚠️) detected! Marking as Verified via Action menu...")
        select_discord_action_menu_item("discord_menu_mark_verified.png")
        return False

    # Copy the phone number as-is (leading 0 is fine, iTunes strips spaces automatically)
    phone_number = copy_value_next_to_label("discord_number_label.png", x_offset=65, is_valid=looks_like_phone)
    if not phone_number:
        print("[WARN] Could not read phone number from embed. Retrying copy...")
        human_pause(0.8, 1.2)
        phone_number = copy_value_next_to_label("discord_number_label.png", x_offset=75, is_valid=looks_like_phone)
    print(f"[TICKET] Copied phone number: '{phone_number}'")

    # Switch to iTunes
    switch_to_itunes()

    # Ensure iTunes is on the Add Payment -> Mobile Carrier (+33) screen
    if not wait_for_element("itunes_phone_input.png", timeout=3, confidence=0.80):
        run_itunes_reset_cycle(return_to_discord=False)

    # Click inside the +33 phone number field and paste as-is
    phone_loc = wait_for_element("itunes_phone_input.png", timeout=8, confidence=0.80)
    if phone_loc:
        human_click(phone_loc.x + 80, phone_loc.y)
    else:
        human_click(*COORDS_1440x900["itunes_phone_input_box"])
    replace_field_text(phone_number)

    # Scroll down and click Submit
    human_scroll(-5)
    click_element("itunes_submit_btn.png", confidence=0.82, fallback_coord=COORDS_1440x900["itunes_submit_phone"], timeout=4)

    print("[ITUNES] Waiting for iTunes to send the code...")
    result = wait_for_any([
        ("itunes_unable_to_send_code.png", 0.80),
        ("itunes_enter_code_input.png", 0.80),
    ], timeout=15)

    # CHECK 1: Did "Unable to Send Code" popup appear?
    if result == "itunes_unable_to_send_code.png":
        print("[ERROR POPUP] 'Unable to Send Code' detected! Resetting iTunes and rejecting ticket...")
        click_element("itunes_popup_ok_btn.png", confidence=0.80, timeout=3)
        human_pause(0.6, 1.0)
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
    for attempt in (1, 2):
        code = wait_for_user_code(timeout=CODE_WAIT_TIMEOUT)

        # If user did not submit a code within 2 minutes:
        if not code:
            print(f"[TIMEOUT] No code submitted on attempt {attempt}. Failing verification...")
            select_discord_action_menu_item("discord_menu_failed_verification.png")
            run_itunes_reset_cycle(return_to_discord=True)
            return False

        # Switch to iTunes, enter the code, and click Submit
        switch_to_itunes()
        code_box = wait_for_element("itunes_enter_code_input.png", timeout=5, confidence=0.80)
        if code_box:
            human_click(code_box.x + 30, code_box.y)
        else:
            human_click(*COORDS_1440x900["itunes_enter_code_box"])
        replace_field_text(code)

        click_element("itunes_submit_btn.png", confidence=0.82, fallback_coord=COORDS_1440x900["itunes_submit_code"], timeout=4)

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
            human_pause(0.6, 1.0)

            if attempt == 1:
                # 1st wrong code: click "Didn't get a verification code?" in iTunes
                print("[RETRY] Clicking 'Didn't get a verification code?' in iTunes...")
                click_element("itunes_didnt_get_code_link.png", confidence=0.80, fallback_coord=COORDS_1440x900["itunes_didnt_get_code"], timeout=4)
                human_pause(0.8, 1.2)

                # Switch to Discord and wait for Resend Code button to become available/bright
                switch_to_discord()
                print("[RETRY] Waiting for Discord 'Resend Code' button to become available...")
                resend_loc = wait_for_element("discord_resend_available.png", timeout=30, confidence=0.85, pick_bottom=True)
                if resend_loc:
                    click_and_wait_for_update(resend_loc.x, resend_loc.y, "Resend Code")
                    print("[RETRY] Clicked 'Resend Code'! Waiting 2 more minutes for 2nd code...")
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
            print("[SUCCESS] Mobile Phone added in Manage Payments! Completing final Discord steps...")
            switch_to_discord()

            # Click Mark as Verified button directly (Action menu only used for ✅⚠️ case)
            verified_loc = wait_for_element("discord_mark_verified_btn.png", timeout=8, confidence=0.82, pick_bottom=True)
            if verified_loc:
                click_and_wait_for_update(verified_loc.x, verified_loc.y, "Mark as Verified")
            else:
                print("[WARN] Mark as Verified button not found")

            # Type "im the bot and done" in the channel chat bar and stop claiming!
            if click_element("discord_chat_input.png", confidence=0.80, timeout=5):
                human_type("im the bot and done")
                human_pause(0.3, 0.6)
                human_press("enter")
                print("[FINISHED] Typed 'im the bot and done'. Stopping bot completely!")
            return True

        print(f"[WARN] iTunes showed no result after the code on attempt {attempt}")

    return False


# ==============================================================================
# MAIN LOOP
# ==============================================================================
def main():
    global last_itunes_cycle_time
    print("==================================================================")
    print("  DISCORD <-> ITUNES VISUAL AUTOMATION BOT (1440x900 @ 100%)")
    print("  Safety Abort: Slam mouse into ANY of the 4 screen corners.")
    print("==================================================================")
    print("Starting in 3 seconds...")
    time.sleep(3)

    last_itunes_cycle_time = time.time()
    switch_to_discord()

    while True:
        # 1. Check if 10 minutes (600s) have elapsed since the last iTunes cycle
        elapsed = time.time() - last_itunes_cycle_time
        if elapsed >= KEEP_ALIVE_INTERVAL:
            print("[10-MIN TIMER] 10 minutes reached! Running iTunes keep-alive cycle...")
            run_itunes_reset_cycle(return_to_discord=True)

        # 2. Watch for a new ticket (either on Discord screen or Windows toast notification)
        if locate_element("notif_new_ticket_blue.png", confidence=0.80) or locate_element("notif_new_ticket_purple.png", confidence=0.80):
            switch_to_discord()

        if locate_element("discord_claim_btn.png", confidence=0.84, pick_bottom=True):
            done = process_ticket()
            if done:
                print("[COMPLETE] Verification goal achieved. Bot is now exiting.")
                sys.exit(0)
            print("[WAIT] Ticket finished. Watching Discord for the next ticket...")

        human_pause(0.8, 1.3)


if __name__ == "__main__":
    main()
