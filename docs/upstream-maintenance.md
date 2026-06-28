# Upstream Mozilla Maintenance

This project is a Firefox for Fire TV derived Android TV browser. It cannot
directly import `mozilla-central` as an application dependency. `mozilla-central`
contains Firefox, Gecko, GeckoView, build infrastructure, desktop code, Android
code, tests, and platform code. For this app, upstream maintenance should flow
through the Android artifacts and source areas that are actually consumed here.

Primary upstreams:

- `mozilla-central`: https://hg.mozilla.org/mozilla-central/
- Firefox GitHub mirror: https://github.com/mozilla-firefox/firefox
- Android Components: https://github.com/mozilla-mobile/android-components
- GeckoView docs: https://firefox-source-docs.mozilla.org/mobile/android/geckoview/

## Current Integration Points

The app currently consumes Mozilla upstream through:

- `org.mozilla.components:*` dependencies pinned by `moz_components_version` in
  the root `build.gradle`.
- `org.mozilla.geckoview:geckoview-nightly` pinned by `geckoview_version` in
  the `gecko` product flavor.
- Gecko engine setup in
  `app/src/gecko/java/org/mozilla/tv/firefox/webrender/WebRenderComponents.kt`.
- System WebView engine setup in
  `app/src/system/java/org/mozilla/tv/firefox/webrender/WebRenderComponents.kt`.
- Shared browser settings in
  `app/src/main/java/org/mozilla/tv/firefox/utils/Settings.kt`.

## Porting Policy

Do not attempt a bulk copy from `mozilla-central`. Port one upstream capability
at a time and keep the TV-specific app shell intact.

Use this order:

1. Identify the user-visible capability or security fix to port.
2. Locate the upstream implementation and the Android artifact that exposes it.
3. Upgrade the smallest required dependency set.
4. Adapt the TV input, focus, media, and overlay behavior.
5. Verify both `system` and `gecko` build flavors, or document why one flavor is
   intentionally unsupported.

## Feature Buckets

Prefer these maintainable buckets instead of a single broad "Firefox parity"
task:

- Engine and security: GeckoView version, Android Components version, tracking
  protection policy, mixed content, safe browsing, file/content access.
- Browser behavior: user agent, session lifecycle, media playback, fullscreen,
  error pages, downloads, permissions.
- TV experience: remote control navigation, cursor behavior, overlays, voice
  media session, pinned tiles, channels.
- Account features: Firefox Accounts, send-tab, push/ADM integration.
- Observability: Glean metrics, Sentry crash reporting, release/build metadata.
- Build and maintenance: Gradle, Android SDK, Kotlin, repository configuration,
  deprecated dependency repositories.

## Current Pinned Upstream Baseline

The current baseline is intentionally conservative:

- Android Components: `24.0.1`
- GeckoView nightly: `72.0.20191202091209`
- Kotlin: `1.3.61`
- Coroutines: `1.3.2`

`browser-engine-gecko-nightly:24.0.1` declares that GeckoView version in its POM.
Do not jump GeckoView independently to the latest nightly unless
`browser-engine-gecko-nightly` and the code that consumes it are migrated at the
same time.

The previous pinned baseline was:

- Android Components: `24.0.0`
- GeckoView nightly: `72.0.20191202091209`
- Kotlin: `1.3.31`
- Coroutines: `1.0.1`

`feature-sendtab` was only published through `25.0.0`, and
`browser-engine-gecko-nightly:25.0.0` is not published. Moving to Android
Components `26.0.0` or later requires replacing or removing the current
`feature-sendtab` integration first. After that, continue in small steps because
later Android Components releases move more browser behavior toward newer
state/store APIs.

The shared-version model should stay on `24.0.1` until `feature-sendtab` is
isolated or replaced. A remote audit of proposed `27.0.0` is expected to fail
while `feature-sendtab` remains in the dependency set, even though
`browser-engine-gecko-nightly:27.0.0` exists and declares GeckoView
`73.0.20200106092427`.

## Audit Command

Run the local audit before planning an upstream port:

```sh
python tools/upstream/audit_mozilla_dependencies.py
```

On Windows from this repository:

```bat
python tools\upstream\audit_mozilla_dependencies.py
```

The script reports current Mozilla dependency pins, Android build pins, and
maintenance warnings. It does not modify files or require network access.

Use the stricter gate before submitting a dependency bump:

```sh
python tools/upstream/audit_mozilla_dependencies.py --strict
python tools/upstream/audit_mozilla_dependencies.py --remote --strict
python tools/upstream/audit_mozilla_dependencies.py --remote --proposed-ac 27.0.0 --strict
```

The default audit performs local checks only. The `--remote` audit queries
Mozilla Maven and verifies that the local GeckoView pin matches the
`browser-engine-gecko-nightly` POM for the current Android Components version.
Use `--proposed-ac` to check whether every currently declared
`org.mozilla.components` artifact exists for a candidate version before editing
Gradle files.

## Minimum Verification

For a dependency or engine port, run at least:

```sh
./gradlew testSystemDebug
./gradlew assembleSystemDebug
./gradlew assembleGeckoDebug
```

On Windows, use `gradlew.bat` for the same tasks.

For user-visible browser behavior, also run the relevant Android TV UI tests on
a real Fire TV device when available. Emulators are useful for fast feedback but
do not match Fire TV WebView behavior.
