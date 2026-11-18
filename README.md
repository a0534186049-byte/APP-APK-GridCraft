# GridCraft for Android

This repository owns the Android build entry point and GridCraft-specific Android compatibility work.

The spreadsheet application source is checked out from the pinned Hebrew/RTL development revision of the official Storytold GridCraft code during each build. The source itself is not duplicated into this repository.

## Current build

- Shared build pipeline: [ArtCraft-Android-Common](https://github.com/a0534186049-byte/ArtCraft-Android-Common)
- Reusable workflow revision: `a7d301f21cebaff853306d63cc4c641246fa1938`
- App source repository: [storytold/gridcraft](https://github.com/storytold/gridcraft)
- Hebrew/RTL source candidate: [shlomoappdev-netizen/gridcraft](https://github.com/shlomoappdev-netizen/gridcraft) at commit `ba06ef38575a1725a78e0d9099161f5c65db3646`
- Android package ID: `com.artcraft.gridcraft`
- App-specific patch script: `scripts/prepare-gridcraft-android.py`

## Run a build

1. Open **Actions** in this repository.
2. Select **GridCraft Android APK**.
3. Choose **Run workflow**.
4. For an initial test, choose **debug**. A distributable release uses **release** and requires this repository's permanent signing Secrets.

Release builds publish `GridCraft.apk` to the fixed `gridcraft-latest` GitHub Release in this repository. The workflow replaces the APK asset in that same Release and verifies the remote asset name and size. Actions Artifacts are only a backup.

## Signing

A release must use a permanent GridCraft-only signing key. Do not reuse a key from WordCraft, PhotoCraft, or another app. The Common repository documents key creation and the three required Actions Secrets.

## Scope and licensing

This repository does not replace GridCraft's product name, application identity, icon, design, or upstream source. Keep the upstream Apache-2.0/MIT license files, NOTICE, and asset-specific notices with any distributed derivative, as applicable. See `HEBREW_STATUS.md` for the current language and RTL verification status.
