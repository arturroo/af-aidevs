"""Build and populate the SQLite inventory database with vector embeddings.

Reads cities.csv, items.csv, and connections.csv, generates embeddings
using Vertex AI text-multilingual-embedding-002 (768d), indexes vectors
with sqlite-vec, and optionally uploads the database to GCS.
"""

import argparse
import csv
import gzip
import logging
import sqlite3
import struct
import sys
from pathlib import Path
from typing import List

import sqlite_vec
from google import genai
from google.cloud import storage
from google.genai import types

# Add parent directory to path so config can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (  # noqa: E402
    DATA_DIR,
    EMBEDDING_MODEL,
    GCS_WORKSPACE_BUCKET,
    GOOGLE_CLOUD_LOCATION,
    GOOGLE_CLOUD_PROJECT,
    INVENTORY_DB_GCS_PATH,
    INVENTORY_DB_PATH,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def serialize_float32(vector: List[float]) -> bytes:
    """Serialize a list of floats to binary float32 buffer for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def init_database(db_path: Path) -> sqlite3.Connection:
    """Create tables and vec0 virtual table in SQLite database."""
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")

    # Relational schema
    cursor.execute("""
        CREATE TABLE cities (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
    """)
    cursor.execute("CREATE INDEX idx_cities_name ON cities(name);")

    cursor.execute("""
        CREATE TABLE items (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
    """)
    cursor.execute("CREATE INDEX idx_items_name ON items(name);")

    cursor.execute("""
        CREATE TABLE connections (
            itemCode TEXT NOT NULL,
            cityCode TEXT NOT NULL,
            PRIMARY KEY (itemCode, cityCode),
            FOREIGN KEY (itemCode) REFERENCES items(code),
            FOREIGN KEY (cityCode) REFERENCES cities(code)
        );
    """)
    cursor.execute("CREATE INDEX idx_conn_item ON connections(itemCode);")
    cursor.execute("CREATE INDEX idx_conn_city ON connections(cityCode);")

    # Vector virtual table for semantic search (768 dimensions)
    cursor.execute("""
        CREATE VIRTUAL TABLE vec_items USING vec0(
            item_code TEXT PRIMARY KEY,
            embedding float[768]
        );
    """)
    conn.commit()
    return conn


def load_csv_data(conn: sqlite3.Connection, data_dir: Path) -> List[dict]:
    """Ingest cities, items, and connections from CSV files into SQLite."""
    cursor = conn.cursor()

    # Ingest cities.csv (name, code)
    cities_file = data_dir / "cities.csv"
    logger.info("Loading cities from %s", cities_file)
    with open(cities_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cities_data = [(row["code"].strip(), row["name"].strip()) for row in reader]
    cursor.executemany("INSERT INTO cities (code, name) VALUES (?, ?);", cities_data)

    # Ingest items.csv (name, code)
    items_file = data_dir / "items.csv"
    logger.info("Loading items from %s", items_file)
    with open(items_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        items_raw = [{"code": row["code"].strip(), "name": row["name"].strip()} for row in reader]
    cursor.executemany(
        "INSERT INTO items (code, name) VALUES (?, ?);",
        [(item["code"], item["name"]) for item in items_raw],
    )

    # Ingest connections.csv (itemCode, cityCode)
    conn_file = data_dir / "connections.csv"
    logger.info("Loading connections from %s", conn_file)
    with open(conn_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        connections_data = [(row["itemCode"].strip(), row["cityCode"].strip()) for row in reader]
    cursor.executemany(
        "INSERT INTO connections (itemCode, cityCode) VALUES (?, ?);", connections_data
    )

    conn.commit()
    logger.info(
        "Loaded %d cities, %d items, %d connections",
        len(cities_data),
        len(items_raw),
        len(connections_data),
    )
    return items_raw


def generate_and_insert_embeddings(
    conn: sqlite3.Connection, items: List[dict], batch_size: int = 100
) -> None:
    """Generate embeddings via Vertex AI and insert into vec_items virtual table."""
    client = genai.Client(
        vertexai=True,
        project=GOOGLE_CLOUD_PROJECT,
        location=GOOGLE_CLOUD_LOCATION,
    )

    cursor = conn.cursor()
    total_items = len(items)
    logger.info(
        "Generating embeddings for %d items using model %s (batch size %d)...",
        total_items,
        EMBEDDING_MODEL,
        batch_size,
    )

    for i in range(0, total_items, batch_size):
        batch = items[i : i + batch_size]

        if "gemini-embedding" in EMBEDDING_MODEL:
            # Gemini Embedding 2 asymmetric document format
            contents = [f"title: none | text: {item['name']}" for item in batch]
            config = types.EmbedContentConfig(output_dimensionality=768)
        else:
            contents = [item["name"] for item in batch]
            config = types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,
            )

        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=contents,
                config=config,
            )
            embeddings = [emb.values for emb in response.embeddings]
        except Exception as e:
            logger.error("Failed to generate embeddings for batch starting at %d: %s", i, e)
            raise

        insert_data = [
            (batch[j]["code"], serialize_float32(embeddings[j])) for j in range(len(batch))
        ]
        cursor.executemany(
            "INSERT INTO vec_items(item_code, embedding) VALUES (?, ?);", insert_data
        )
        conn.commit()
        logger.info("Embedded and inserted %d / %d items...", min(i + batch_size, total_items), total_items)


def upload_to_gcs(local_db_path: Path, bucket_name: str, gcs_dest_path: str) -> None:
    """Upload database to Google Cloud Storage shared workspace layer (both raw and .gz)."""
    storage_client = storage.Client(project=GOOGLE_CLOUD_PROJECT)
    bucket = storage_client.bucket(bucket_name)

    # 1. Upload raw database
    logger.info("Uploading %s to gs://%s/%s...", local_db_path, bucket_name, gcs_dest_path)
    blob_raw = bucket.blob(gcs_dest_path)
    blob_raw.upload_from_filename(str(local_db_path))

    # 2. Upload gzip compressed database (for network egress optimization)
    gz_dest_path = f"{gcs_dest_path}.gz" if not gcs_dest_path.endswith(".gz") else gcs_dest_path
    logger.info("Compressing and uploading gs://%s/%s...", bucket_name, gz_dest_path)
    raw_bytes = local_db_path.read_bytes()
    compressed_bytes = gzip.compress(raw_bytes, compresslevel=6)
    blob_gz = bucket.blob(gz_dest_path)
    blob_gz.upload_from_string(compressed_bytes, content_type="application/gzip")

    logger.info(
        "Successfully uploaded inventory.db (%d bytes) and inventory.db.gz (%d bytes) to GCS.",
        len(raw_bytes),
        len(compressed_bytes),
    )


def main():
    parser = argparse.ArgumentParser(description="Build and index SQLite inventory database.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=INVENTORY_DB_PATH,
        help="Target local path for inventory.db",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Directory containing cities.csv, items.csv, and connections.csv",
    )
    parser.add_argument(
        "--skip-gcs-upload",
        action="store_true",
        help="Skip uploading the generated database to GCS",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation (useful for quick local schema tests)",
    )
    args = parser.parse_args()

    conn = init_database(args.db_path)
    items = load_csv_data(conn, args.data_dir)

    if not args.skip_embeddings:
        generate_and_insert_embeddings(conn, items)
    else:
        logger.warning("Skipping embeddings generation as requested (--skip-embeddings).")

    conn.close()
    logger.info("Database build complete at: %s", args.db_path)

    if not args.skip_gcs_upload:
        upload_to_gcs(args.db_path, GCS_WORKSPACE_BUCKET, INVENTORY_DB_GCS_PATH)
    else:
        logger.info("Skipped GCS upload as requested.")


if __name__ == "__main__":
    main()
