Param(
    [int]$Port = 8000
)

Write-Host "Starting SureBet API on port $Port..." -ForegroundColor Green
$env:PYTHONUNBUFFERED = "1"
uvicorn api.app:app --host 0.0.0.0 --port $Port --reload
