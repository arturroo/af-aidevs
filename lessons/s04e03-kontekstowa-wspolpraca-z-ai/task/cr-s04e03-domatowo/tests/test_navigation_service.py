"""Unit tests for deterministic navigation and precomputed routing tables in S04E03."""

import pytest

from services.navigation_service import NavigationService


@pytest.fixture
def nav():
    return NavigationService()


def test_coordinate_conversion(nav):
    assert nav.to_coords("A1") == (0, 0)
    assert nav.to_coords("B1") == (1, 0)
    assert nav.to_coords("K11") == (10, 10)
    assert nav.to_coords("F2") == (5, 1)

    assert nav.to_tile(0, 0) == "A1"
    assert nav.to_tile(1, 0) == "B1"
    assert nav.to_tile(10, 10) == "K11"
    assert nav.to_tile(5, 1) == "F2"


def test_neighbors(nav):
    # Corner
    a1_neighbors = nav.get_neighbors("A1")
    assert sorted(a1_neighbors) == sorted(["B1", "A2"])

    # Center
    d6_neighbors = nav.get_neighbors("D6")
    assert sorted(d6_neighbors) == sorted(["C6", "E6", "D5", "D7"])


def test_precomputed_tables_loaded(nav):
    # Verify all 14 B3 tiles exist in ALL_B3_TILES
    assert len(nav.ALL_B3_TILES) == 14
    assert "F2" in nav.ALL_B3_TILES
    assert "B10" in nav.ALL_B3_TILES
    assert "H10" in nav.ALL_B3_TILES

    # Check that precomputed routes are populated
    assert len(nav.transporter_routes) > 0
    assert len(nav.scout_routes) > 0


def test_direct_transporter_road_route(nav):
    # B1 to E2 is entirely along the road network (B1 -> C1 -> D1 -> D2 -> E2)
    resp = nav.calculate_route(origin="B1", destination="E2", unit_type="transporter")
    assert resp.direct_route_possible is True
    assert resp.route is not None
    assert resp.route.path[0] == "B1"
    assert resp.route.path[-1] == "E2"
    assert resp.route.ap_cost == 4  # 4 steps along road * 1 AP
    assert resp.route.unit_type == "transporter"


def test_alternative_dropoff_for_offroad_building(nav):
    # F2 is a B3 building. A transporter cannot drive onto F2.
    resp = nav.calculate_route(origin="B1", destination="F2", unit_type="transporter")
    assert resp.direct_route_possible is False
    assert resp.recommended_alternative_route is not None
    alt = resp.recommended_alternative_route
    assert alt.dropoff_tile == "E2"  # E2 is the adjacent road
    assert alt.transporter_path[-1] == "E2"
    assert alt.scout_foot_path == ["E2", "F2"]
    assert alt.scout_ap_cost == 7  # 1 foot step * 7 AP
    assert alt.transporter_ap_cost == 4
    assert alt.total_trip_ap_cost == 11


def test_target_symbol_nearest_cluster_query(nav):
    # When querying target_symbol="B3" from B1, the North cluster (F2) is closest
    resp = nav.calculate_route(origin="B1", target_symbol="B3", unit_type="transporter")
    assert resp.recommended_alternative_route is not None
    assert resp.recommended_alternative_route.dropoff_tile == "E2"


def test_scout_foot_patrol(nav):
    # Scout walking from E2 into F2
    resp = nav.calculate_route(origin="E2", destination="F2", unit_type="scout")
    assert resp.direct_route_possible is True
    assert resp.route is not None
    assert resp.route.path == ["E2", "F2"]
    assert resp.route.ap_cost == 7  # 1 step * 7 AP
    assert resp.route.unit_type == "scout"


def test_clockwise_sweep_sequences(nav):
    north_sweep = nav.CLOCKWISE_SWEEPS["north"]
    assert north_sweep == ["F2", "G2", "G1", "F1"]

    se_sweep = nav.CLOCKWISE_SWEEPS["south_east"]
    assert se_sweep == ["H10", "I10", "I11", "H11"]

    sw_sweep = nav.CLOCKWISE_SWEEPS["south_west"]
    assert sw_sweep == ["B10", "A10", "A11", "B11", "C11", "C10"]
