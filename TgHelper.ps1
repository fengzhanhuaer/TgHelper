Set-Location -LiteralPath $PSScriptRoot
$env:TGHELPER_DEV = "1"
python TgHelper.py
