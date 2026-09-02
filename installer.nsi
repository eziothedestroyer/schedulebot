Unicode True
!include "MUI2.nsh"
!include "version.nsh"

Name "ScheduleBot Creator Edition"
OutFile "dist\ScheduleBot-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\ScheduleBot"
RequestExecutionLevel user
Icon "schedulebot-icon.ico"

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "ScheduleBot Creator Edition"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "FileDescription" "ScheduleBot installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "Publisher" "ScheduleBot"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "dist\ScheduleBot.exe"
  CreateShortcut "$DESKTOP\ScheduleBot.lnk" "$INSTDIR\ScheduleBot.exe"
  CreateDirectory "$SMPROGRAMS\ScheduleBot"
  CreateShortcut "$SMPROGRAMS\ScheduleBot\ScheduleBot.lnk" "$INSTDIR\ScheduleBot.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "DisplayName" "ScheduleBot Creator Edition"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "Publisher" "ScheduleBot"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScheduleBot" "NoRepair" 1
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
