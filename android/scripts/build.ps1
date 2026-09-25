param(
    [ValidateSet("Debug", "Release", "Clean", "InstallDebug")]
    [string]$Task = "Debug"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$GradleVersion = "8.9"
$DistDir = Join-Path $ProjectDir ".gradle-dist"
$GradleHome = Join-Path $DistDir ("gradle-" + $GradleVersion)
$GradleBat = Join-Path $GradleHome "bin\gradle.bat"

Write-Host "Android project: $ProjectDir"

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw "Java not found. Install JDK 17 and add java to PATH."
}

if (-not (Test-Path $GradleBat)) {
    New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
    $Zip = Join-Path $DistDir ("gradle-" + $GradleVersion + "-bin.zip")
    $Url = "https://services.gradle.org/distributions/gradle-" + $GradleVersion + "-bin.zip"

    Write-Host "Downloading Gradle $GradleVersion..."
    Invoke-WebRequest -Uri $Url -OutFile $Zip
    Write-Host "Extracting Gradle..."
    Expand-Archive -Path $Zip -DestinationPath $DistDir -Force
    Remove-Item $Zip -Force
}

$Sdk = $env:ANDROID_SDK_ROOT
if (-not $Sdk) { $Sdk = $env:ANDROID_HOME }

$LocalProperties = Join-Path $ProjectDir "local.properties"
if ($Sdk -and -not (Test-Path $LocalProperties)) {
    $EscapedSdk = $Sdk.Replace("\", "\\")
    Set-Content -Path $LocalProperties -Value ("sdk.dir=" + $EscapedSdk)
    Write-Host "Created local.properties from Android SDK environment."
} elseif (-not $Sdk -and -not (Test-Path $LocalProperties)) {
    throw "Android SDK not found. Set ANDROID_SDK_ROOT/ANDROID_HOME or open android/ in Android Studio once."
}

$GradleTask = switch ($Task) {
    "Debug" { ":app:assembleDebug" }
    "Release" { ":app:assembleRelease" }
    "Clean" { "clean" }
    "InstallDebug" { ":app:installDebug" }
}

Push-Location $ProjectDir
try {
    & $GradleBat --no-daemon $GradleTask
    if ($LASTEXITCODE -ne 0) {
        throw "Gradle failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

if ($Task -eq "Debug") {
    Write-Host ""
    Write-Host ("APK: " + (Join-Path $ProjectDir "app\build\outputs\apk\debug\app-debug.apk"))
} elseif ($Task -eq "Release") {
    Write-Host ""
    Write-Host ("Unsigned APK: " + (Join-Path $ProjectDir "app\build\outputs\apk\release\app-release-unsigned.apk"))
}
