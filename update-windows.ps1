# Downloads the latest CV Studio release and replaces the app files in this folder.
# Personal CV files (content\*.local.json, content\profiles\, content\*.json you added) are never touched.
$ErrorActionPreference = 'Stop'
$repo = 'bayleafwalker/cv-studio'
$url = "https://github.com/$repo/releases/latest/download/cv-studio-windows.zip"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-Version($folder) {
    $toml = Join-Path $folder 'pyproject.toml'
    if (Test-Path $toml) { $m = Select-String -Path $toml -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1; if ($m) { return $m.Matches[0].Groups[1].Value } }
    return 'unknown'
}

$before = Get-Version $here
Write-Host "Installed version: $before"
$temp = Join-Path ([IO.Path]::GetTempPath()) ("cv-studio-update-" + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    $zip = Join-Path $temp 'cv-studio-windows.zip'
    Write-Host "Downloading $url ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $temp -Force
    $source = Get-ChildItem -Path $temp -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'server.py') } | Select-Object -First 1
    if (-not $source) { $source = Get-Item $temp }
    if (-not (Test-Path (Join-Path $source.FullName 'server.py'))) { throw 'The downloaded file does not look like CV Studio.' }
    $after = Get-Version $source.FullName
    if ($after -eq $before) { Write-Host "You already have the newest version ($before). Nothing changed."; exit 0 }

    Get-ChildItem -Path $source.FullName -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($source.FullName.Length + 1)
        if ($relative -like 'content\*' -and $relative -ne 'content\cv.sample.json') { return }  # never overwrite personal CVs
        $target = Join-Path $here $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -Path $_.FullName -Destination $target -Force
    }
    Write-Host "Updated CV Studio from $before to $after. Your CV files were kept."
    Write-Host 'If CV Studio is open, close its black window and double-click start-windows.bat again.'
} catch {
    Write-Host "The update did not work: $($_.Exception.Message)"
    Write-Host "You can also download it by hand: https://github.com/$repo/releases/latest"
    exit 1
} finally {
    Remove-Item -Path $temp -Recurse -Force -ErrorAction SilentlyContinue
}
