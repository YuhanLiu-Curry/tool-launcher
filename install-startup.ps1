$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\LENOVO\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\tool-launcher.lnk")
$Shortcut.TargetPath = "C:\Python314\pythonw.exe"
$Shortcut.Arguments = "D:\projects\tool-launcher\run.py"
$Shortcut.WorkingDirectory = "D:\projects\tool-launcher"
$Shortcut.WindowStyle = 7
$Shortcut.Description = "tool-launcher"
$Shortcut.Save()
Write-Host "done"
