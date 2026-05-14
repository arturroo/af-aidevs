#!/bin/bash
set -e

PROJECT_ID="af-aidevs"
LOCATION="europe-west6"
REPOSITORY="python-packages"

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Czyszczenie katalogu dist, aby nie publikować starych wersji
echo "Cleaning dist directory..."
rm -rf dist/

# --- AUTOMATYCZNE PODBIJANIE WERSJI (PATCH) ---
echo "Bumping patch version in pyproject.toml..."
python3 -c "
import re
with open('pyproject.toml', 'r') as f:
    content = f.read()
# Szukamy version = \"X.Y.Z\"
match = re.search(r'version\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"', content)
if match:
    major, minor, patch = match.groups()
    new_version = f'{major}.{minor}.{int(patch)+1}'
    # Podmieniamy tylko linię z wersją
    new_content = re.sub(r'version\s*=\s*\".*\"', f'version = \"{new_version}\"', content, count=1)
    with open('pyproject.toml', 'w') as f:
        f.write(new_content)
    print(f'Version bumped to: {new_version}')
else:
    print('Could not find version in pyproject.toml')
    exit(1)
"

echo "Getting access token..."
TOKEN=$(gcloud auth print-access-token)

# Eksport zmiennych dla uv do autoryzacji z Artifact Registry
export UV_INDEX_GAR_USERNAME="oauth2accesstoken"
export UV_INDEX_GAR_PASSWORD="$TOKEN"

echo "Building package from current directory..."
uv build

echo "Publishing to Artifact Registry..."
uv publish --publish-url "https://${LOCATION}-python.pkg.dev/${PROJECT_ID}/${REPOSITORY}/" --username "oauth2accesstoken" --password "$TOKEN"

echo "Done!"
