import os
import re
import sys
import shutil
import tempfile
import zipfile

import requests


APP_ID = "hydros-pro.extractor"
APP_TITLE = "HydroS Pro"
UPDATE_DOWNLOAD_DIRNAME = "HydroS Pro Temp"
GITHUB_REPO = "CarlmanPaulus/HydroS-Pro"
RELEASE_URL = "https://github.com/CarlmanPaulus/HydroS-Pro/releases/latest"
RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def normalize_version(version_text):
    return (version_text or "").strip().lstrip("vV")


def parse_version(version_text):
    return tuple(int(part) for part in re.findall(r"\d+", normalize_version(version_text)))


def compare_versions(left, right):
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    width = max(len(left_parts), len(right_parts), 1)
    left_padded = left_parts + (0,) * (width - len(left_parts))
    right_padded = right_parts + (0,) * (width - len(right_parts))
    if left_padded < right_padded:
        return -1
    if left_padded > right_padded:
        return 1
    return 0


def is_newer_version(candidate, current):
    return compare_versions(candidate, current) > 0


def is_major_update(current_version, latest_version):
    current_parts = parse_version(current_version)
    latest_parts = parse_version(latest_version)
    current_major = current_parts[0] if current_parts else 0
    latest_major = latest_parts[0] if latest_parts else 0
    return latest_major > current_major


def fetch_remote_version():
    """Fetch the latest published app version from the GitHub releases API."""
    return fetch_latest_release(None)["release_version"]


def _select_asset_by_ext(assets, extensions):
    best_asset = None
    best_score = None
    for asset in assets or []:
        name = (asset.get("name") or "").lower()
        download_url = asset.get("browser_download_url")
        if not download_url or not any(name.endswith(ext) for ext in extensions):
            continue

        score = 0
        if APP_TITLE.lower() in name:
            score += 2
        if "debug" in name or "symbols" in name:
            score -= 6

        if best_score is None or score > best_score:
            best_asset = asset
            best_score = score
    return best_asset


def select_zip_asset(assets):
    return _select_asset_by_ext(assets, (".zip",))


def select_installer_asset(assets):
    asset = _select_asset_by_ext(assets, (".exe", ".msi"))
    if asset:
        name = (asset.get("name") or "").lower()
        if "setup" in name or "installer" in name:
            return asset
    return _select_asset_by_ext(assets, (".exe", ".msi"))


def fetch_latest_release(expected_version):
    response = requests.get(
        RELEASE_API_URL,
        timeout=10,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": APP_ID,
        },
    )
    response.raise_for_status()
    release = response.json()

    release_version = normalize_version(release.get("tag_name") or release.get("name") or "")
    if expected_version and release_version and compare_versions(release_version, expected_version) < 0:
        raise RuntimeError(
            f"Latest GitHub release is {release_version}, but the app expects at least {expected_version}. "
            "Please publish the matching release assets first."
        )

    return {
        "release_version": release_version or expected_version,
        "release_url": release.get("html_url") or RELEASE_URL,
        "assets": release.get("assets") or [],
    }


# Keep for backward compatibility
def fetch_latest_release_asset(expected_version):
    info = fetch_latest_release(expected_version)
    asset = select_installer_asset(info["assets"])
    if not asset:
        raise RuntimeError("No installer asset (.exe or .msi) was found in the latest GitHub release.")
    return {
        "release_version": info["release_version"],
        "release_url": info["release_url"],
        "asset_name": asset.get("name") or "setup.exe",
        "asset_url": asset["browser_download_url"],
    }


def get_update_download_dir():
    base_temp_dir = os.environ.get("TEMP") or tempfile.gettempdir()
    return os.path.join(base_temp_dir, UPDATE_DOWNLOAD_DIRNAME)


def get_install_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def cleanup_update_downloads(exclude_paths=None):
    update_dir = get_update_download_dir()
    if not os.path.isdir(update_dir):
        return

    excluded = {
        os.path.normcase(os.path.abspath(path))
        for path in (exclude_paths or [])
        if path
    }

    for entry in os.scandir(update_dir):
        if not entry.is_file():
            continue
        if os.path.splitext(entry.name)[1].lower() not in {".exe", ".msi", ".zip"}:
            continue

        full_path = os.path.normcase(os.path.abspath(entry.path))
        if full_path in excluded:
            continue

        try:
            os.remove(entry.path)
        except OSError:
            pass

    try:
        if not any(os.scandir(update_dir)):
            os.rmdir(update_dir)
    except OSError:
        pass


def make_unique_path(target_path):
    if not os.path.exists(target_path):
        return target_path

    base, ext = os.path.splitext(target_path)
    counter = 1
    while True:
        candidate = f"{base} ({counter}){ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def download_file(url, destination, status_callback=None, progress_callback=None):
    with requests.get(
        url,
        stream=True,
        timeout=(10, 120),
        allow_redirects=True,
        headers={"User-Agent": APP_ID},
    ) as response:
        response.raise_for_status()
        total_bytes = int(response.headers.get("content-length") or 0)
        downloaded = 0
        last_reported = -10

        with open(destination, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=262144):
                if not chunk:
                    continue
                file_obj.write(chunk)
                downloaded += len(chunk)

                if total_bytes and status_callback:
                    percent = int(downloaded * 100 / total_bytes)
                    if percent >= last_reported + 10 or percent == 100:
                        last_reported = percent
                        status_callback(f"Downloading update... {percent}%")
                if total_bytes and progress_callback:
                    percent = int(downloaded * 100 / total_bytes)
                    progress_callback(percent, 100)

    if status_callback:
        status_callback(f"Download complete: {os.path.basename(destination)}")
    if progress_callback:
        progress_callback(100, 100)

    return destination


def extract_patch_zip(zip_path, extract_dir):
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # The zip may contain a top-level folder (e.g. HydroS/) — detect and return it
    entries = os.listdir(extract_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
        return os.path.join(extract_dir, entries[0])
    return extract_dir


def write_patch_script(source_dir, install_dir):
    script_path = os.path.join(get_update_download_dir(), "_update.cmd")
    exe_name = os.path.basename(sys.executable)
    script = (
        '@echo off\r\n'
        'timeout /t 2 /nobreak >nul\r\n'
        f'taskkill /f /im "{exe_name}" >nul 2>&1\r\n'
        'timeout /t 1 /nobreak >nul\r\n'
        f'robocopy "{source_dir}" "{install_dir}" /E /NFL /NDL /NJH /NJS /R:3 /W:2\r\n'
        f'start "" "{os.path.join(install_dir, exe_name)}"\r\n'
        f'del "%~f0"\r\n'
    )
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    return script_path


def check_for_updates(current_version, callback):
    try:
        latest = fetch_remote_version()
        if is_newer_version(latest, current_version):
            callback(latest)
    except Exception as exc:
        print("Update check failed:", exc)
