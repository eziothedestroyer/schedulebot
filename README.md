# ScheduleBot

A small offline Windows scheduling app. Type requests such as:

- `Study tomorrow at 7 pm for 2 hours`
- `Gym every Monday at 6:30 am`
- `Dentist September 5 at 2:30 pm`

Tasks are saved on the computer. The schedule can be exported to CSV or an `.ics`
file that opens in Outlook, Google Calendar, and Apple Calendar. No account or API
key is needed.

Streaming Studio also supports OBS WebSocket controls, Discord announcements,
YouTube/Twitch planning, and TikTok desktop authorization plus draft video upload.
For TikTok, register `http://127.0.0.1:*/callback/` as the Desktop redirect URI and
enable Login Kit with `user.info.basic` and Content Posting API `video.upload`.

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
