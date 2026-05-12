# Python Packages

This directory contains shared Python packages for the AI_Devs course.

## Useful Commands

To check available Python versions in `uv` (both installed and available for download):
```bash
uv python list
```

## Installing Packages from Private Repository (Artifact Registry)

To install packages in another project (or generate a lock file) without manually entering a password, set the environment variables for `uv` (assuming the index name in `pyproject.toml` is `gar`):

```bash
export UV_INDEX_GAR_USERNAME="oauth2accesstoken"
export UV_INDEX_GAR_PASSWORD=$(gcloud auth print-access-token)
```

After setting these variables, you can safely run:
```bash
uv lock
# or
uv sync
```
This will allow `uv` to automatically use these credentials to authenticate with the `gar` index.
