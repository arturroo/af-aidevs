"""Deterministic state-space graph search engine (Multi-State A* / Dijkstra) for S03E05 savethem."""

import heapq
import logging
from typing import Dict, List, Optional, Set, Tuple
from schemas import Coordinate, TerrainMap, VehicleSpec

logger = logging.getLogger("services.solver")

# Movement vectors on 10x10 grid: (dx, dy)
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

# Standard impassable obstacle tiles unless vehicle explicitly allows them
DEFAULT_OBSTACLES: Set[str] = {
    "river",
    "water",
    "deep_water",
    "rock",
    "rocks",
    "mountain",
    "mountains",
    "wall",
    "x",
    "r",
    "w",
    "m",
}


class SolverService:
    """Finds mathematically optimal, collision-free paths across 10x10 terrain within fuel/food budgets."""

    @staticmethod
    def is_tile_passable(tile: str, vehicle: VehicleSpec) -> bool:
        """Determines if a tile can be traversed by the given vehicle/mode."""
        normalized = tile.strip().lower()

        # Plain ground, start, and goal are universally passable for all ground modes
        if normalized in {".", "s", "g", "start", "goal", "plain", "road", "base", "city", "ground"}:
            return True

        v_name = vehicle.name.lower()

        # Water/river tiles: passable ONLY on foot/walk (wading/swimming), destroyed for vehicles
        if normalized in {"w", "water", "river", "deep_water"}:
            return v_name in {"walk", "foot", "walking"}

        # Rocks, walls and mountains: impassable for all ground vehicles and foot
        if normalized in {"r", "m", "rock", "rocks", "mountain", "mountains", "wall", "x"}:
            return False

        # Trees/forest: passable on foot or horse, blocked for car/rocket
        if normalized in {"t", "tree", "trees", "forest"}:
            return v_name in {"walk", "foot", "walking", "horse"}

        if vehicle.traversable_tiles:
            allowed = [t.lower() for t in vehicle.traversable_tiles]
            if normalized in allowed:
                return True

        # Fallback: check if tile is in obstacle list
        if normalized in DEFAULT_OBSTACLES:
            return False

        return True

    @classmethod
    def solve_single_mode(
        cls,
        terrain: TerrainMap,
        vehicle: VehicleSpec,
        initial_fuel: float = 10.0,
        initial_food: float = 10.0,
    ) -> Optional[Dict]:
        """Runs A* search from start to destination using a single vehicle/mode throughout."""
        start_x, start_y = terrain.start.x, terrain.start.y
        dest_x, dest_y = terrain.destination.x, terrain.destination.y

        # Priority queue entries: (cost, steps, x, y, fuel, food, path)
        # Cost = steps - remaining_resources_bonus
        initial_state = (0, 0, start_x, start_y, initial_fuel, initial_food, [])
        heap = [initial_state]

        # Visited tracker: (x, y) -> max (fuel, food)
        visited: Dict[Tuple[int, int], Tuple[float, float]] = {}

        while heap:
            _, steps, cx, cy, fuel, food, path = heapq.heappop(heap)

            if cx == dest_x and cy == dest_y:
                return {
                    "vehicle": vehicle.name,
                    "itinerary": [vehicle.name] + path,
                    "steps": steps,
                    "fuel_remaining": fuel,
                    "food_remaining": food,
                    "success": True,
                }

            state_key = (cx, cy)
            if state_key in visited:
                v_fuel, v_food = visited[state_key]
                if fuel <= v_fuel and food <= v_food:
                    continue
            visited[state_key] = (fuel, food)

            for dname, (dx, dy) in DIRECTIONS.items():
                nx, ny = cx + dx, cy + dy

                # Check grid boundaries
                if not (0 <= nx < terrain.width and 0 <= ny < terrain.height):
                    continue

                # Check terrain traversability
                tile = terrain.grid[ny][nx]
                if not cls.is_tile_passable(tile, vehicle):
                    continue

                # Deduct resources
                n_fuel = round(fuel - vehicle.fuel_per_move, 2)
                n_food = round(food - vehicle.food_per_move, 2)

                if n_fuel < 0.0 or n_food < 0.0:
                    continue

                manhattan = abs(dest_x - nx) + abs(dest_y - ny)
                # A* priority heuristic: prefer shorter path and higher remaining resources
                priority = (steps + 1) + manhattan - (n_fuel + n_food) * 0.1

                heapq.heappush(
                    heap,
                    (priority, steps + 1, nx, ny, n_fuel, n_food, path + [dname]),
                )

        return None

    @classmethod
    def solve_multimodal(
        cls,
        terrain: TerrainMap,
        vehicle: VehicleSpec,
        foot_spec: VehicleSpec,
        initial_fuel: float = 10.0,
        initial_food: float = 10.0,
    ) -> Optional[Dict]:
        """Runs Multi-State A* permitting a one-way dismount transition from vehicle to foot."""
        start_x, start_y = terrain.start.x, terrain.start.y
        dest_x, dest_y = terrain.destination.x, terrain.destination.y

        # State: (cost, steps, x, y, current_mode, fuel, food, path)
        initial_state = (0, 0, start_x, start_y, vehicle.name, initial_fuel, initial_food, [])
        heap = [initial_state]

        # Visited: (x, y, mode) -> (fuel, food)
        visited: Dict[Tuple[int, int, str], Tuple[float, float]] = {}

        while heap:
            _, steps, cx, cy, mode, fuel, food, path = heapq.heappop(heap)

            if cx == dest_x and cy == dest_y:
                return {
                    "vehicle": vehicle.name,
                    "itinerary": [vehicle.name] + path,
                    "steps": steps,
                    "fuel_remaining": fuel,
                    "food_remaining": food,
                    "success": True,
                }

            state_key = (cx, cy, mode)
            if state_key in visited:
                v_fuel, v_food = visited[state_key]
                if fuel <= v_fuel and food <= v_food:
                    continue
            visited[state_key] = (fuel, food)

            cur_spec = vehicle if mode == vehicle.name else foot_spec

            # 1. Normal moves in current mode
            for dname, (dx, dy) in DIRECTIONS.items():
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < terrain.width and 0 <= ny < terrain.height):
                    continue

                tile = terrain.grid[ny][nx]
                if not cls.is_tile_passable(tile, cur_spec):
                    continue

                n_fuel = round(fuel - cur_spec.fuel_per_move, 2)
                n_food = round(food - cur_spec.food_per_move, 2)

                if n_fuel < 0.0 or n_food < 0.0:
                    continue

                manhattan = abs(dest_x - nx) + abs(dest_y - ny)
                priority = (steps + 1) + manhattan - (n_fuel + n_food) * 0.1

                heapq.heappush(
                    heap,
                    (priority, steps + 1, nx, ny, mode, n_fuel, n_food, path + [dname]),
                )

            # 2. Dismount to foot if currently in vehicle
            if mode == vehicle.name and vehicle.name != foot_spec.name:
                manhattan = abs(dest_x - cx) + abs(dest_y - cy)
                priority = steps + manhattan - (fuel + food) * 0.1 + 0.05
                heapq.heappush(
                    heap,
                    (
                        priority,
                        steps,
                        cx,
                        cy,
                        foot_spec.name,
                        fuel,
                        food,
                        path + ["dismount"],
                    ),
                )

        return None

    @classmethod
    def find_best_route(
        cls,
        terrain: TerrainMap,
        vehicles: List[VehicleSpec],
        foot_spec: Optional[VehicleSpec] = None,
        initial_fuel: float = 10.0,
        initial_food: float = 10.0,
    ) -> Optional[Dict]:
        """Evaluates all candidate vehicles and foot travel to select the optimal route."""
        # Detect foot_spec from candidate vehicles if not passed explicitly
        effective_foot = foot_spec
        if not effective_foot and vehicles:
            for v in vehicles:
                if v.name.lower() in {"walk", "foot", "walking"}:
                    effective_foot = v
                    break

        if not effective_foot:
            effective_foot = VehicleSpec(
                name="walk",
                fuel_per_move=0.0,
                food_per_move=2.5,
                speed=1.0,
                traversable_tiles=[".", "s", "g", "plain", "road", "grass", "tree", "forest", "sand", "base", "city", "w", "water", "river"],
            )

        candidates: List[Dict] = []
        eval_vehicles = list(vehicles) if vehicles else [
            VehicleSpec(name="rocket", fuel_per_move=1.0, food_per_move=0.1, speed=1.0),
            VehicleSpec(name="car", fuel_per_move=0.7, food_per_move=1.0, speed=1.0),
            VehicleSpec(name="horse", fuel_per_move=0.0, food_per_move=1.6, speed=1.0),
            VehicleSpec(name="walk", fuel_per_move=0.0, food_per_move=2.5, speed=1.0),
        ]

        # 1. Evaluate single-mode route for each candidate vehicle
        for v in eval_vehicles:
            res = cls.solve_single_mode(
                terrain=terrain,
                vehicle=v,
                initial_fuel=initial_fuel,
                initial_food=initial_food,
            )
            if res and res["success"]:
                candidates.append(res)

        # 2. Evaluate pure foot travel
        foot_res = cls.solve_single_mode(
            terrain=terrain,
            vehicle=effective_foot,
            initial_fuel=initial_fuel,
            initial_food=initial_food,
        )
        if foot_res and foot_res["success"]:
            candidates.append(foot_res)

        # 3. If no single-mode path found, evaluate multimodal transitions
        if not candidates:
            for v in eval_vehicles:
                if v.name.lower() in {"walk", "foot", "walking"}:
                    continue
                multi_res = cls.solve_multimodal(
                    terrain=terrain,
                    vehicle=v,
                    foot_spec=effective_foot,
                    initial_fuel=initial_fuel,
                    initial_food=initial_food,
                )
                if multi_res and multi_res["success"]:
                    candidates.append(multi_res)

        if not candidates:
            logger.error("No valid route found within fuel and food constraints!")
            return None

        # Sort candidates by minimum resource margin (most robust) then shortest steps
        candidates.sort(
            key=lambda c: (
                min(c["fuel_remaining"], c["food_remaining"]),
                c["fuel_remaining"] + c["food_remaining"],
                -c["steps"],
            ),
            reverse=True,
        )
        best = candidates[0]
        logger.info(
            f"Best route selected: vehicle={best['vehicle']}, steps={best['steps']}, "
            f"fuel_left={best['fuel_remaining']}, food_left={best['food_remaining']}"
        )
        return best
