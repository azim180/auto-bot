========================================================================
DISCORD + ITUNES VISUAL BOT (Windows display scaling 100%)
========================================================================

INCLUDED IN THIS FOLDER:
1. bot.py                   - Complete visual automation bot script
2. images/1440x900/         - Cropped visual cue images for a 1440 x 900 screen
3. images/1920x1080/        - Images for a 1920 x 1080 screen (see its README)
4. install_requirements.bat - One-click installer for OpenCV & Pillow
5. start_bot.bat            - One-click launcher for the bot

HOW TO RUN:
1. Extract this entire ZIP folder anywhere on your PC.
2. Double-click "install_requirements.bat" once to make sure opencv-python
   and pillow are installed alongside pyautogui.
3. Open Discord (the right Discord icon on your taskbar, inside #code-farm)
   and open iTunes in the background.
4. Double-click "start_bot.bat" (or run `python bot.py` in terminal).
5. It asks your screen resolution: 1) 1440x900 or 2) 1920x1080. Pressing
   Enter picks the one that matches this screen.
6. It asks how many verifications to do: type 1, 2, 3 ... or just press Enter
   for no limit. After that many verifications it types "im the bot and done"
   and stops.
   (Shortcut: `python bot.py 2 1920x1080` skips both questions.)

SCREEN RESOLUTION:
The bot finds buttons by comparing small cropped images, pixel for pixel, so
Windows display scaling must be 100% and Discord must use its dark theme.
Each resolution has its own folder in images/. An image missing from the
1920x1080 folder is borrowed from 1440x900 (buttons are the same size at 100%
scaling), so only re-crop the ones the bot cannot find. Fixed backup click
spots exist for 1440x900 only; on 1920x1080 the bot only clicks what it sees.

SAFETY STOP:
Slam your mouse cursor into ANY of the 4 corners of your monitor at any
time to immediately stop the bot.
