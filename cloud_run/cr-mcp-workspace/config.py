import os
from pathlib import Path

# The workspace root is determined by the mounted GCS bucket (Cloud Storage FUSE)
# Typically mounted at /mnt/workspaces
WORKSPACE_MOUNT_ROOT = Path(os.getenv("WORKSPACE_MOUNT_ROOT", "/mnt/workspaces"))
RESOURCE_NAME = "cr-mcp-workspace"
