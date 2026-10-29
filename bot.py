import os
import re
import sys
import time
import ctypes
import tkinter as tk
import pyautogui

# ==============================================================================
# CONFIGURATION (1440 x 900 Resolution @ 100% Scale)
# ==============================================================================
pyautogui.FAILSAFE = True   # Slam mouse into any of the 4 screen corners to abort
pyautogui.PAUSE = 0.25      # Short pause between actions

IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
CONFIDENCE = 0.84

# 10-minute timer (600 seconds) for the iTunes keep-alive cycle
KEEP_ALIVE_INTERVAL = 600
# 2-minute timer (120 seconds) waiting for the user's verification code
CODE_WAIT_TIMEOUT = 120

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


def click_element(image_name, confidence=CONFIDENCE, region=None, pick_bottom=False, fallback_coord=None):
    """Finds and clicks an image, or uses fallback_coord if provided."""
    loc = locate_element(image_name, confidence=confidence, region=region, pick_bottom=pick_bottom)
    if loc:
        pyautogui.moveTo(loc.x, loc.y, duration=0.2)
        pyautogui.click()
        return loc
    if fallback_coord:
        print(f"[INFO] Using 1440x900 fallback coordinate {fallback_coord} for {image_name}")
        pyautogui.moveTo(fallback_coord[0], fallback_coord[1], duration=0.2)
        pyautogui.click()
        return fallback_coord
    return None


def wait_for_element(image_name, timeout=10, confidence=CONFIDENCE, pick_bottom=False):
    """Waits up to `timeout` seconds for an image to appear and returns its center."""
    start = time.time()
    while time.time() - start < timeout:
        loc = locate_element(image_name, confidence=confidence, pick_bottom=pick_bottom)
        if loc:
            return loc
        time.sleep(0.5)
    return None


# ==============================================================================
# WINDOW SWITCHING (Right Discord Icon & iTunes)
# ==============================================================================
def switch_to_discord():
    """Brings the Right Discord instance to the foreground without minimizing it."""
    title = get_active_window_title()
    if "Discord" in title or locate_element("discord_chat_input.png", confidence=0.80):
        return
    print("[SWITCH] Clicking Right Discord icon on taskbar...")
    # Look in the taskbar region (bottom 55 pixels of 1440x900 screen)
    loc = locate_element("taskbar_discord_right.png", confidence=0.80, region=(450, 845, 200, 55))
    if loc:
        pyautogui.click(loc.x, loc.y)
    else:
        pyautogui.click(*COORDS_1440x900["taskbar_discord_right"])
    time.sleep(1.0)


def switch_to_itunes():
    """Brings iTunes to the foreground from minimized/background state."""
    title = get_active_window_title()
    if "iTunes" in title or locate_element("itunes_menu_account.png", confidence=0.82):
        return
    print("[SWITCH] Clicking iTunes icon on taskbar...")
    loc = locate_element("taskbar_itunes.png", confidence=0.80, region=(750, 845, 200, 55))
    if loc:
        pyautogui.click(loc.x, loc.y)
    else:
        pyautogui.click(*COORDS_1440x900["taskbar_itunes"])
    time.sleep(1.2)


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
    time.sleep(0.8)

    # Dismiss any leftover popup first
    if locate_element("itunes_popup_ok_btn.png", confidence=0.82):
        click_element("itunes_popup_ok_btn.png", confidence=0.82)
        time.sleep(0.8)

    # Step 2 rule: If not already on Account Settings, click Account -> View My Account...
    if not locate_element("itunes_account_settings_header.png", confidence=0.82):
        print("[ITUNES CYCLE] Clicking Account -> View My Account...")
        click_element("itunes_menu_account.png", fallback_coord=COORDS_1440x900["itunes_menu_account"])
        time.sleep(0.8)
        if wait_for_element("itunes_menu_view_account.png", timeout=4):
            click_element("itunes_menu_view_account.png")
        else:
            # Fallback: View My Account is ~70px below Account menu
            pyautogui.click(COORDS_1440x900["itunes_menu_account"][0] + 20, COORDS_1440x900["itunes_menu_account"][1] + 72)
        time.sleep(2.5)

    # Click Manage Payments
    if wait_for_element("itunes_manage_payments_link.png", timeout=8):
        print("[ITUNES CYCLE] Clicking Manage Payments...")
        click_element("itunes_manage_payments_link.png", fallback_coord=COORDS_1440x900["itunes_manage_payments"])
        time.sleep(2.5)

    # If Manage Payments shows existing list with "Add Payment" button, click "Add Payment"
    if locate_element("itunes_add_payment_btn.png", confidence=0.82):
        print("[ITUNES CYCLE] Clicking Add Payment...")
        click_element("itunes_add_payment_btn.png")
        time.sleep(2.0)

    # Select Mobile Carrier icon
    if wait_for_element("itunes_mobile_carrier_icon.png", timeout=8):
        print("[ITUNES CYCLE] Selecting Mobile Carrier icon...")
        click_element("itunes_mobile_carrier_icon.png", fallback_coord=COORDS_1440x900["itunes_mobile_carrier"])
        time.sleep(1.5)

    # Reset the 10-minute timer to 0 because the full cycle just completed!
    last_itunes_cycle_time = time.time()
    print("[TIMER] 10-minute keep-alive timer reset to 0:00.")

    if return_to_discord:
        switch_to_discord()


