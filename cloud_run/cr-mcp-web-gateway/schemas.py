from pydantic import BaseModel, Field


class FetchWebResourceResponse(BaseModel):
    output_path: str = Field(description="Relative workspace path where file was saved")
    size_bytes: int = Field(description="Size of the downloaded file in bytes")
    mime_type: str = Field(description="MIME type derived from HTTP Content-Type or file extension")
    is_binary: bool = Field(description="True if resource is binary (zip, image, etc.), False if text/json/markdown")
    sha256: str = Field(description="SHA-256 integrity checksum computed before disk write")
    status: str = Field(default="success", description="Status message")
    hint: str | None = Field(default=None, description="Operational guidance or next steps")
