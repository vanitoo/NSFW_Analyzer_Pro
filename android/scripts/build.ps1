param(
    [ValidateSet("Debug", "Release", "BundleRelease", "Clean", "InstallDebug")]
    [string]$Task = "Debug",
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$GradleVersion = "8.9"
$DistDir = Join-Path $ProjectDir ".gradle-dist"
$GradleHome = Join-Path $DistDir ("gradle-" + $GradleVersion)
$GradleBat = Join-Path $GradleHome "bin\gradle.bat"

Write-Host "Android project: $ProjectDir"

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    $AndroidStudioJdk = "C:\Program Files\Android\Android Studio\jbr"
    if (Test-Path (Join-Path $AndroidStudioJdk "bin\java.exe")) {
        $env:JAVA_HOME = $AndroidStudioJdk
        $env:Path = (Join-Path $AndroidStudioJdk "bin") + ";" + $env:Path
        Write-Host "Using Android Studio JDK: $AndroidStudioJdk"
    } else {
        throw "Java not found. Install Android Studio/JDK 17 or add java to PATH."
    }
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
if (-not $Sdk -and $env:LOCALAPPDATA) {
    $DefaultSdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    if (Test-Path $DefaultSdk) {
        $Sdk = $DefaultSdk
        Write-Host "Using Android SDK: $Sdk"
    }
}

$LocalProperties = Join-Path $ProjectDir "local.properties"
if ($Sdk -and -not (Test-Path $LocalProperties)) {
    $EscapedSdk = $Sdk.Replace("\", "\\")
    Set-Content -Path $LocalProperties -Value ("sdk.dir=" + $EscapedSdk)
    Write-Host "Created local.properties from Android SDK environment."
} elseif (-not $Sdk -and -not (Test-Path $LocalProperties)) {
    throw "Android SDK not found. Install it with Android Studio or set ANDROID_SDK_ROOT."
}

if ($Sdk) {
    $Platform35 = Join-Path $Sdk "platforms\android-35"
    if (-not (Test-Path $Platform35)) {
        throw "Android SDK Platform 35 is missing. Install API 35 in Android Studio SDK Manager."
    }
}

if ($Task -ne "Clean" -and -not $SkipModels) {
    $PrepareModels = Join-Path $ProjectDir "scripts\prepare_models.ps1"
    Write-Host "Preparing mobile models..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $PrepareModels
    if ($LASTEXITCODE -ne 0) {
        throw "Model preparation failed with exit code $LASTEXITCODE"
    }
}

$GradleTask = switch ($Task) {
    "Debug" { ":app:assembleDebug" }
    "Release" { ":app:assembleRelease" }
    "BundleRelease" { ":app:bundleRelease" }
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
} elseif ($Task -eq "BundleRelease") {
    Write-Host ""
    Write-Host ("AAB: " + (Join-Path $ProjectDir "app\build\outputs\bundle\release\app-release.aab"))
}
