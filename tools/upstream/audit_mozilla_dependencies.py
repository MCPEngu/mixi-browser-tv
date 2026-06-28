#!/usr/bin/env python3
"""Report Mozilla upstream integration points for this Android TV browser."""

from __future__ import annotations

import argparse
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote


ROOT_BUILD = "build.gradle"
APP_BUILD = "app/build.gradle"
BUILDSRC_BUILD = "buildSrc/build.gradle.kts"
MOZILLA_MAVEN = "https://maven.mozilla.org/maven2"
GECKOVIEW_METADATA = (
    f"{MOZILLA_MAVEN}/org/mozilla/geckoview/geckoview-nightly/maven-metadata.xml"
)
BROWSER_ENGINE_GECKO_METADATA = (
    f"{MOZILLA_MAVEN}/org/mozilla/components/browser-engine-gecko-nightly/maven-metadata.xml"
)
FEATURE_SENDTAB_LAST_PUBLISHED = "25.0.0"
KNOWN_GECKOVIEW_BY_BROWSER_ENGINE = {
    "24.0.1": "72.0.20191202091209",
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing required file: {path}") from exc


def find_ext_versions(root_build: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for match in re.finditer(r"ext\.([A-Za-z0-9_]+)\s*=\s*['\"]([^'\"]+)['\"]", root_build):
        versions[match.group(1)] = match.group(2)
    return versions


def find_android_pins(app_build: str) -> list[tuple[str, str]]:
    pins: list[tuple[str, str]] = []
    for name in ("compileSdkVersion", "buildToolsVersion", "minSdkVersion", "targetSdkVersion"):
        match = re.search(rf"\b{name}\s+['\"]?([^'\"\s]+)", app_build)
        if match:
            pins.append((name, match.group(1)))
    return pins


def pins_to_dict(pins: list[tuple[str, str]]) -> dict[str, str]:
    return {name: value for name, value in pins}


def find_mozilla_dependencies(app_build: str) -> list[tuple[str, str]]:
    deps: list[tuple[str, str]] = []
    pattern = re.compile(
        r"^\s*([A-Za-z0-9_]+Implementation|implementation|compileOnly)\s+"
        r"(?:\(?\s*)?['\"]([^'\"]*(?:mozilla|gecko|glean)[^'\"]*)['\"]",
        re.MULTILINE,
    )
    for match in pattern.finditer(app_build):
        deps.append((match.group(1), match.group(2)))
    return deps


def parse_version(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts)


def version_greater_than(left: str, right: str) -> bool:
    return parse_version(left) > parse_version(right)


def uses_dependency(app_build: str, artifact: str) -> bool:
    return f"org.mozilla.components:{artifact}:" in app_build


def find_mozilla_component_artifacts(app_build: str) -> list[str]:
    artifacts: list[str] = []
    pattern = re.compile(r"org\.mozilla\.components:([^:'\"]+):\$moz_components_version")
    for artifact in pattern.findall(app_build):
        if artifact not in artifacts:
            artifacts.append(artifact)
    return artifacts


def fetch_xml(url: str) -> ET.Element:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return ET.fromstring(response.read())
    except (ET.ParseError, TimeoutError, urllib.error.URLError) as exc:
        raise RuntimeError(f"Could not fetch {url}: {exc}") from exc


def fetch_url(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return response.read()
    except (TimeoutError, urllib.error.URLError) as exc:
        raise RuntimeError(f"Could not fetch {url}: {exc}") from exc


def artifact_pom_url(group: str, artifact: str, version: str) -> str:
    group_path = "/".join(quote(part) for part in group.split("."))
    artifact_path = quote(artifact)
    version_path = quote(version)
    return (
        f"{MOZILLA_MAVEN}/{group_path}/{artifact_path}/{version_path}/"
        f"{artifact_path}-{version_path}.pom"
    )


def artifact_exists(group: str, artifact: str, version: str) -> bool:
    try:
        fetch_url(artifact_pom_url(group, artifact, version))
        return True
    except RuntimeError:
        return False


def xml_text(
    root: ET.Element,
    path: str,
    namespaces: dict[str, str] | None = None,
) -> str | None:
    found = root.find(path, namespaces or {})
    if found is None:
        return None
    return found.text


def find_compatible_geckoview_version(moz_components_version: str) -> str | None:
    pom_url = (
        f"{MOZILLA_MAVEN}/org/mozilla/components/browser-engine-gecko-nightly/"
        f"{moz_components_version}/browser-engine-gecko-nightly-{moz_components_version}.pom"
    )
    pom = fetch_xml(pom_url)
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    for dependency in pom.findall("m:dependencies/m:dependency", namespace):
        group_id = xml_text(dependency, "m:groupId", namespace)
        artifact_id = xml_text(dependency, "m:artifactId", namespace)
        version = xml_text(dependency, "m:version", namespace)
        if group_id == "org.mozilla.geckoview" and artifact_id == "geckoview-nightly":
            return version
    return None


def print_local_compatibility(versions: dict[str, str], app_build: str) -> list[str]:
    print_section("Compatibility Checks")
    failures: list[str] = []
    moz_components_version = versions.get("moz_components_version")
    geckoview_version = versions.get("geckoview_version")

    if not moz_components_version:
        failures.append("moz_components_version is missing from the root build.gradle.")
    if not geckoview_version:
        failures.append("geckoview_version is missing from the root build.gradle.")

    expected_geckoview = KNOWN_GECKOVIEW_BY_BROWSER_ENGINE.get(moz_components_version or "")
    if expected_geckoview and geckoview_version == expected_geckoview:
        print(
            "ok: local GeckoView pin matches the known "
            f"browser-engine-gecko-nightly:{moz_components_version} POM."
        )
    elif expected_geckoview:
        failures.append(
            f"geckoview_version {geckoview_version} does not match "
            f"browser-engine-gecko-nightly:{moz_components_version} expected {expected_geckoview}."
        )
    else:
        print("info: no offline GeckoView compatibility record for this Android Components version.")

    if geckoview_version and "$geckoview_version" in app_build:
        print("ok: GeckoView is pinned through the shared geckoview_version property.")
    elif geckoview_version:
        failures.append("app/build.gradle does not use the shared geckoview_version property.")

    if uses_dependency(app_build, "feature-sendtab") and moz_components_version:
        if version_greater_than(moz_components_version, FEATURE_SENDTAB_LAST_PUBLISHED):
            failures.append(
                "feature-sendtab is still in use, but it was only published through "
                f"{FEATURE_SENDTAB_LAST_PUBLISHED}."
            )
        else:
            print(
                "ok: feature-sendtab is still within its known published version range; "
                "replace it before moving Android Components beyond 25.0.0."
            )

    if failures:
        for failure in failures:
            print(f"error: {failure}")
    else:
        print("No local compatibility errors found.")
    return failures


def print_remote_upstream(
    versions: dict[str, str],
    app_build: str,
    proposed_ac_version: str | None,
) -> list[str]:
    print_section("Remote Upstream")
    failures: list[str] = []
    moz_components_version = proposed_ac_version or versions.get("moz_components_version")
    geckoview_version = versions.get("geckoview_version")
    if proposed_ac_version:
        print(f"proposed Android Components version: {proposed_ac_version}")
    try:
        geckoview = fetch_xml(GECKOVIEW_METADATA)
        print(f"latest geckoview-nightly: {xml_text(geckoview, './versioning/latest')}")
    except RuntimeError as exc:
        print(exc)
        failures.append(str(exc))

    try:
        browser_engine = fetch_xml(BROWSER_ENGINE_GECKO_METADATA)
        print(
            "latest browser-engine-gecko-nightly: "
            f"{xml_text(browser_engine, './versioning/latest')}"
        )
    except RuntimeError as exc:
        print(exc)
        failures.append(str(exc))

    if moz_components_version:
        missing_artifacts: list[str] = []
        for artifact in find_mozilla_component_artifacts(app_build):
            if not artifact_exists("org.mozilla.components", artifact, moz_components_version):
                missing_artifacts.append(artifact)
        if missing_artifacts:
            failure = (
                f"missing org.mozilla.components artifacts for {moz_components_version}: "
                f"{', '.join(missing_artifacts)}"
            )
            print(f"error: {failure}")
            failures.append(failure)
        else:
            print(f"all declared org.mozilla.components artifacts exist for {moz_components_version}")

        try:
            compatible = find_compatible_geckoview_version(moz_components_version)
            print(
                f"browser-engine-gecko-nightly:{moz_components_version} declares "
                f"geckoview-nightly:{compatible or 'not found'}"
            )
            if compatible is None:
                failures.append(
                    f"browser-engine-gecko-nightly:{moz_components_version} POM does not declare GeckoView."
                )
            elif proposed_ac_version:
                print(
                    "proposed baseline requires "
                    f"geckoview_version = '{compatible}' if adopted."
                )
            elif geckoview_version and compatible != geckoview_version:
                failures.append(
                    f"geckoview_version {geckoview_version} does not match remote POM {compatible}."
                )
        except RuntimeError as exc:
            print(exc)
            failures.append(str(exc))
    return failures


def print_section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit local Mozilla dependency pins and upstream porting hotspots."
    )
    parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Query Mozilla Maven metadata for latest upstream versions.",
    )
    parser.add_argument(
        "--proposed-ac",
        metavar="VERSION",
        help="Check whether the current Mozilla Components artifact set exists for a proposed version.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 when compatibility checks fail.",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    root_build = read_text(repo / ROOT_BUILD)
    app_build = read_text(repo / APP_BUILD)
    buildsrc_build = read_text(repo / BUILDSRC_BUILD)

    versions = find_ext_versions(root_build)
    android_pins = find_android_pins(app_build)
    android_pin_values = pins_to_dict(android_pins)
    mozilla_deps = find_mozilla_dependencies(app_build)

    print(f"Repository: {repo}")

    print_section("Version Pins")
    for key in (
        "moz_components_version",
        "geckoview_version",
        "kotlin_version",
        "androidx_version",
        "architecture_components_version",
        "androidx_work_version",
        "robolectric_version",
    ):
        value = versions.get(key, "not found")
        print(f"{key}: {value}")

    print_section("Android Build Pins")
    for name, value in android_pins:
        print(f"{name}: {value}")

    print_section("Mozilla Dependencies")
    if mozilla_deps:
        for scope, coordinate in mozilla_deps:
            print(f"{scope}: {coordinate}")
    else:
        print("No Mozilla dependencies found in app/build.gradle")

    print_section("Upstream Porting Hotspots")
    hotspots = [
        "app/src/gecko/java/org/mozilla/tv/firefox/webrender/WebRenderComponents.kt",
        "app/src/system/java/org/mozilla/tv/firefox/webrender/WebRenderComponents.kt",
        "app/src/main/java/org/mozilla/tv/firefox/utils/Settings.kt",
        "app/src/main/java/org/mozilla/tv/firefox/webrender/WebRenderFragment.kt",
        "app/src/main/java/org/mozilla/tv/firefox/navigationoverlay/NavigationOverlayFragment.kt",
    ]
    for hotspot in hotspots:
        exists = "present" if (repo / hotspot).exists() else "missing"
        print(f"{exists}: {hotspot}")

    failures = print_local_compatibility(versions, app_build)

    print_section("Maintenance Warnings")
    combined_gradle = "\n".join((root_build, app_build, buildsrc_build))

    if "jcenter()" in combined_gradle:
        print("jcenter repository is still configured and should be removed during build modernization.")
    moz_components_version = versions.get("moz_components_version")
    if moz_components_version in {"24.0.0", "24.0.1", "26.0.0"}:
        print(
            f"Android Components are pinned to {moz_components_version}; "
            "expect API migration work for modern GeckoView."
        )
    if "classpath 'com.android.tools.build:gradle:3.4.1'" in root_build:
        print("Android Gradle Plugin is pinned to 3.4.1; modern SDK and Kotlin upgrades require staged changes.")
    if android_pin_values.get("targetSdkVersion") == "28":
        print("targetSdkVersion remains 28; raising it requires Android behavior and Fire TV testing.")
    if 'org.mozilla.geckoview:geckoview-nightly"' in app_build or "org.mozilla.geckoview:geckoview-nightly'" in app_build:
        print("GeckoView uses a floating nightly coordinate; pin exact versions for reproducible ports.")
    if not args.remote and versions.get("geckoview_version"):
        print("Run with --remote to verify GeckoView matches the browser-engine-gecko-nightly POM.")

    if args.proposed_ac and not args.remote:
        print("warning: --proposed-ac requires --remote; skipping proposed version checks.")
    if args.remote:
        failures.extend(print_remote_upstream(versions, app_build, args.proposed_ac))

    print_section("Reference Upstreams")
    print("mozilla-central: https://hg.mozilla.org/mozilla-central/")
    print("Firefox mirror: https://github.com/mozilla-firefox/firefox")
    print("Android Components: https://github.com/mozilla-mobile/android-components")
    print("GeckoView docs: https://firefox-source-docs.mozilla.org/mobile/android/geckoview/")

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
