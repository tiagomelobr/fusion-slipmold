<#
.SYNOPSIS
Install the SlipMold Fusion add-in without Python: a directory junction (no admin rights)
  %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\SlipMold -> <repo>\addin\SlipMold

.DESCRIPTION
Same junction as tools/install_addin.py. Never deletes anything except its own junction: an existing
target is replaced (or removed with -Uninstall) only when it is a junction to a SlipMold add-in with the
same manifest id; a folder or anything else is left alone and reported. -MoldsDir writes "moldsDir" into
the SlipMold user config (%APPDATA%\SlipMold\config.json), the folder that receives molds\<design>.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1 -MoldsDir D:\Molds
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1 -Uninstall
#>
param(
    [switch]$Uninstall,
    [switch]$DryRun,
    [string]$Target = (Join-Path $env:APPDATA "Autodesk\Autodesk Fusion 360\API\AddIns\SlipMold"),
    [string]$MoldsDir = ""
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Repo "addin\SlipMold"
$Manifest = "SlipMold.manifest"
$Start = "Start it in Fusion: Utilities > Add-Ins (Shift+S) > Add-Ins tab > SlipMold > Run; tick Run on Startup " +
         "to load it with Fusion. The SlipMold panel is in the Design workspace, Solid tab."

function Get-ManifestId([string]$Folder) {
    try { return (Get-Content -Raw -LiteralPath (Join-Path $Folder $Manifest) | ConvertFrom-Json).id } catch { return $null }
}

function Get-Ownership([string]$Path) {
    # none | ours-link (junction to this repo) | own-link (junction to another SlipMold with our id) | foreign
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) { return "none" }
    if ($item.LinkType -ne "Junction" -and $item.LinkType -ne "SymbolicLink") { return "foreign" }
    $dest = @($item.Target)[0]
    if (-not $dest) { return "foreign" }
    $dest = $dest -replace '^\\\\\?\\', ''
    $norm = { param($p) [System.IO.Path]::GetFullPath($p).TrimEnd('\').ToLowerInvariant() }
    if ((& $norm $dest) -eq (& $norm $Source)) { return "ours-link" }
    $id = Get-ManifestId $dest
    if ($id -and $id -eq (Get-ManifestId $Source)) { return "own-link" }
    return "foreign"
}

function Remove-OwnJunction([string]$Path) {
    # Directory.Delete on a junction removes the link only, never the folder it points to
    [System.IO.Directory]::Delete($Path, $false)
}

if (-not (Test-Path -LiteralPath (Join-Path $Source $Manifest))) {
    Write-Output "error: $Source has no $Manifest (run this script from the repository's tools folder)"
    exit 1
}
$kind = Get-Ownership $Target

if ($Uninstall) {
    switch ($kind) {
        "none" { Write-Output "nothing installed at $Target"; exit 0 }
        "foreign" { Write-Output "error: $Target is not a SlipMold junction made by this tool; left alone"; exit 1 }
        default {
            if ($DryRun) { Write-Output "would remove the junction $Target ($kind)"; exit 0 }
            Remove-OwnJunction $Target
            Write-Output "removed the junction $Target ($kind)"
            exit 0
        }
    }
}

if ($kind -eq "foreign") {
    Write-Output ("error: $Target exists and is not a SlipMold junction made by this tool (a copy made by " +
                  "install_addin.py --copy is removed with: python tools\install_addin.py --uninstall); " +
                  "remove or rename it yourself, then run again")
    exit 1
}
if ($kind -eq "ours-link") {
    Write-Output "already linked: $Target -> $Source"
} elseif ($DryRun) {
    $what = if ($kind -eq "none") { "" } else { "replace the $kind junction and " }
    Write-Output "would ${what}link $Target -> $Source"
} else {
    if ($kind -eq "own-link") { Remove-OwnJunction $Target }
    $parent = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    New-Item -ItemType Junction -Path $Target -Value $Source | Out-Null
    if ((Get-Ownership $Target) -ne "ours-link") {
        Write-Output "error: the junction attempt left $Target in an unexpected state; check it by hand"
        exit 1
    }
    Write-Output "linked: $Target -> $Source"
}

if ($MoldsDir -and -not $DryRun) {
    $cfgPath = Join-Path $env:APPDATA "SlipMold\config.json"
    $cfg = [ordered]@{}
    if (Test-Path -LiteralPath $cfgPath) {
        try {
            $old = Get-Content -Raw -LiteralPath $cfgPath | ConvertFrom-Json
            foreach ($p in $old.PSObject.Properties) { $cfg[$p.Name] = $p.Value }
        } catch { }
    }
    $cfg["moldsDir"] = [System.IO.Path]::GetFullPath($MoldsDir)
    New-Item -ItemType Directory -Path (Split-Path -Parent $cfgPath) -Force | Out-Null
    $json = ($cfg | ConvertTo-Json -Depth 5) -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText($cfgPath, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Output "moldsDir = $($cfg['moldsDir']) (in $cfgPath)"
}
Write-Output $Start
