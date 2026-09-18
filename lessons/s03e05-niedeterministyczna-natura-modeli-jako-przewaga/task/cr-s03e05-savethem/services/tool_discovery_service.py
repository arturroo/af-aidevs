"""Tool discovery and dynamic invocation service for S03E05 savethem."""

from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import config
from schemas import Coordinate, DiscoveredTool, TerrainMap, VehicleSpec
from services.mcp_service import MCPService

logger = logging.getLogger("services.discovery")
ZURICH_TZ = ZoneInfo("Europe/Zurich")


class ToolDiscoveryService:
    """Discovers domain tools via toolsearch and manages remote tool execution with workspace persistence."""

    def __init__(self, mcp_service: MCPService):
        self.mcp = mcp_service
        self.toolsearch_url = config.AIDEVS_TOOLSEARCH_URL
        self.api_key = config.AIDEVS_API_KEY
        # In-memory query cache: (tool_url, query) -> response_dict
        self._query_cache: Dict[str, Any] = {}
        # Registered tool definitions: name -> DiscoveredTool
        self.known_tools: Dict[str, DiscoveredTool] = {}
        # Cached domain entities
        self.cached_terrain: Optional[TerrainMap] = None
        self.cached_vehicles: List[VehicleSpec] = []
        self.cached_foot_spec: Optional[VehicleSpec] = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensures endpoint URLs have an http/https scheme and hostname."""
        trimmed = url.strip()
        # Intercept localhost or 127.0.0.1 and remap to AIDEVS_BASE_URL
        if "localhost" in trimmed or "127.0.0.1" in trimmed:
            trimmed = re.sub(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?", "", trimmed)
        if not trimmed.startswith("http://") and not trimmed.startswith("https://"):
            path = trimmed.lstrip("/")
            if not path.startswith("api/") and not path.startswith("verify"):
                path = f"api/{path}"
            return f"{config.AIDEVS_BASE_URL.rstrip('/')}/{path}"
        return trimmed

    async def search_tools(self, session_id: str, query: str) -> List[DiscoveredTool]:
        """Queries $AIDEVS_API_TOOLSEARCH and caches discovered tools."""
        cache_key = f"toolsearch:{query.strip().lower()}"
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        payload = {"apikey": self.api_key, "query": query}
        logger.info(f"Querying toolsearch: '{query}' via MCP Web Gateway")

        res = await self.mcp.post_web_resource(
            session_id=session_id,
            url=self.toolsearch_url,
            payload=payload,
        )

        discovered: List[DiscoveredTool] = []

        # Parse tool results (handles various response structures from Centrala)
        tools_list = res.get("tools") or res.get("results") or res.get("data")
        if not tools_list and isinstance(res, list):
            tools_list = res
        elif not tools_list and "raw_output" in res:
            try:
                parsed = json.loads(res["raw_output"])
                tools_list = parsed.get("tools") or parsed.get("results") or []
            except Exception:
                pass

        if isinstance(tools_list, list):
            for item in tools_list:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("tool") or item.get("title") or "unknown_tool"
                    raw_url = item.get("url") or item.get("endpoint") or item.get("URL") or ""
                    desc = item.get("description") or item.get("desc") or str(item)
                    if raw_url:
                        url = self._normalize_url(raw_url)
                        tool_obj = DiscoveredTool(name=name, url=url, description=desc)
                        discovered.append(tool_obj)
                        self.known_tools[name] = tool_obj
                        # Persist tool documentation to cr-mcp-workspace
                        spec_md = (
                            f"# Tool Specification: {name}\n\n"
                            f"- **Endpoint**: {url}\n"
                            f"- **Description**: {desc}\n\n"
                            f"### Example Payload\n"
                            f"```json\n{{\"apikey\": \"$AIDEVS_API_KEY\", \"query\": \"...\"}}\n```\n"
                        )
                        await self.mcp.write_file(
                            session_id=session_id,
                            file_path=f"tools/{name}.md",
                            content=spec_md,
                            reasoning=f"Persist tool specification for {name}",
                        )

        self._query_cache[cache_key] = discovered
        return discovered

    async def invoke_remote_tool(
        self,
        session_id: str,
        tool_name: str,
        query: str,
        endpoint_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calls a remote tool via cr-mcp-web-gateway, saving the response in cr-mcp-workspace."""
        clean_name = tool_name.strip()
        if endpoint_url and endpoint_url.strip():
            resolved_url = self._normalize_url(endpoint_url)
        elif clean_name in self.known_tools:
            resolved_url = self.known_tools[clean_name].url
        else:
            path = clean_name.lstrip("/")
            if not path.startswith("api/") and not path.startswith("verify"):
                path = f"api/{path}"
            resolved_url = f"{config.AIDEVS_BASE_URL.rstrip('/')}/{path}"

        cache_key = f"{resolved_url}:{query.strip().lower()}"
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        payload = {"apikey": self.api_key, "query": query}
        logger.info(f"Invoking remote tool '{clean_name}' at {resolved_url} with query: '{query}'")

        res = await self.mcp.post_web_resource(
            session_id=session_id,
            url=resolved_url,
            payload=payload,
        )

        now_str = datetime.now(ZURICH_TZ).strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", query[:30]).strip("_")
        workspace_file = f"tools/{tool_name}/{now_str}_{slug}.md"

        content_md = (
            f"# Tool Invocation: {tool_name}\n\n"
            f"- **Timestamp**: {now_str}\n"
            f"- **Endpoint**: {resolved_url}\n"
            f"- **Query**: {query}\n\n"
            f"## Response Payload\n"
            f"```json\n{json.dumps(res, indent=2, ensure_ascii=False)}\n```\n"
        )
        await self.mcp.write_file(
            session_id=session_id,
            file_path=workspace_file,
            content=content_md,
            reasoning=f"Log remote tool response for {tool_name}",
        )

        # Inspect if this tool returned map or vehicle data and update cache
        self._inspect_and_update_cache(tool_name, res)

        self._query_cache[cache_key] = res
        return res

    def _inspect_and_update_cache(self, tool_name: str, res: Dict[str, Any]):
        """Inspects tool response payloads to automatically extract map or vehicle specifications."""
        # 1. Map tile extraction
        grid_data = (
            res.get("grid")
            or res.get("map")
            or res.get("tiles")
            or res.get("terrain")
            or res.get("data")
        )
        if isinstance(grid_data, str):
            lines = [l.strip() for l in grid_data.strip().splitlines() if l.strip()]
            if len(lines) == 10:
                grid_data = lines

        if isinstance(grid_data, list) and len(grid_data) == 10:
            formatted_grid = []
            for row in grid_data:
                if isinstance(row, str):
                    formatted_grid.append(list(row))
                elif isinstance(row, list):
                    formatted_grid.append([str(c) for c in row])
                else:
                    formatted_grid = None
                    break

            if formatted_grid and len(formatted_grid) == 10:
                start_coord = None
                dest_coord = None

                # 1. Scan grid characters for 'S' (Start) and 'G' (Goal)
                for r_idx, row in enumerate(formatted_grid):
                    for c_idx, cell in enumerate(row):
                        cell_str = str(cell).strip().upper()
                        if cell_str == "S":
                            start_coord = Coordinate(x=c_idx, y=r_idx)
                        elif cell_str == "G":
                            dest_coord = Coordinate(x=c_idx, y=r_idx)

                # 2. Fallback to explicit fields or known defaults if not found in grid
                if not start_coord:
                    start_raw = res.get("start") or res.get("base") or {"x": 0, "y": 7}
                    if isinstance(start_raw, (list, tuple)) and len(start_raw) == 2:
                        start_coord = Coordinate(x=start_raw[0], y=start_raw[1])
                    elif isinstance(start_raw, dict):
                        start_coord = Coordinate(
                            x=start_raw.get("x", start_raw.get("col", 0)),
                            y=start_raw.get("y", start_raw.get("row", 7)),
                        )
                    else:
                        start_coord = Coordinate(x=0, y=7)

                if not dest_coord:
                    dest_raw = (
                        res.get("destination")
                        or res.get("end")
                        or res.get("target")
                        or res.get("skolwin")
                        or {"x": 8, "y": 4}
                    )
                    if isinstance(dest_raw, (list, tuple)) and len(dest_raw) == 2:
                        dest_coord = Coordinate(x=dest_raw[0], y=dest_raw[1])
                    elif isinstance(dest_raw, dict):
                        dest_coord = Coordinate(
                            x=dest_raw.get("x", dest_raw.get("col", 8)),
                            y=dest_raw.get("y", dest_raw.get("row", 4)),
                        )
                    else:
                        dest_coord = Coordinate(x=8, y=4)

                self.cached_terrain = TerrainMap(
                    grid=formatted_grid,
                    start=start_coord,
                    destination=dest_coord,
                )
                logger.info(
                    f"Successfully parsed and cached 10x10 TerrainMap: "
                    f"start=({start_coord.x}, {start_coord.y}), destination=({dest_coord.x}, {dest_coord.y})"
                )

        # 2. Vehicle specs extraction
        v_list = (
            res.get("vehicles")
            or res.get("results")
            or res.get("items")
            or res.get("fleet")
            or res.get("transport")
        )
        items_to_parse = []
        if isinstance(v_list, list):
            items_to_parse.extend(v_list)
        elif isinstance(res, dict) and "name" in res:
            items_to_parse.append(res)
        elif isinstance(res, list):
            items_to_parse.extend([x for x in res if isinstance(x, dict) and "name" in x])

        for v in items_to_parse:
            if isinstance(v, dict) and "name" in v:
                try:
                    v_name = str(v["name"]).strip().lower()
                    fuel_raw = v.get("fuel") or v.get("fuel_per_move") or v.get("fuel_consumption")
                    food_raw = v.get("food") or v.get("food_per_move") or v.get("food_consumption")
                    speed_raw = v.get("speed")

                    # If missing, try regex parsing from note or text
                    note_text = str(v.get("note") or v.get("description") or "")
                    if fuel_raw is None and note_text:
                        m_fuel = re.search(r"fuel[^\d]*(\d+(?:\.\d+)?)", note_text, re.IGNORECASE)
                        if m_fuel:
                            fuel_raw = float(m_fuel.group(1))
                    if food_raw is None and note_text:
                        m_food = re.search(r"food[^\d]*(\d+(?:\.\d+)?)", note_text, re.IGNORECASE)
                        if m_food:
                            food_raw = float(m_food.group(1))

                    # Resilient defaults if not explicitly numeric in JSON
                    if fuel_raw is None:
                        fuel_raw = 0.7 if v_name == "car" else (0.0 if v_name in {"horse", "walk", "foot"} else 1.0)
                    if food_raw is None:
                        food_raw = 1.0 if v_name == "car" else (1.6 if v_name == "horse" else (2.5 if v_name in {"walk", "foot"} else 1.0))

                    fuel_val = float(fuel_raw)
                    food_val = float(food_raw)
                    speed_val = float(speed_raw or 1.0)
                    trav = v.get("traversable_tiles") or [".", "s", "g", "plain", "road", "base", "city", "tree", "forest"]

                    v_spec = VehicleSpec(
                        name=v_name,
                        fuel_per_move=fuel_val,
                        food_per_move=food_val,
                        speed=speed_val,
                        traversable_tiles=trav,
                        description=v.get("description") or v.get("note"),
                    )
                    if v_spec.name in {"foot", "walking", "walk"}:
                        self.cached_foot_spec = v_spec
                    else:
                        if not any(x.name == v_spec.name for x in self.cached_vehicles):
                            self.cached_vehicles.append(v_spec)
                    logger.info(f"Parsed vehicle spec: {v_spec.name} (fuel={fuel_val}, food={food_val})")
                except Exception as e:
                    logger.warning(f"Failed to parse VehicleSpec: {e}")
