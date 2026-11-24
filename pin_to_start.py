import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROGRAMS_USER = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
PROGRAMS_ALL = Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs")
DESKTOP_DIR = Path(os.environ["USERPROFILE"]) / "Desktop"

TARGET_EXE = BASE_DIR / "Kuro.exe"
ICON_PATH = BASE_DIR / "kuro.ico"

def install_all_shortcuts():
    # PowerShell script to create shortcuts pointing directly to Kuro.exe
    ps_code = f"""
    $WshShell = New-Object -ComObject WScript.Shell

    $locations = @(
        '{str(PROGRAMS_USER / "Kuro.lnk")}',
        '{str(PROGRAMS_USER / "Kuro Anime Screensaver.lnk")}',
        '{str(PROGRAMS_ALL / "Kuro.lnk")}',
        '{str(DESKTOP_DIR / "Kuro.lnk")}'
    )

    foreach ($loc in $locations) {{
        $s = $WshShell.CreateShortcut($loc)
        $s.TargetPath = '{str(TARGET_EXE)}'
        $s.WorkingDirectory = '{str(BASE_DIR)}'
        $s.IconLocation = '{str(ICON_PATH)},0'
        $s.Description = 'KURO // ANIME - Cinematic Ambient Screensaver'
        $s.Save()
        Write-Output "Created: $loc"
    }}
    """
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, text=True)
    print(res.stdout.strip())
    if res.stderr.strip():
        print("Errors:", res.stderr.strip())

if __name__ == "__main__":
    install_all_shortcuts()
