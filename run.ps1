# Запуск сайта школы 93 на своём компьютере (Windows).
# Нужен Python 3.11 или новее: https://www.python.org/downloads/ (при установке отметить «Add python.exe to PATH»).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv")) {
  Write-Host "Создаю окружение..." -ForegroundColor Cyan
  python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
if (-not (Test-Path "data\site.db")) {
  Write-Host "Заполняю базу данными со старого сайта..." -ForegroundColor Cyan
  & .\.venv\Scripts\python.exe -m app.seed data\files.csv
}
Write-Host ""
Write-Host "Сайт:    http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Админка: http://127.0.0.1:8000/admin   логин admin, пароль school93-admin" -ForegroundColor Green
Write-Host "Остановить: Ctrl+C" -ForegroundColor Gray
# браузер открываем, когда сервер уже поднялся
Start-Job { Start-Sleep -Seconds 4; Start-Process "http://127.0.0.1:8000" } | Out-Null
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
