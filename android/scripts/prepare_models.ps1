param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ModelsDir = Join-Path $ProjectDir "app\src\main\assets\models"
$Target = Join-Path $ModelsDir "nsfw.onnx"
$ExpectedSha256 = "46995c000cb285d0c0a0e5b58cc618012ed2e649d326d4fddae910951848fc40"
$Url = "https://huggingface.co/taufiqdp/mobilenetv4_conv_small.e2400_r224_in1k_nsfw_classifier/resolve/504317ad62086f357c9c5f70cf983726ff47efdb/mobilenetv4_conv_small.e2400_r224_in1k_nsfw_classifier.onnx?download=true"

New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

function Test-ModelHash {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    $Hash = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    return $Hash -eq $ExpectedSha256
}

if (-not $Force -and (Test-ModelHash $Target)) {
    Write-Host "NSFW ONNX model already prepared: $Target"
    exit 0
}

$Temp = $Target + ".download"
if (Test-Path $Temp) { Remove-Item $Temp -Force }

Write-Host "Downloading compact NSFW model (~10 MB)..."
Invoke-WebRequest -Uri $Url -OutFile $Temp -MaximumRedirection 10

$ActualSha256 = (Get-FileHash -Algorithm SHA256 -Path $Temp).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    Remove-Item $Temp -Force
    throw "Model SHA-256 mismatch. Expected $ExpectedSha256, got $ActualSha256"
}

Move-Item -Path $Temp -Destination $Target -Force
Write-Host "Model ready: $Target"
Write-Host "SHA-256: $ActualSha256"
