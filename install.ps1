# SRS Edge Learning — installer for Windows (PowerShell 5+).
#   irm https://raw.githubusercontent.com/GGCryptoh/srs-edge-learning/main/install.ps1 | iex
# Installs into %USERPROFILE%\.claude\skills\srs-edge-learning (Claude Code) and, if present, .codex\skills and .copilot\skills.
$ErrorActionPreference = "Stop"
$Name = "srs-edge-learning"; $Url = "https://github.com/GGCryptoh/srs-edge-learning/releases/latest/download/srs-edge-learning.zip"
$Dest = if ($env:SKILLS_DIR) { $env:SKILLS_DIR } else { Join-Path $HOME ".claude\skills" }
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) { Write-Host "Python 3 is required: https://www.python.org/downloads/ (tick 'Add to PATH')"; exit 1 }
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("skill-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
Write-Host "Downloading $Url"
Invoke-WebRequest -Uri $Url -OutFile (Join-Path $tmp "skill.zip")
New-Item -ItemType Directory -Path $Dest -Force | Out-Null
if (Test-Path (Join-Path $Dest $Name)) { Remove-Item (Join-Path $Dest $Name) -Recurse -Force }
Expand-Archive -Path (Join-Path $tmp "skill.zip") -DestinationPath $Dest -Force
Remove-Item $tmp -Recurse -Force
Write-Host "Installed -> $(Join-Path $Dest $Name)"
foreach ($d in @((Join-Path $HOME ".codex\skills"), (Join-Path $HOME ".copilot\skills"))) {
  if ((Test-Path $d) -and ($d -ne $Dest)) { if (Test-Path (Join-Path $d $Name)) { Remove-Item (Join-Path $d $Name) -Recurse -Force }; Copy-Item (Join-Path $Dest $Name) -Destination $d -Recurse; Write-Host "Also installed -> $(Join-Path $d $Name)" }
}
Write-Host ""
Write-Host "Done. Open your agent (Claude Code, Codex, Copilot CLI) in a new session and type:"
Write-Host "  /$Name <the thing you want to get smart at>"
