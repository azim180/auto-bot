========================================================================
DISCORD + ITUNES VISUAL BOT
========================================================================

INCLUDED IN THIS FOLDER:
1. bot.py                   - Complete visual automation bot script
2. images/                  - Cropped visual cue images (one set for every screen)
3. install_requirements.bat - One-click installer (Python if missing + all packages)
4. start_bot.bat            - One-click launcher for the bot
5. find_python.bat          - Finds Python for the other .bat files

HOW TO RUN:
1. Extract this entire ZIP folder anywhere on your PC.
2. Double-click "install_requirements.bat" once. It finds Python even when it
   is not on PATH (or installs Python 3.12 with winget if there is none),
   installs every package, and checks they all load before saying it's done.
3. Open Discord (the right Discord icon on your taskbar, inside #code-farm)
   and open iTunes in the background.
4. Double-click "start_bot.bat" (or run `python bot.py` in terminal).
5. It asks how many verifications to do: type 1, 2, 3 ... or just press Enter
   for no limit. After that many verifications it types "im the bot and done"
   and stops. (Shortcut: `python bot.py 2` skips the question.)

ANY SCREEN, ANY SCALING:
There is no resolution to choose. The bot finds buttons by comparing the
small images in images/, which works on any screen resolution. Windows
display scaling (125%, 150%...) and Discord's zoom make everything bigger,
so at startup and whenever it switches to Discord or iTunes the bot measures
how big that app is drawn and resizes the images to match. The console shows
what it found, e.g. "[SCALE] Discord is drawn at 100% size". 100% scaling is
still the most reliable, because text drawn at another size never matches a
resized image perfectly. Discord must use its dark theme.

You can change the resolution, the scaling or Discord's zoom while the bot
runs: it notices ("[SCREEN] Changed from ..." or "[SCALE] ... measuring it
again") and adjusts on the fly. Best between tickets: a claimed ticket is
recognised by a snapshot of its number, which no longer matches after a
scaling or zoom change (a resolution change alone is fine), so tickets already
claimed at that moment are left for a human.

ANOTHER PC:
- Discord's theme: the box behind the Number and Code values is drawn in
  another colour by other Discord themes. The bot reads that colour from
  every claimed ticket's number box ("[THEME] ..."), so the Code is copied in
  any theme.
- Fonts: a PC can draw some text a pixel wider, so an image cropped on one PC
  can miss on another. Put a crop from that PC next to the original as
  images/<same name>@<anything>.png (e.g. itunes_didnt_get_code_link@1080p.png):
  the bot then tries both. The same is used for iTunes' Code and phone number
  fields while they are selected (thick dark border): *@selected.png.
- Copying: the bot never takes text that was already on the clipboard for a
  new copy, and after pasting the number or code into iTunes it reads the
  field back to check it holds that value (and pastes again if not).

BACKUP CLICK SPOTS:
If a button's image is missed, the bot clicks where it last saw that button
on this screen (it remembers them in learned_spots.json; delete that file if
you move the iTunes window). A 1440x900 screen at 100% also has spots that
were measured by hand. It never clicks a backup spot while a Windows
notification is showing.

NOTIFICATIONS OVER THE SUBMIT BUTTON:
Before clicking iTunes' Submit, the bot closes every Windows notification in
the bottom-right corner by its X, one after another while new ones keep
coming, waiting each time until they stop sliding. It looks again right
before the click, so one that pops up while the mouse is moving is closed
too, instead of being clicked (that would open Discord).

SEVERAL TICKETS AT ONCE:
New tickets are claimed right away, even while the bot is busy with another
one: while it waits for a code in Discord it claims every new ticket it sees,
and while it is in iTunes a new-ticket notification is clicked, the ticket
claimed, and the bot goes back to iTunes and carries on where it was. Claimed
tickets are then handled one after another, oldest first (never more than
the verification goal needs).
Tickets come from two Discord servers, each with a #code-farm:
  server 1 - green cash icon, blue/black notification ("Verification")
  server 2 - grey cash icon, purple notification ("Verification+")
Every claimed ticket remembers its server. When the bot needs a ticket that
is in the other server (after claiming one from a notification, say), it
clicks that server's icon in Discord's server list and carries on there.
At startup it reads which server is open from the white bar Discord draws
next to it (or opens server 1). The icons are images/discord_server1_icon.png
and discord_server2_icon.png - re-crop them if a server changes its icon.
While another claimed ticket is waiting, the current user gets one try: no
code within 1 minute, or a wrong code, and the ticket is failed right away so
the next one can start. With nobody else waiting it is as before: 2 minutes,
and after a wrong code a Resend Code and a second try.

DURING A TICKET:
The bot remembers its ticket by the phone-number box, so new tickets arriving
(and pushing it up the chat) don't confuse it - it scrolls up to it if needed
and back down afterwards. If the ticket's Code shows "Left" (the user left),
it stops that ticket, resets iTunes and waits for the next one.

SAFETY STOP:
Slam your mouse cursor into ANY of the 4 corners of your monitor at any
time to immediately stop the bot.
