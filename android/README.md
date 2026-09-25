# AI Gallery Analyzer — Android MVP

Standalone Android application inside the desktop repository.

## Current MVP

- Kotlin + Jetpack Compose;
- reads the device photo gallery through MediaStore;
- requests Android gallery permission;
- Room database caches results by MediaStore id + modified time + model version;
- WorkManager runs gallery analysis outside the UI thread;
- unchanged photos are skipped on subsequent runs;
- ONNX Runtime Android is included;
- a real compact MobileNetV4 NSFW ONNX classifier is supported;
- NNAPI is enabled when available, with normal ONNX Runtime fallback;
- UI shows gallery count, analyzed count, NSFW count and progress;
- all processing is local.

## Models

Mobile model assets live in:

```text
app/src/main/assets/models/
  nsfw.onnx
  general.onnx
```

The first real mobile backend is a compact MobileNetV4 NSFW classifier (~10 MB)
with five classes: `drawings / hentai / neutral / porn / sexy`. The app combines
`hentai + porn + sexy` into `nsfwScore`.

Model binaries are not committed to Git. `PREPARE_MODELS.cmd` downloads the
pinned ONNX file and verifies its SHA-256. All normal Windows build scripts call
model preparation automatically, so a fresh `BUILD_DEBUG.cmd` produces an APK
with the NSFW model included.

The `general.onnx` slot is reserved for the second compact general-purpose
classifier; its adapter will be added separately.

## Requirements

- Windows 10/11 for the supplied .cmd scripts;
- JDK 17;
- Android SDK with API 35;
- Android platform-tools for `INSTALL_DEBUG.cmd`;
- internet access on the first build so Gradle/Maven dependencies can download.

Android Studio already includes a suitable JDK and can install the Android SDK.

## Prepare models manually

Normally this is automatic during a build. To download/verify the model only:

```bat
cd android
PREPARE_MODELS.cmd
```

## Build debug APK

From repository root:

```bat
cd android
BUILD_DEBUG.cmd
```

The script downloads Gradle 8.9 into `android/.gradle-dist/` if necessary.

Output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

## Install debug APK on a connected phone

Enable Developer options + USB debugging, connect the phone, then:

```bat
cd android
INSTALL_DEBUG.cmd
```

## Release APK

```bat
cd android
BUILD_RELEASE.cmd
```

Output is unsigned:

```text
android/app/build/outputs/apk/release/app-release-unsigned.apk
```

Signing will be added when package name and release strategy are finalized.

## Build release AAB

For a Play Store style bundle:

```bat
cd android
BUILD_BUNDLE.cmd
```

Output:

```text
android/app/build/outputs/bundle/release/app-release.aab
```

The release output is not signed yet.

## Clean

```bat
cd android
CLEAN.cmd
```

## Android Studio

Open the `android/` directory as a project. Do not open the repository root
as the Android project.

## Architecture

```text
MediaStore
   ↓
GalleryRepository
   ↓
GalleryAnalysisWorker
   ↓
ImageAnalyzer
   ├── NoOpAnalyzer
   └── ONNX adapters (next step)
   ↓
Room
   ↓
Compose UI
```
