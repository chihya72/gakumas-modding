[CmdletBinding()]
param(
    [string]$MeshJson = (Join-Path $PSScriptRoot '..\research\assetstudio\export-body-json\Geo_Body.json'),
    [string]$SkeletonJson = (Join-Path $PSScriptRoot '..\research\assetstudio\export-body-json\Geo_Body.skeleton.json'),
    [string]$OutputPath = (Join-Path $PSScriptRoot '..\mods\poc-tpose-hski-body\Buffers\Body.TPose.VB0.buf')
)

$ErrorActionPreference = 'Stop'

$mesh = Get-Content -LiteralPath $MeshJson -Raw | ConvertFrom-Json
$skeleton = Get-Content -LiteralPath $SkeletonJson -Raw | ConvertFrom-Json
$vertexCount = [int]$mesh.m_VertexCount
$positions = $mesh.m_Vertices
$normals = $mesh.m_Normals
$tangents = $mesh.m_Tangents

if ($positions.Count -ne $vertexCount * 3) {
    throw "Position count mismatch: $($positions.Count), expected $($vertexCount * 3)"
}
if ($normals.Count -ne $vertexCount * 3) {
    throw "Normal count mismatch: $($normals.Count), expected $($vertexCount * 3)"
}
if ($tangents.Count -ne $vertexCount * 4) {
    throw "Tangent count mismatch: $($tangents.Count), expected $($vertexCount * 4)"
}

# Unity's Mesh data is in renderer/mesh space, while this game's final dynamic
# body VB is consumed in root-bone space. The root bone's bind pose is the exact
# Mesh -> RootBone transform required by the draw call.
$rootBone = $skeleton.nodes | Where-Object {
    [string]$_.pathId -eq [string]$skeleton.rootBonePathId
} | Select-Object -First 1
if ($null -eq $rootBone -or $null -eq $rootBone.bindPose) {
    throw "Root bone or bind pose not found for path ID $($skeleton.rootBonePathId)"
}
$m = $rootBone.bindPose

function Transform-Direction {
    param([double]$X, [double]$Y, [double]$Z)

    $tx = [double]$m.M00 * $X + [double]$m.M10 * $Y + [double]$m.M20 * $Z
    $ty = [double]$m.M01 * $X + [double]$m.M11 * $Y + [double]$m.M21 * $Z
    $tz = [double]$m.M02 * $X + [double]$m.M12 * $Y + [double]$m.M22 * $Z
    $length = [Math]::Sqrt($tx * $tx + $ty * $ty + $tz * $tz)
    if ($length -gt 0.0) {
        $tx /= $length
        $ty /= $length
        $tz /= $length
    }
    return @([single]$tx, [single]$ty, [single]$tz)
}

$outputDirectory = Split-Path -Parent $OutputPath
[void][System.IO.Directory]::CreateDirectory($outputDirectory)

$stream = [System.IO.File]::Open($OutputPath, [System.IO.FileMode]::Create)
$writer = [System.IO.BinaryWriter]::new($stream)
try {
    for ($vertex = 0; $vertex -lt $vertexCount; $vertex++) {
        $p = $vertex * 3
        $t = $vertex * 4
        $px = [double]$positions[$p + 0]
        $py = [double]$positions[$p + 1]
        $pz = [double]$positions[$p + 2]
        $writer.Write([single]([double]$m.M00 * $px + [double]$m.M10 * $py + [double]$m.M20 * $pz + [double]$m.M30))
        $writer.Write([single]([double]$m.M01 * $px + [double]$m.M11 * $py + [double]$m.M21 * $pz + [double]$m.M31))
        $writer.Write([single]([double]$m.M02 * $px + [double]$m.M12 * $py + [double]$m.M22 * $pz + [double]$m.M32))

        $normal = Transform-Direction $normals[$p + 0] $normals[$p + 1] $normals[$p + 2]
        $writer.Write($normal[0])
        $writer.Write($normal[1])
        $writer.Write($normal[2])

        $tangent = Transform-Direction $tangents[$t + 0] $tangents[$t + 1] $tangents[$t + 2]
        $writer.Write($tangent[0])
        $writer.Write($tangent[1])
        $writer.Write($tangent[2])
        $writer.Write([single]$tangents[$t + 3])
    }
}
finally {
    $writer.Dispose()
    $stream.Dispose()
}

$expectedBytes = $vertexCount * 40
$actualBytes = (Get-Item -LiteralPath $OutputPath).Length
if ($actualBytes -ne $expectedBytes) {
    throw "VB0 byte size mismatch: $actualBytes, expected $expectedBytes"
}

Write-Output ([pscustomobject]@{
    OutputPath = (Resolve-Path -LiteralPath $OutputPath).Path
    VertexCount = $vertexCount
    Stride = 40
    ByteLength = $actualBytes
    RootBone = $rootBone.name
    RootBonePathId = $skeleton.rootBonePathId
    Translation = @([single]$m.M30, [single]$m.M31, [single]$m.M32)
})
