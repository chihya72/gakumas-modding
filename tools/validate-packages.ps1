param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()
$manifestSchema = Join-Path $Root 'spec\manifest.schema.json'
$profileSchema = Join-Path $Root 'spec\profile.schema.json'

function Test-SchemaFile([string]$Path, [string]$Schema) {
    try {
        $json = Get-Content -LiteralPath $Path -Raw
        if (-not ($json | Test-Json -SchemaFile $Schema -ErrorAction SilentlyContinue)) {
            $errors.Add("Schema validation failed: $Path")
        }
    } catch {
        $errors.Add("Invalid JSON: $Path ($($_.Exception.Message))")
    }
}

$profileIds = @{}
Get-ChildItem (Join-Path $Root 'profiles') -Directory | ForEach-Object {
    $dir = $_.FullName
    foreach ($required in 'profile.json','drawcall_map.json','material_map.json','texture_map.json','notes.md') {
        if (-not (Test-Path (Join-Path $dir $required))) {
            $errors.Add("Missing Profile file: $($_.Name)/$required")
        }
    }
    $profilePath = Join-Path $dir 'profile.json'
    if (Test-Path $profilePath) {
        Test-SchemaFile $profilePath $profileSchema
        try {
            $profile = Get-Content $profilePath -Raw | ConvertFrom-Json
            $profileIds[$profile.id] = $true
        } catch {}
    }
}

$modIds = @{}
$conflictOwners = @{}
Get-ChildItem (Join-Path $Root 'mods') -Directory | ForEach-Object {
    $dir = $_.FullName
    $manifestPath = Join-Path $dir 'manifest.json'
    $iniPath = Join-Path $dir 'mod.ini'
    if (-not (Test-Path $manifestPath)) {
        if ($_.Name -notlike 'dev-*') { $errors.Add("Missing manifest: $($_.Name)") }
        return
    }
    Test-SchemaFile $manifestPath $manifestSchema
    try {
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        if ($modIds.ContainsKey($manifest.id)) { $errors.Add("Duplicate Mod ID: $($manifest.id)") }
        $modIds[$manifest.id] = $true
        if (-not $profileIds.ContainsKey($manifest.profile)) { $errors.Add("Unknown Profile '$($manifest.profile)' in $($_.Name)") }
        foreach ($key in $manifest.conflicts) {
            if (-not $conflictOwners.ContainsKey($key)) { $conflictOwners[$key] = @() }
            $conflictOwners[$key] += $manifest.id
        }
    } catch {}
    if (-not (Test-Path $iniPath)) {
        $errors.Add("Missing mod.ini: $($_.Name)")
        return
    }
    $ini = Get-Content $iniPath -Raw
    foreach ($match in [regex]::Matches($ini, '(?im)^\s*filename\s*=\s*(.+?)\s*$')) {
        $relative = $match.Groups[1].Value.Trim()
        if (-not (Test-Path (Join-Path $dir $relative))) {
            $errors.Add("Missing referenced resource in $($_.Name): $relative")
        }
    }
}

foreach ($entry in $conflictOwners.GetEnumerator()) {
    if ($entry.Value.Count -gt 1) {
        $warnings.Add("Declared conflict '$($entry.Key)': $($entry.Value -join ', ')")
    }
}

foreach ($warning in $warnings) { Write-Warning $warning }
if ($errors.Count) {
    foreach ($message in $errors) { Write-Error $message -ErrorAction Continue }
    Write-Host "Validation failed: $($errors.Count) error(s), $($warnings.Count) warning(s)." -ForegroundColor Red
    exit 1
}

Write-Host "Validation passed: $($profileIds.Count) profile(s), $($modIds.Count) mod package(s), $($warnings.Count) warning(s)." -ForegroundColor Green
