"""Deterministic tactical navigation and pathfinding service with precomputed routing tables."""

import collections
import logging
from typing import Any, ClassVar

from schemas import (
    AlternativeDropoffRoute,
    CalculateRouteResponse,
    RouteLeg,
    TerrainType,
)

logger = logging.getLogger("services.navigation")


class NavigationService:
    """Precomputes and serves deterministic shortest paths on the 11x11 Domatowo city grid."""

    COL_LETTERS: ClassVar[str] = "ABCDEFGHIJK"
    GRID_WIDTH: ClassVar[int] = 11
    GRID_HEIGHT: ClassVar[int] = 11

    # Canonical 11x11 layout from course preview
    DEFAULT_GRID: ClassVar[dict[str, str]] = {
        # Row 1
        "A1": "DR",
        "B1": "UL",
        "C1": "UL",
        "D1": "UL",
        "E1": " ",
        "F1": "B3",
        "G1": "B3",
        "H1": "DR",
        "I1": " ",
        "J1": "PK",
        "K1": "PK",
        # Row 2
        "A2": "DR",
        "B2": "DR",
        "C2": " ",
        "D2": "UL",
        "E2": "UL",
        "F2": "B3",
        "G2": "B3",
        "H2": "DR",
        "I2": "UL",
        "J2": "PK",
        "K2": "PK",
        # Row 3
        "A3": " ",
        "B3": " ",
        "C3": " ",
        "D3": "UL",
        "E3": "PK",
        "F3": " ",
        "G3": " ",
        "H3": "DR",
        "I3": "UL",
        "J3": " ",
        "K3": " ",
        # Row 4
        "A4": "B1",
        "B4": "B1",
        "C4": " ",
        "D4": "UL",
        "E4": "PK",
        "F4": "SZ",
        "G4": "SZ",
        "H4": "SZ",
        "I4": "UL",
        "J4": "BS",
        "K4": "BS",
        # Row 5
        "A5": "B1",
        "B5": "B1",
        "C5": " ",
        "D5": "UL",
        "E5": "PK",
        "F5": "SZ",
        "G5": "SZ",
        "H5": "SZ",
        "I5": "UL",
        "J5": "BS",
        "K5": "BS",
        # Row 6
        "A6": "UL",
        "B6": "UL",
        "C6": "UL",
        "D6": "UL",
        "E6": "UL",
        "F6": "UL",
        "G6": "UL",
        "H6": "UL",
        "I6": "UL",
        "J6": "UL",
        "K6": " ",
        # Row 7
        "A7": "B2",
        "B7": "B2",
        "C7": " ",
        "D7": "UL",
        "E7": " ",
        "F7": "KS",
        "G7": "KS",
        "H7": "KS",
        "I7": " ",
        "J7": "DR",
        "K7": " ",
        # Row 8
        "A8": "B2",
        "B8": "B2",
        "C8": " ",
        "D8": "UL",
        "E8": " ",
        "F8": "KS",
        "G8": "KS",
        "H8": "KS",
        "I8": " ",
        "J8": "DR",
        "K8": " ",
        # Row 9
        "A9": " ",
        "B9": "UL",
        "C9": "UL",
        "D9": "UL",
        "E9": "UL",
        "F9": "UL",
        "G9": "UL",
        "H9": "UL",
        "I9": "UL",
        "J9": "UL",
        "K9": " ",
        # Row 10
        "A10": "B3",
        "B10": "B3",
        "C10": "B3",
        "D10": " ",
        "E10": "DR",
        "F10": " ",
        "G10": " ",
        "H10": "B3",
        "I10": "B3",
        "J10": "DR",
        "K10": " ",
        # Row 11
        "A11": "B3",
        "B11": "B3",
        "C11": "B3",
        "D11": " ",
        "E11": "DR",
        "F11": " ",
        "G11": " ",
        "H11": "B3",
        "I11": "B3",
        "J11": "DR",
        "K11": " ",
    }

    # B3 Target Clusters & Perimeter Sweep Sequences
    CLUSTERS: ClassVar[dict[str, list[str]]] = {
        "north": ["F1", "G1", "F2", "G2"],
        "south_east": ["H10", "I10", "H11", "I11"],
        "south_west": ["A10", "B10", "C10", "A11", "B11", "C11"],
    }

    CLOCKWISE_SWEEPS: ClassVar[dict[str, list[str]]] = {
        "north": ["F2", "G2", "G1", "F1"],
        "south_east": ["H10", "I10", "I11", "H11"],
        "south_west": ["B10", "A10", "A11", "B11", "C11", "C10"],
    }

    ALL_B3_TILES: ClassVar[list[str]] = [
        "F1",
        "G1",
        "F2",
        "G2",
        "H10",
        "I10",
        "H11",
        "I11",
        "A10",
        "B10",
        "C10",
        "A11",
        "B11",
        "C11",
    ]

    def __init__(self, custom_grid: dict[str, str] | None = None):
        self.grid = custom_grid or dict(self.DEFAULT_GRID)
        self.road_tiles = {k for k, v in self.grid.items() if v == TerrainType.ULICA}
        self.all_tiles = list(self.grid.keys())

        # Precomputed tables
        self.transporter_routes: dict[tuple[str, str], dict[str, Any]] = {}
        self.scout_routes: dict[tuple[str, str], list[str]] = {}

        self._precompute_all_tables()

    @classmethod
    def to_coords(cls, tile: str) -> tuple[int, int]:
        """Converts coordinate string (e.g. 'F2') to (col_idx, row_idx)."""
        col_letter = tile[0].upper()
        col_idx = cls.COL_LETTERS.index(col_letter)
        row_idx = int(tile[1:]) - 1
        return col_idx, row_idx

    @classmethod
    def to_tile(cls, col_idx: int, row_idx: int) -> str:
        """Converts (col_idx, row_idx) to coordinate string (e.g. 'F2')."""
        return f"{cls.COL_LETTERS[col_idx]}{row_idx + 1}"

    def get_neighbors(self, tile: str) -> list[str]:
        """Returns 4-directional adjacent valid tiles within grid boundaries."""
        c, r = self.to_coords(tile)
        neighbors = []
        for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nc, nr = c + dc, r + dr
            if 0 <= nc < self.GRID_WIDTH and 0 <= nr < self.GRID_HEIGHT:
                neighbors.append(self.to_tile(nc, nr))
        return neighbors

    def find_shortest_path(
        self, origin: str, destination: str, allowed_tiles: set[str]
    ) -> list[str] | None:
        """Finds shortest path using BFS over allowed_tiles."""
        if origin not in allowed_tiles or destination not in allowed_tiles:
            return None
        if origin == destination:
            return [origin]

        queue = collections.deque([(origin, [origin])])
        visited = {origin}

        while queue:
            curr, path = queue.popleft()
            for neighbor in self.get_neighbors(curr):
                if neighbor == destination:
                    return path + [neighbor]
                if neighbor in allowed_tiles and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    def _precompute_all_tables(self):
        """Generates all-pairs precomputed routes for both transporters and scouts in <10ms."""
        # 1. Scout routes: passable terrain is all tiles except impassable obstacles (DR)
        passable_scout = {k for k, v in self.grid.items() if v != TerrainType.DRZEWA}

        for origin in self.all_tiles:
            if origin not in passable_scout:
                continue
            for target in self.ALL_B3_TILES:
                path = self.find_shortest_path(origin, target, passable_scout)
                if path:
                    self.scout_routes[(origin, target)] = path

        # 2. Transporter routes: strictly over road_tiles
        for road_origin in self.road_tiles:
            for target_b3 in self.ALL_B3_TILES:
                # Find all road tiles adjacent to target_b3 on scout network
                adjacent_roads = [
                    n for n in self.get_neighbors(target_b3) if n in self.road_tiles
                ]

                best_combined = None
                for dropoff in adjacent_roads:
                    road_path = self.find_shortest_path(
                        road_origin, dropoff, self.road_tiles
                    )
                    if road_path:
                        trans_cost = len(road_path) - 1
                        scout_cost = 7  # 1 step from adjacent road into building
                        total_cost = trans_cost + scout_cost
                        if (
                            best_combined is None
                            or total_cost < best_combined["total_trip_ap_cost"]
                        ):
                            best_combined = {
                                "dropoff_tile": dropoff,
                                "transporter_path": road_path,
                                "transporter_ap_cost": trans_cost,
                                "scout_foot_path": [dropoff, target_b3],
                                "scout_ap_cost": scout_cost,
                                "total_trip_ap_cost": total_cost,
                            }
                if best_combined:
                    self.transporter_routes[(road_origin, target_b3)] = best_combined

        logger.info(
            f"Precomputed {len(self.transporter_routes)} transporter routes and {len(self.scout_routes)} scout routes."
        )

    def calculate_route(
        self,
        origin: str,
        destination: str | None = None,
        target_symbol: str | None = None,
        unit_type: str = "transporter",
        reasoning: str = "",
    ) -> CalculateRouteResponse:
        """Calculates optimal path and AP expenditure for transporter or scout."""
        origin = origin.upper().strip()

        # Handle target_symbol query (e.g. 'B3' or 'BLOK_3P')
        if target_symbol and not destination:
            # Find nearest B3 tile from origin
            best_plan = None
            best_cost = 9999
            for cand in self.ALL_B3_TILES:
                plan = self.calculate_route(
                    origin=origin,
                    destination=cand,
                    unit_type=unit_type,
                    reasoning=reasoning,
                )
                cost = (
                    plan.route.ap_cost
                    if plan.direct_route_possible and plan.route
                    else (
                        plan.recommended_alternative_route.total_trip_ap_cost
                        if plan.recommended_alternative_route
                        else 9999
                    )
                )
                if best_plan is None or cost < best_cost:
                    best_cost = cost
                    best_plan = plan
            if best_plan:
                return best_plan
            destination = "F2"

        if not destination:
            destination = "F2"

        destination = destination.upper().strip()

        # TRANSPORTER NAVIGATION
        if unit_type == "transporter":
            # Check if destination is on road
            if destination in self.road_tiles:
                road_path = self.find_shortest_path(
                    origin, destination, self.road_tiles
                )
                if road_path:
                    steps = len(road_path) - 1
                    return CalculateRouteResponse(
                        direct_route_possible=True,
                        route=RouteLeg(
                            path=road_path,
                            steps=steps,
                            ap_cost=steps,  # 1 AP per road step
                            unit_type="transporter",
                        ),
                        tactical_briefing=f"Direct road route available from {origin} to {destination} ({steps} steps, {steps} AP).",
                        hint="Execute transporter movement along road path.",
                    )

            # Destination is OFF-ROAD: look up precomputed alternative dropoff
            if (origin, destination) in self.transporter_routes:
                rec = self.transporter_routes[(origin, destination)]
                alt = AlternativeDropoffRoute(
                    dropoff_tile=rec["dropoff_tile"],
                    transporter_path=rec["transporter_path"],
                    transporter_ap_cost=rec["transporter_ap_cost"],
                    scout_foot_path=rec["scout_foot_path"],
                    scout_ap_cost=rec["scout_ap_cost"],
                    total_trip_ap_cost=rec["total_trip_ap_cost"],
                )
                return CalculateRouteResponse(
                    direct_route_possible=False,
                    reason=f"Destination {destination} is off-road for transporter ({self.grid.get(destination, 'Unknown')}).",
                    recommended_alternative_route=alt,
                    tactical_briefing=(
                        f"Drive transporter from {origin} to drop-off tile {alt.dropoff_tile} ({alt.transporter_ap_cost} AP), "
                        f"disembark scout (0 AP), walk 1 step into {destination} ({alt.scout_ap_cost} AP). Total cost: {alt.total_trip_ap_cost} AP."
                    ),
                    hint="Move transporter to recommended drop-off tile, disembark scout, and step into building.",
                )

        # SCOUT NAVIGATION
        passable_scout = {k for k, v in self.grid.items() if v != TerrainType.DRZEWA}
        foot_path = self.find_shortest_path(origin, destination, passable_scout)
        if foot_path:
            steps = len(foot_path) - 1
            ap_cost = steps * 7  # 7 AP per foot step
            return CalculateRouteResponse(
                direct_route_possible=True,
                route=RouteLeg(
                    path=foot_path,
                    steps=steps,
                    ap_cost=ap_cost,
                    unit_type="scout",
                ),
                tactical_briefing=f"Scout foot path from {origin} to {destination} ({steps} steps, {ap_cost} AP).",
                hint="Move scout on foot to destination tile.",
            )

        return CalculateRouteResponse(
            direct_route_possible=False,
            reason=f"No passable path found from {origin} to {destination} for unit {unit_type}.",
            tactical_briefing=f"Unable to chart path from {origin} to {destination}.",
            hint="Select an alternative destination or reposition unit.",
        )
