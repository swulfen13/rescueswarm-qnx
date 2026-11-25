# Kopiert ein gebautes QNX-Programm in die VM und startet es.
# Beispiel: .\run_on_qnx.ps1 hello\hello
param([Parameter(Mandatory=$true)][string]$Binary, [string]$Args = "")
$ip = (Get-Content (Join-Path $PSScriptRoot "..\vm_ip.txt") -Raw).Trim()   # bei Bedarf: qnx.bat bash vm_start.sh zeigt die aktuelle IP
$o = @("-i","C:\Users\Admin\qnxvm\qnx_key","-o","StrictHostKeyChecking=no","-o","UserKnownHostsFile=NUL",
       "-o","LogLevel=ERROR","-o","Ciphers=aes128-ctr","-o","MACs=hmac-sha2-256")  # Cipher/MAC noetig wegen VirtualBox ("Corrupted MAC")
$name = Split-Path $Binary -Leaf
scp @o $Binary "root@${ip}:/tmp/$name"
ssh @o "root@$ip" "chmod +x /tmp/$name; /tmp/$name $Args"
