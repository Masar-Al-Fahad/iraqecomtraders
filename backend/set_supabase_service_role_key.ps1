# Sets SUPABASE_SERVICE_ROLE_KEY in local .env files without printing the secret.
$ErrorActionPreference = 'Stop'
$backendEnv = Join-Path $PSScriptRoot '.env'
$rootEnv = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'

Write-Host ''
Write-Host '=== Supabase Service Role Key ===' -ForegroundColor Cyan
Write-Host 'Paste the key from Supabase → Project Settings → API → service_role'
Write-Host 'Input is hidden. Press Enter when done.'
Write-Host ''

$secure = Read-Host 'SUPABASE_SERVICE_ROLE_KEY' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
}
$key = ($key -as [string]).Trim()
if (-not $key -or $key.Length -lt 20) {
  Write-Host 'ERROR: key was empty or too short.' -ForegroundColor Red
  exit 1
}

function Set-EnvKey([string]$path, [string]$value) {
  if (-not (Test-Path $path)) { throw "Missing file: $path" }
  $lines = Get-Content -Path $path -Encoding UTF8
  $found = $false
  $out = foreach ($line in $lines) {
    if ($line -match '^\s*SUPABASE_SERVICE_ROLE_KEY\s*=') {
      $found = $true
      "SUPABASE_SERVICE_ROLE_KEY=$value"
    } else { $line }
  }
  if (-not $found) { $out = @($out) + "SUPABASE_SERVICE_ROLE_KEY=$value" }
  Set-Content -Path $path -Value $out -Encoding UTF8
}

Set-EnvKey $backendEnv $key
Set-EnvKey $rootEnv $key

$len = $key.Length
$key = $null
[GC]::Collect()

Write-Host ''
Write-Host "SUCCESS: key saved to backend/.env and .env (length=$len)." -ForegroundColor Green
Write-Host 'You can close this window.'
exit 0