# ==============================================================================
# DISCORD TEXT EXTRACTION & ACTIONS
# ==============================================================================
def copy_value_next_to_label(label_img, x_offset=65):
    """
    Finds `Number ->` or `Code ->` on the newest ticket embed,
    triple-clicks the value block to its right, and copies it to clipboard.
    """
    loc = locate_element(label_img, confidence=0.82, pick_bottom=True)
    if not loc:
        return ""

    set_clipboard_text("")
    target_x = loc.x + x_offset
    target_y = loc.y

    # Triple-click the inline code block in Discord
    pyautogui.moveTo(target_x, target_y, duration=0.2)
    pyautogui.click(clicks=3, interval=0.08)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.3)

    copied = get_clipboard_text().strip()

    # Fallback drag-select if triple-click missed
    if not copied:
        pyautogui.moveTo(loc.x + 38, target_y, duration=0.15)
        pyautogui.dragTo(loc.x + 145, target_y, duration=0.3, button="left")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.3)
        copied = get_clipboard_text().strip()

    return copied


def select_discord_action_menu_item(menu_item_img):
    """Clicks the Action dropdown on the newest ticket and selects the specified option."""
    switch_to_discord()
    time.sleep(0.5)
    print(f"[DISCORD] Opening Action dropdown for {menu_item_img}...")
    # Wait up to 5s for the Action button to appear (embed may still be updating after claim)
    action_loc = wait_for_element("discord_action_dropdown.png", timeout=5, confidence=0.80)
    if not action_loc:
        print("[WARN] Could not find Action dropdown button")
        return False
    pyautogui.click(action_loc.x, action_loc.y)
    time.sleep(1.5)  # give the dropdown menu time to fully open

    # Open menu rows render on a different shade than the cropped template, so match in
    # grayscale and step the confidence down until the option is found.
    path = img_path(menu_item_img)
    for conf in (0.80, 0.75, 0.70, 0.65):
        try:
            loc = pyautogui.locateCenterOnScreen(path, confidence=conf, grayscale=True)
        except Exception:
            loc = None
        if loc:
            print(f"[DISCORD] Found {menu_item_img} (confidence {conf:.2f}), clicking...")
            pyautogui.click(loc.x, loc.y)
            time.sleep(1.0)
            return True

    debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_dropdown.png")
    try:
        pyautogui.screenshot(debug_path)
        print(f"[WARN] Could not find {menu_item_img} in dropdown menu. Screenshot saved: {debug_path}")
    except Exception:
        print(f"[WARN] Could not find {menu_item_img} in dropdown menu")
    pyautogui.press("escape")  # close the open dropdown
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
            time.sleep(1.0)

        # 2. Periodically check Discord embed directly (every ~4s) so we never miss a code
        if int(time.time() - start) % 4 == 0:
            switch_to_discord()
            time.sleep(0.6)

        # When a user submits a code, the green "Mark as Verified" button appears on the embed
        if locate_element("discord_mark_verified_btn.png", confidence=0.82, pick_bottom=True):
            raw_code = copy_value_next_to_label("discord_code_label.png", x_offset=55)
            digits = "".join(re.findall(r"\d+", raw_code))
            if digits and "second" not in raw_code.lower() and "ago" not in raw_code.lower():
                print(f"[CODE COPIED] Extracted verification code: {digits}")
                return digits

        time.sleep(1.0)

    print("[TIMEOUT] 2 minutes elapsed without a valid code submission.")
    return None


