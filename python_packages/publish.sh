#!/bin/bash
set -e

PROJECT_ID="af-aidevs"
LOCATION="europe-west6"
REPOSITORY="python-packages"

# Check if package name is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <package_name>"
    echo "Example: $0 utils"
    exit 1
fi

PACKAGE_NAME="$1"

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Check if the package directory exists
if [ ! -d "$PACKAGE_NAME" ]; then
    echo "Error: Directory '$PACKAGE_NAME' does not exist."
    exit 1
fi

cd "$PACKAGE_NAME"

echo "Building package '$PACKAGE_NAME'..."
uv build

echo "Getting access token..."
TOKEN=$(gcloud auth print-access-token)

echo "Publishing to Artifact Registry..."
uv publish --publish-url "https://${LOCATION}-python.pkg.dev/${PROJECT_ID}/${REPOSITORY}/" --username "oauth2accesstoken" --password "$TOKEN"

echo "Done!"
