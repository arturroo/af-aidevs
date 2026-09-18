"""Unit tests for Multi-State A* pathfinding and resource solver."""

import pytest
from schemas import Coordinate, TerrainMap, VehicleSpec
from services.solver_service import SolverService


@pytest.fixture
def empty_terrain():
    """10x10 plain terrain with start at (0,0) and dest at (2,2)."""
    grid = [["plain" for _ in range(10)] for _ in range(10)]
    return TerrainMap(
        grid=grid,
        start=Coordinate(x=0, y=0),
        destination=Coordinate(x=2, y=2),
    )


@pytest.fixture
def terrain_with_river():
    """10x10 terrain with a river from y=0 to y=8 at x=1, leaving a passage at (1, 9)."""
    grid = [["plain" for _ in range(10)] for _ in range(10)]
    for y in range(9):
        grid[y][1] = "river"
    return TerrainMap(
        grid=grid,
        start=Coordinate(x=0, y=0),
        destination=Coordinate(x=2, y=0),
    )


def test_solve_simple_path(empty_terrain):
    rover = VehicleSpec(
        name="rover",
        fuel_per_move=1.0,
        food_per_move=0.5,
        speed=1.0,
        traversable_tiles=["plain"],
    )
    res = SolverService.solve_single_mode(
        terrain=empty_terrain,
        vehicle=rover,
        initial_fuel=10.0,
        initial_food=10.0,
    )
    assert res is not None
    assert res["success"] is True
    assert res["vehicle"] == "rover"
    assert res["steps"] == 4  # Manhattan distance (0,0) to (2,2) = 4
    assert res["fuel_remaining"] == 6.0  # 10 - 4*1.0 = 6.0
    assert res["food_remaining"] == 8.0  # 10 - 4*0.5 = 8.0
    assert res["itinerary"][0] == "rover"
    assert len(res["itinerary"]) == 5  # ["rover", dir1, dir2, dir3, dir4]


def test_obstacle_avoidance(terrain_with_river):
    rover = VehicleSpec(
        name="rover",
        fuel_per_move=0.5,
        food_per_move=0.2,
        speed=1.0,
        traversable_tiles=["plain"],
    )
    res = SolverService.solve_single_mode(
        terrain=terrain_with_river,
        vehicle=rover,
        initial_fuel=10.0,
        initial_food=10.0,
    )
    assert res is not None
    assert res["success"] is True
    # The rover must go down to row 9 to bypass the river, cross at x=1, then go up to (2,0)
    # Total distance: (0,0)->(0,9) [9] + (0,9)->(1,9) [1] + (1,9)->(2,9) [1] + (2,9)->(2,0) [9] = 20 steps
    assert res["steps"] == 20
    assert res["fuel_remaining"] == 0.0  # 10 - 20*0.5 = 0.0


def test_resource_exhaustion_fails(empty_terrain):
    # A gas guzzler burning 3.0 fuel per step on a 4-step path (requires 12 fuel, but only 10 provided)
    gas_guzzler = VehicleSpec(
        name="heavy_tank",
        fuel_per_move=3.0,
        food_per_move=0.5,
        speed=1.0,
        traversable_tiles=["plain"],
    )
    res = SolverService.solve_single_mode(
        terrain=empty_terrain,
        vehicle=gas_guzzler,
        initial_fuel=10.0,
        initial_food=10.0,
    )
    assert res is None


def test_multimodal_transition(empty_terrain):
    # Car runs out of fuel after 2 steps (fuel_rate = 5.0, fuel=10), then dismounts to foot
    car = VehicleSpec(
        name="sports_car",
        fuel_per_move=5.0,
        food_per_move=0.5,
        speed=2.0,
        traversable_tiles=["plain"],
    )
    foot = VehicleSpec(
        name="foot",
        fuel_per_move=0.0,
        food_per_move=1.0,
        speed=1.0,
        traversable_tiles=["plain"],
    )

    res = SolverService.solve_multimodal(
        terrain=empty_terrain,
        vehicle=car,
        foot_spec=foot,
        initial_fuel=10.0,
        initial_food=10.0,
    )
    assert res is not None
    assert res["success"] is True
    assert res["steps"] == 4
    assert res["itinerary"][0] == "sports_car"
    assert "dismount" in res["itinerary"]


def test_find_best_route_picks_most_efficient(empty_terrain):
    v1_inefficient = VehicleSpec(name="gas_truck", fuel_per_move=2.0, food_per_move=1.0)
    v2_efficient = VehicleSpec(name="electric_rover", fuel_per_move=0.5, food_per_move=0.5)

    best = SolverService.find_best_route(
        terrain=empty_terrain,
        vehicles=[v1_inefficient, v2_efficient],
    )
    assert best is not None
    assert best["vehicle"] == "electric_rover"


def test_savethem_skolwin_multimodal_rocket_to_walk():
    """Simulates the actual S03E05 Skolwin terrain grid with unbroken river barrier."""
    raw_grid = [
        list("........WW"),
        list(".......WW."),
        list(".T....WW.."),
        list("......W..."),
        list("..T...W.G."),
        list("....R.W..."),
        list("...RR.WW.."),
        list("SR.....W.."),
        list("......WW.."),
        list(".....WW..."),
    ]
    terrain = TerrainMap(
        grid=raw_grid,
        start=Coordinate(x=0, y=7),
        destination=Coordinate(x=8, y=4),
    )

    rocket = VehicleSpec(name="rocket", fuel_per_move=1.0, food_per_move=0.1)
    car = VehicleSpec(name="car", fuel_per_move=0.7, food_per_move=1.0)
    horse = VehicleSpec(name="horse", fuel_per_move=0.0, food_per_move=1.6)
    walk = VehicleSpec(name="walk", fuel_per_move=0.0, food_per_move=2.5)

    best = SolverService.find_best_route(
        terrain=terrain,
        vehicles=[rocket, car, horse, walk],
        initial_fuel=10.0,
        initial_food=10.0,
    )

    assert best is not None, "Solver must find a valid route across the river"
    assert best["success"] is True
    assert best["vehicle"] == "rocket"
    assert best["fuel_remaining"] >= 0.0
    assert best["food_remaining"] >= 0.0
    assert best["itinerary"][0] == "rocket"
    assert "dismount" in best["itinerary"], "Itinerary must contain 'dismount' transition token"
    assert best["itinerary"] == [
        "rocket", "up", "right", "right", "up", "right", "up", "right", "right", "dismount", "right", "right", "right"
    ]
    assert len(best["itinerary"]) == 13
