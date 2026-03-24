import math
import os
import json
from pathlib import Path

def haversine(lat1, lon1, lat2, lon2):
    """
    Oblicza najkrótszą odległość sferyczną pomiędzy dwoma punktami (Haversine formula).
    """
    R = 6371.0 # Promień ziemi w km
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def find_closest_plant(file_id: str) -> str:
    """
    Kalkulator przyjmujący identyfikator pliku z lokalizacjami danej osoby, porównujący je 
    względem współrzędnych Elektrowni zapisanych w naszym lokalnym środowisku, by sprawdzić
    czy badana osoba była chociaż raz w bliskiej odległości.
    """
    base_dir = Path(__file__).parent.parent.absolute()
    
    # 1. Odczyt pre-cache elektrowni
    cache_file = base_dir / "data" / "cache" / "power_plants_augmented.json"
    if not cache_file.exists():
        return "Błąd: Brak zasilonego cache elektrowni. Nie można policzyć dystansu. Rozpocznij procedurę inicjalizacji środowiska przez admina."
        
    with open(cache_file, "r", encoding="utf-8") as f:
        power_plants = json.load(f)
        
    # 2. Path Traversal Protection - narzucamy os.path.basename żeby agent nas nie zhakował
    safe_file_id = os.path.basename(file_id)
    if not safe_file_id.endswith(".json"):
        safe_file_id += ".json"
        
    locations_file = base_dir / "data" / "get_person_locations" / safe_file_id
    if not locations_file.exists():
        return f"Błąd: Nie znaleziono zrzuconej teczki z zapisem nawigacji pod ID '{file_id}'. Prawdopodobnie nie użyłeś jeszcze narzędzia namierzającego telefon."
        
    with open(locations_file, "r", encoding="utf-8") as f:
        person_locations = json.load(f)
    
    # Analiza matematyczna (Boilerplate dla oszczędzenia zamieszania logiki LLMa)
    closest_distance = float('inf')
    closest_city = None
    plant_code = None
    
    if "locations" not in person_locations.get("message", "{}"):
        # The structure is directly a dict with message? We should check API response format.
        # Format returns: {"message": "Locations found", "locations": [{"lat": 50.1, "lon": 19.3}, ...]}
        pass
        
    locs = person_locations.get("locations", [])
    if not locs and "message" in person_locations:
        locs = person_locations.get("message", {}).get("locations", [])
        
    if not locs:
        # Fallback if the body is a direct list
        locs = person_locations if isinstance(person_locations, list) else []
        
    for p_loc in locs:
        p_lat = p_loc.get("lat")
        p_lon = p_loc.get("lon")
        
        if p_lat is None or p_lon is None: continue
        
        for city, info in power_plants.items():
            c_lat = info.get("lat")
            c_lon = info.get("lon")
            if c_lat is None or c_lon is None: continue
            
            dist = haversine(p_lat, p_lon, c_lat, c_lon)
            if dist < closest_distance:
                closest_distance = dist
                closest_city = city
                plant_code = info.get("code")
                
    if closest_distance < 20:  # Zwykle elektrownia to bliskość paru kilometrów, bezpieczny buffor 20km
        return f"Znaleziono powiązanie! Osoba znajdowała się zaledwie {closest_distance:.1f} km od elektrowni '{closest_city}'. Jej kod, którego będziesz potrzebować do zweryfikowania śledczego to: {plant_code}."
    else:
        return f"Ta osoba jest "czysta". Najbliższa elektrownia znajdowała się aż {closest_distance:.1f} km od jej miejsc logowania, nie stanowi podejrzeń."
