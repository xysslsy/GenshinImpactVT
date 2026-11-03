Option Explicit
Dim fso, shell, launcher, root, pythonw, app
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
If Not fso.FileExists(pythonw) Then
    pythonw = fso.GetAbsolutePathName(fso.BuildPath(root, "..\experiments\webview2-poc\.venv\Scripts\pythonw.exe"))
End If
app = fso.BuildPath(root, "start.pyw")
If Not fso.FileExists(pythonw) Or Not fso.FileExists(app) Then
    MsgBox "GenshinImpactVT could not find Python or start.pyw. See README.md.", 16, "GenshinImpactVT"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
Set launcher = CreateObject("Shell.Application")
launcher.ShellExecute pythonw, Chr(34) & app & Chr(34), root, "runas", 1
