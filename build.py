import argparse
import datetime
import json
import os
import shutil
import site
import sys
import zipfile

import PyInstaller.__main__

# Default version
VERSION = "1.0.0"


def find_path_in_site_packages(target_path):
    """Find a path in site-packages or create a fallback"""
    site_packages_paths = site.getsitepackages()
    print(f"Looking for {target_path} in {len(site_packages_paths)} site-packages paths")

    for path in site_packages_paths:
        potential_path = os.path.join(path, target_path)
        if os.path.exists(potential_path):
            print(f"Found {target_path} at: {potential_path}")
            return potential_path

    # Create fallback if not found
    fallback_path = os.path.join(os.getcwd(), f"{target_path.replace('/', '_')}_fallback")
    os.makedirs(fallback_path, exist_ok=True)
    print(f"Created fallback path at: {fallback_path}")
    return fallback_path


def extract_version():
    """Get version from git tag, version.txt, or use default"""
    # Try from GitHub Actions
    github_ref = os.environ.get('GITHUB_REF', '')
    if github_ref.startswith('refs/tags/v'):
        version = github_ref.replace('refs/tags/v', '')
        print(f"Using version from GitHub tag: {version}")
        return version

    # Try from git command
    try:
        import subprocess
        result = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            tag = result.stdout.strip()
            if tag.startswith('v'):
                version = tag[1:]
                print(f"Using version from git tag: {version}")
                return version
    except Exception:
        pass

    # Try from version.txt
    version_file = os.path.join(os.getcwd(), 'version.txt')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            version = f.read().strip()
        print(f"Using version from version.txt: {version}")
        return version

    # Use default
    print(f"Using default version: {VERSION}")
    return VERSION


def update_app_configjson(version, build_time):
    """Update version information in app_config.json at top level, creating the file if it doesn't exist"""
    current_dir = os.getcwd()
    config_dir = os.path.join(current_dir, 'assets', 'config')
    app_configjson_path = os.path.join(config_dir, 'app_config.json')

    try:
        # Create directory structure if it doesn't exist
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
            print(f"Created directory: {config_dir}")

        # Initialize config
        if os.path.exists(app_configjson_path):
            print(f"Reading existing JSON at: {app_configjson_path}")
            with open(app_configjson_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            print(f"app_config.json not found. Creating new file at: {app_configjson_path}")
            config = {}  # Initialize empty config if file doesn't exist

        # Add version info at top level
        config["version"] = version
        config["build_time"] = build_time

        # Save updated config
        with open(app_configjson_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        print(f"Successfully updated version info in app_config.json")
        return True
    except Exception as e:
        print(f"Error updating app_config.json: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Build script for MFWPH')
    parser.add_argument('--version', '-v', help='Version number to use')
    parser.add_argument('--keep-files', '-k', action='store_true',
                        help='Keep intermediate files in dist directory')
    parser.add_argument('--zip-name', '-z', help='Custom name for the output zip file (without .zip extension)')
    parser.add_argument('--exclude', '-e', nargs='+',
                        default=['.git', '.github', '.gitignore', '.gitmodules', '.nicegui', '.idea'],
                        help='List of file/folder names to exclude from the zip package')
    args = parser.parse_args()

    # Setup build parameters
    current_dir = os.getcwd()
    dist_dir = os.path.join(current_dir, 'dist')
    build_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    version = args.version or extract_version()

    # Always use MFWPH for the executable name
    exe_name = "MFWPH"

    # Package name for the zip file (with version)
    if args.zip_name:
        package_name = args.zip_name
        zip_filename = f"{package_name}.zip"
    else:
        package_name = f"MFWPH_{version}"
        zip_filename = f"{package_name}_{build_time}.zip"

    zip_filepath = os.path.join(dist_dir, zip_filename)

    print(f"Starting build process for MFWPH version {version}")
    print(f"Executable will be named: {exe_name}.exe")
    print(f"Zip package will be named: {zip_filename}")

    os.makedirs(dist_dir, exist_ok=True)

    # Update version in app_config.json
    update_app_configjson(version, build_time)

    # Find required paths
    maa_bin_path = find_path_in_site_packages('maa/bin')
    maa_agent_binary_path = find_path_in_site_packages('MaaAgentBinary')

    # Create logs directory in dist
    logs_dir = os.path.join(dist_dir, 'logs')
    logs_backup_dir = os.path.join(logs_dir, 'backup')
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(logs_backup_dir, exist_ok=True)

    # Create an empty app.log file to include in the zip
    with open(os.path.join(logs_dir, 'app.log'), 'w', encoding='utf-8') as f:
        f.write(f"Log file created on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Run PyInstaller
    print("Starting PyInstaller...")
    pyinstaller_args = [
        'main.py',
        '--onefile',
        '--windowed',  # No console window will appear
        f'--name={exe_name}',
        '--clean',
        '--uac-admin',
        f'--add-data={maa_bin_path}{os.pathsep}maa/bin',
        f'--add-data={maa_agent_binary_path}{os.pathsep}MaaAgentBinary'
    ]

    try:
        PyInstaller.__main__.run(pyinstaller_args)
        print("PyInstaller completed successfully")
    except Exception as e:
        print(f"PyInstaller failed: {str(e)}")
        sys.exit(1)

    # Copy assets folder
    assets_source_path = os.path.join(current_dir, 'assets')
    assets_dest_path = os.path.join(dist_dir, 'assets')
    if os.path.exists(assets_source_path):
        print(f"Copying assets from {assets_source_path} to {assets_dest_path}")
        if os.path.exists(assets_dest_path):
            shutil.rmtree(assets_dest_path)
        shutil.copytree(assets_source_path, assets_dest_path)
    else:
        print(f"Warning: assets folder not found at {assets_source_path}")

    # Define exclusion list
    excluded_items = args.exclude if args.exclude else ['.git', '.github', '.gitignore', '.gitmodules', '.nicegui',
                                                        '.idea','config','debug']
    print(f"Excluded items from zip: {', '.join(excluded_items)}")

    # Create zip package
    print(f"Creating zip file: {zip_filepath}")
    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        files_added = 0
        skipped_items = 0

        # Walk through directory structure
        for root, dirs, files in os.walk(dist_dir):
            # Modify dirs in-place to skip excluded directories
            # This prevents os.walk from traversing into excluded directories
            dirs[:] = [d for d in dirs if d not in excluded_items]

            for file in files:
                # Skip the current zip file itself
                if file == os.path.basename(zip_filepath):
                    continue

                # Skip excluded files
                if file in excluded_items:
                    print(f"Skipping excluded file: {file}")
                    skipped_items += 1
                    continue

                # Check if any parent directory is in excluded items
                rel_dir = os.path.relpath(root, dist_dir)
                if any(part in excluded_items for part in rel_dir.split(os.sep) if part):
                    skipped_items += 1
                    continue

                # Add file to zip
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)
                files_added += 1

        print(f"Added {files_added} files to zip, skipped {skipped_items} excluded items")

    print(f"Build process completed successfully. Output: {zip_filepath}")
    print(f"::set-output name=zip_file::{zip_filepath}")
    print(f"::set-output name=version::{version}")
    sys.exit(0)


if __name__ == "__main__":
    main()