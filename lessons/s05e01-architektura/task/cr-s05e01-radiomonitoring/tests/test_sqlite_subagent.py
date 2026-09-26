import sqlite3

from agents.sqlite_subagent import SQLiteSubagent
from services.mcp_service import MCPService


def test_sqlite_introspection():
    # Build an in-memory database to serialize
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE cities (id INTEGER PRIMARY KEY, name TEXT, area REAL, warehouses INTEGER);"
    )
    cur.execute(
        "INSERT INTO cities (name, area, warehouses) VALUES ('Opalino', 14.85, 12);"
    )
    conn.commit()
    db_bytes = conn.serialize()
    conn.close()

    mcp = MCPService()
    subagent = SQLiteSubagent(mcp_service=mcp)
    schemas, dumps = subagent.introspect_and_dump(db_bytes)

    assert "cities" in schemas
    assert "CREATE TABLE cities" in schemas["cities"]
    assert "cities" in dumps
    assert len(dumps["cities"]) == 1
    assert dumps["cities"][0]["name"] == "Opalino"
    assert dumps["cities"][0]["warehouses"] == 12
