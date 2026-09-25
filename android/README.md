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
- NNAPI is enabled in the ONNX session factory;
- UI shows gallery count, analyzed count, NSFW count and progress;
- all processing is local.

## Models

Mobile model assets live in:

```text
app/src/main/assets/models/
  nsfw.onnx
  general.onnx
```

The project intentionally does not commit model binaries yet. The app remains
buildable without them and uses `NoOpAnalyzer`. The next model step is to
choose/export a compact NSFW model and a compact general classifier, then add
their exact preprocessing/input/output adapters.

## Requirements

- Windows 10/11 for the supplied .cmd scripts;
- JDK 17;
- Android SDK with API 35;
- Android platform-tools for `INSTALL_DEBUG.cmd`;
- internet access on the first build so Gradle/Maven dependencies can download.

Android Studio already includes a suitable JDK and can install the Android SDK.

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
