import os
from pathlib import Path

# The workspace root is determined by the mounted GCS bucket (Cloud Storage FUSE)
WORKSPACE_MOUNT_ROOT = Path(os.getenv("WORKSPACE_MOUNT_ROOT", "/workspace"))
RESOURCE_NAME = "cr-mcp-web-gateway"
