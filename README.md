# ScheduleBot

[![Build Windows EXE](https://github.com/eziothedestroyer/schedulebot/actions/workflows/build-windows.yml/badge.svg)](https://github.com/eziothedestroyer/schedulebot/actions/workflows/build-windows.yml)

A small offline Windows scheduling app. Type requests such as:

- `Study tomorrow at 7 pm for 2 hours`
- `Gym every Monday at 6:30 am`
- `Dentist September 5 at 2:30 pm`

Tasks are saved on the computer. The schedule can be exported to CSV or an `.ics`
file that opens in Outlook, Google Calendar, and Apple Calendar. Scheduling itself
does not require an account or API key.

The schedule view supports live task search, hiding completed work, bulk completion
and deletion, and editing by selecting a task or double-clicking it. The edit window
can change the title, date, time, duration, and weekly recurrence.

Streaming Studio also supports OBS WebSocket controls, Discord announcements,
YouTube/Twitch planning, resumable YouTube video and VOD uploads, VTuber workflows,
local editing, and AI-assisted VOD highlights.
External services require
the user's own credentials and authorization. Secrets are stored in the operating
system credential vault and are not written to `schedule.json`.
See `PUBLIC_SETUP.md` for integration setup, privacy, and distribution guidance.

## Download

Download public builds from the [GitHub Releases page](https://github.com/eziothedestroyer/schedulebot/releases).
Verify the downloaded executable against the accompanying `.sha256` file before running it.
Until a code-signed installer is published, Windows may display a SmartScreen warning.

## Run from Python

Python 3.10 or newer is recommended. From this folder, run:

```shell
python app.py
```

## Make the Windows `.exe`

On Windows, double-click `build.bat`. The finished file will be:

```text
dist\ScheduleBot.exe
```

Alternatively, upload this project to GitHub and open **Actions → Build Windows
EXE → Run workflow**. Download the `ScheduleBot-Windows` artifact when it finishes.
GitHub-hosted artifacts are temporary; for a public download, attach the `.exe` to
a GitHub Release.

Windows may show a SmartScreen warning for unsigned, newly downloaded programs.
Code-signing the `.exe` is the normal way to remove that warning.

## Build on Arch Linux

Run:

```shell
chmod +x build-arch.sh
./build-arch.sh
```

The standalone native program will be at `dist/ScheduleBot`. It does not require
Python on the computer where it runs. The build needs Python, Tk, and a working C
toolchain; on Arch these are available with `sudo pacman -S python tk base-devel`.

## Tests

```shell
python -m unittest discover -s tests -v
```

## Privacy and support

- [Privacy policy](https://eziothedestroyer.github.io/schedulebot/privacy.html)
- [Terms of service](https://eziothedestroyer.github.io/schedulebot/terms.html)
- [Report a problem](https://github.com/eziothedestroyer/schedulebot/issues)
