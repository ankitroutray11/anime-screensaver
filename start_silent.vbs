' KURO // ANIME — Silent Screensaver Launcher
' Launches the backend and kiosk browser without opening command prompt windows.
Option Explicit

Dim WshShell, fso, scriptDir, pythonwPath, pyPath, cmdStr, exitCode

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

' 1. Locate pythonw or python
pythonwPath = ""
On Error Resume Next
exitCode = WshShell.Run("where pythonw.exe", 0, True)
If exitCode = 0 Then
    pythonwPath = "pythonw.exe"
Else
    exitCode = WshShell.Run("where python.exe", 0, True)
    If exitCode = 0 Then
        pythonwPath = "python.exe"
    End If
End If
On Error GoTo 0

If pythonwPath = "" Then
    MsgBox "Python was not detected on your system PATH." & vbCrLf & vbCrLf & _
           "Please install Python 3.9+ from https://python.org and check 'Add Python to PATH'.", _
           vbCritical, "KuroAnime Screensaver - Startup Error"
    WScript.Quit 1
End If

' 2. Build silent launcher command line
cmdStr = """" & pythonwPath & """ """ & scriptDir & "\launcher.py"" start --silent"

' Pass any command line arguments if provided
If WScript.Arguments.Count > 0 Then
    Dim i
    For i = 0 To WScript.Arguments.Count - 1
        cmdStr = cmdStr & " " & WScript.Arguments(i)
    Next
End If

' 3. Run silently (0 = Hide window, False = Do not block VBScript thread)
exitCode = WshShell.Run(cmdStr, 0, False)
If exitCode <> 0 Then
    MsgBox "Unable to launch KuroAnime Screensaver." & vbCrLf & _
           "Please check kuro_server.log for details.", _
           vbExclamation, "KuroAnime Screensaver"
    WScript.Quit exitCode
End If