# ==============================================================================
# MAIN TICKET WORKFLOW
# ==============================================================================
def process_ticket():
    """Handles a single Discord verification ticket from Claim to completion."""
    switch_to_discord()
    time.sleep(0.4)

    # Check if the newest ticket has the special returning-user warning: Server -> ✅ ⚠️
    claim_loc = locate_element("discord_claim_btn.png", confidence=0.84, pick_bottom=True)
    if not claim_loc:
        return False

    # Look in a region just above the Claim button for the ✅ ⚠️ indicator
    embed_region = (max(0, int(claim_loc.x - 120)), max(0, int(claim_loc.y - 160)), 350, 160)
    is_returning_user = locate_element("discord_server_returning_warn.png", confidence=0.83, region=embed_region) is not None

    # Click Claim on this ticket
    print("[TICKET] Clicking Claim button...")
    pyautogui.moveTo(claim_loc.x, claim_loc.y, duration=0.2)
    pyautogui.click()
    time.sleep(1.5)

    # SPECIAL CASE: Server -> ✅ ⚠️ (Claim -> Action -> Mark as Verified immediately)
    if is_returning_user:
        print("[SPECIAL CASE] Returning user (✅ ⚠️) detected! Marking as Verified via Action menu...")
        time.sleep(1.0)  # extra wait for embed to update after claim
        select_discord_action_menu_item("discord_menu_mark_verified.png")
        return False

    # Copy the phone number as-is (leading 0 is fine, iTunes strips spaces automatically)
    phone_number = copy_value_next_to_label("discord_number_label.png", x_offset=65)
    print(f"[TICKET] Copied phone number: '{phone_number}'")
    if not phone_number:
        print("[WARN] Could not read phone number from embed. Retrying copy...")
        time.sleep(0.8)
        phone_number = copy_value_next_to_label("discord_number_label.png", x_offset=75)

    # Switch to iTunes
    switch_to_itunes()
    time.sleep(0.8)

    # Ensure iTunes is on the Add Payment -> Mobile Carrier (+33) screen
    if not locate_element("itunes_phone_input.png", confidence=0.80):
        run_itunes_reset_cycle(return_to_discord=False)

    # Click inside the +33 phone number field and paste as-is
    phone_loc = locate_element("itunes_phone_input.png", confidence=0.80)
    if phone_loc:
        pyautogui.click(phone_loc.x + 80, phone_loc.y)
    else:
        pyautogui.click(*COORDS_1440x900["itunes_phone_input_box"])

    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    set_clipboard_text(phone_number)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)

    # Scroll down and click Submit
    pyautogui.scroll(-600)
    time.sleep(0.6)
    click_element("itunes_submit_btn.png", confidence=0.82, fallback_coord=COORDS_1440x900["itunes_submit_phone"])
    time.sleep(2.5)

    # CHECK 1: Did "Unable to Send Code" popup appear?
    if locate_element("itunes_unable_to_send_code.png", confidence=0.80):
        print("[ERROR POPUP] 'Unable to Send Code' detected! Resetting iTunes and rejecting ticket...")
        click_element("itunes_popup_ok_btn.png", confidence=0.80)
        time.sleep(0.8)
        run_itunes_reset_cycle(return_to_discord=True)

        # In Discord: click Reject directly if visible; if user submitted code, click Action -> Reject
        if locate_element("discord_reject_btn.png", confidence=0.82, pick_bottom=True):
            click_element("discord_reject_btn.png", confidence=0.82, pick_bottom=True)
        else:
            select_discord_action_menu_item("discord_menu_reject.png")
        return False

    # CHECK 2: Wait for "Enter the verification code" screen in iTunes
    if not wait_for_element("itunes_enter_code_input.png", timeout=8, confidence=0.80):
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
        time.sleep(0.6)
        code_box = locate_element("itunes_enter_code_input.png", confidence=0.80)
        if code_box:
            pyautogui.click(code_box.x + 30, code_box.y)
        else:
            pyautogui.click(*COORDS_1440x900["itunes_enter_code_box"])

        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        set_clipboard_text(code)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.4)

        click_element("itunes_submit_btn.png", confidence=0.82, fallback_coord=COORDS_1440x900["itunes_submit_code"])
        time.sleep(3.0)

        # OUTCOME A: "Unable to Verify Code" popup (Wrong code entered)
        if locate_element("itunes_unable_to_verify_code.png", confidence=0.80):
            print(f"[WRONG CODE] 'Unable to Verify Code' on attempt {attempt}!")
            click_element("itunes_popup_ok_btn.png", confidence=0.80)
            time.sleep(0.8)

            if attempt == 1:
                # 1st wrong code: click "Didn't get a verification code?" in iTunes
                print("[RETRY] Clicking 'Didn't get a verification code?' in iTunes...")
                click_element("itunes_didnt_get_code_link.png", confidence=0.80, fallback_coord=COORDS_1440x900["itunes_didnt_get_code"])
                time.sleep(1.0)

                # Switch to Discord and wait for Resend Code button to become available/bright
                switch_to_discord()
                print("[RETRY] Waiting for Discord 'Resend Code' button to become available...")
                resend_loc = wait_for_element("discord_resend_available.png", timeout=30, confidence=0.85, pick_bottom=True)
                if resend_loc:
                    pyautogui.click(resend_loc.x, resend_loc.y)
                    print("[RETRY] Clicked 'Resend Code'! Waiting 2 more minutes for 2nd code...")
                    time.sleep(1.5)
                continue
            else:
                # 2nd wrong code: click Failed Verification in Discord and reset iTunes
                print("[FAILED] 2nd wrong code! Clicking Failed Verification and resetting iTunes...")
                switch_to_discord()
                time.sleep(0.6)
                if locate_element("discord_failed_verification_btn.png", confidence=0.82, pick_bottom=True):
                    click_element("discord_failed_verification_btn.png", confidence=0.82, pick_bottom=True)
                else:
                    select_discord_action_menu_item("discord_menu_failed_verification.png")
                run_itunes_reset_cycle(return_to_discord=True)
                return False

        # OUTCOME B: Red "Billing issue" banner in iTunes
        if locate_element("itunes_billing_issue_banner.png", confidence=0.75):
            print("[BILLING ISSUE] Billing issue banner detected in iTunes!")
            run_itunes_reset_cycle(return_to_discord=True)
            select_discord_action_menu_item("discord_menu_billing_issue.png")
            return False

        # OUTCOME C: Success! Manage Payments shows Mobile Phone added
        if wait_for_element("itunes_mobile_phone_verified.png", timeout=6, confidence=0.80):
            print("[SUCCESS] Mobile Phone added in Manage Payments! Completing final Discord steps...")
            switch_to_discord()
            time.sleep(0.8)

            # Click Mark as Verified button directly (Action menu only used for ✅⚠️ case)
            click_element("discord_mark_verified_btn.png", confidence=0.82, pick_bottom=True)
            time.sleep(1.2)

            # Type "im the bot and done" in the channel chat bar and stop claiming!
            if click_element("discord_chat_input.png", confidence=0.80):
                time.sleep(0.4)
                pyautogui.write("im the bot and done", interval=0.04)
                pyautogui.press("enter")
                print("[FINISHED] Typed 'im the bot and done'. Stopping bot completely!")
            return True

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

        time.sleep(1.0)


if __name__ == "__main__":
    main()
