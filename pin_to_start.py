import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROGRAMS_USER = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
DESKTOP_DIR = Path(os.environ["USERPROFILE"]) / "Desktop"

def get_pythonw_path() -> str:
    py_dir = Path(sys.executable).parent
    pythonw = py_dir / "pythonw.exe"
    if pythonw.is_file():
        return str(pythonw)
    which_w = shutil.which("pythonw")
    if which_w:
        return which_w
    return sys.executable

TARGET_EXE = get_pythonw_path()
LAUNCHER_PY = BASE_DIR / "launcher.py"
ICON_PATH = BASE_DIR / "kuro.ico"

def install_all_shortcuts():
    # PowerShell script to create shortcuts pointing directly to Microsoft-signed pythonw.exe
    # Fully complies with Windows 11 Smart App Control (SAC)
    ps_code = f"""
    $WshShell = New-Object -ComObject WScript.Shell

    $locations = @(
        '{str(PROGRAMS_USER / "Kuro.lnk")}',
        '{str(PROGRAMS_USER / "Kuro Anime Screensaver.lnk")}',
        '{str(DESKTOP_DIR / "Kuro.lnk")}',
        '{str(DESKTOP_DIR / "Kuro Anime Screensaver.lnk")}',
        '{str(BASE_DIR / "Kuro.lnk")}'
    )

    foreach ($loc in $locations) {{
        $s = $WshShell.CreateShortcut($loc)
        $s.TargetPath = '{str(TARGET_EXE)}'
        $s.Arguments = '"{str(LAUNCHER_PY)}" start'
        $s.WorkingDirectory = '{str(BASE_DIR)}'
        if (Test-Path '{str(ICON_PATH)}') {{
            $s.IconLocation = '{str(ICON_PATH)},0'
        }}
        $s.Description = 'KURO // ANIME - Cinematic Ambient Screensaver'
        $s.Save()
        Write-Output "Created: $loc"
    }}

    $shell = New-Object -ComObject Shell.Application
    $folder = $shell.Namespace('{str(PROGRAMS_USER)}')
    $item = $folder.ParseName('Kuro.lnk')
    if ($item) {{
        foreach ($verb in $item.Verbs()) {{
            $clean = $verb.Name -replace '&', ''
            if ($clean -match 'Pin to Start|pintostart') {{
                $verb.DoIt()
                break
            }}
        }}
    }}
    """
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, text=True)
    print(res.stdout.strip())
    if res.stderr.strip():
        print("Errors:", res.stderr.strip())

if __name__ == "__main__":
    install_all_shortcuts()
