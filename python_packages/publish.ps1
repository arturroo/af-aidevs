$ErrorActionPreference = "Stop"

$PROJECT_ID = "af-aidevs"
$LOCATION = "europe-west6"
$REPOSITORY = "python-packages"

param (
    [Parameter(Mandatory=$true)]
    [string]$PackageName
)

# Ensure we are in the script's directory
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $PSScriptRoot

# Check if the package directory exists
if (!(Test-Path $PackageName)) {
    Write-Error "Directory '$PackageName' does not exist."
    exit 1
}

Set-Location $PackageName

Write-Host "Building package '$PackageName'..." -ForegroundColor Cyan
uv build

Write-Host "Getting access token..." -ForegroundColor Cyan
$TOKEN = gcloud auth print-access-token

Write-Host "Publishing to Artifact Registry..." -ForegroundColor Cyan
uv publish --publish-url "https://${LOCATION}-python.pkg.dev/${PROJECT_ID}/${REPOSITORY}/" --username "oauth2accesstoken" --password $TOKEN

Write-Host "Done!" -ForegroundColor Green
