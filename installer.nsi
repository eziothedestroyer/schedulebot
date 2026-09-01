Unicode True
Name "ScheduleBot Creator Edition"
OutFile "dist\ScheduleBot-Setup-1.0.0.exe"
InstallDir "$LOCALAPPDATA\ScheduleBot"
RequestExecutionLevel user
Icon "schedulebot-icon.ico"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "windows-dist\ScheduleBot.exe"
  CreateShortcut "$DESKTOP\ScheduleBot.lnk" "$INSTDIR\ScheduleBot.exe"
  CreateDirectory "$SMPROGRAMS\ScheduleBot"
  CreateShortcut "$SMPROGRAMS\ScheduleBot\ScheduleBot.lnk" "$INSTDIR\ScheduleBot.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "DisplayName" "ScheduleBot Creator Edition"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "UninstallString" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\ScheduleBot.lnk"
  Delete "$SMPROGRAMS\ScheduleBot\ScheduleBot.lnk"
  RMDir "$SMPROGRAMS\ScheduleBot"
  Delete "$INSTDIR\ScheduleBot.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot"
SectionEnd
