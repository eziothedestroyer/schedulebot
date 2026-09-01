# -*- mode: python ; coding: utf-8 -*-
import sys
a = Analysis(['app.py'], pathex=[], binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='ScheduleBot', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=True, console=False,
          icon='schedulebot-icon.ico' if sys.platform == 'win32' else 'schedulebot-icon.png',
          version='version_info.txt' if sys.platform == 'win32' else None)
