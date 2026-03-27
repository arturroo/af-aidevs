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

def find_closest_plant(file_id: str, reasoning: str) -> str:
    """
    Kalkulator przyjmujący identyfikator pliku z lokalizacjami danej osoby, porównujący je 
    względem współrzędnych Elektrowni zapisanych w naszym lokalnym środowisku, by sprawdzić
    czy badana osoba była chociaż raz w bliskiej odległości.
    
    Args:
        file_id: Identyfikator pliku (np. loc_Jan_Kowalski).
        reasoning: Krótkie uzasadnienie agenta (Chain of Thought), dlaczego wywołuje to narzędzie (np. "Muszę sprawdzić odległość dla osoby XYZ...").
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
    
    # Zabezpieczone parsowanie (plik może być listą słowników lub słownikiem z listą)
    if isinstance(person_locations, list):
        locs = person_locations
    elif isinstance(person_locations, dict):
        locs = person_locations.get("locations", [])
        if not locs and isinstance(person_locations.get("message"), dict):
            locs = person_locations["message"].get("locations", [])
    else:
        locs = []
        
    for p_loc in locs:
        p_lat = p_loc.get("latitude")
        p_lon = p_loc.get("longitude")
        
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
                
    # Wydobywamy "Personę/Zmienną śledztwa" z nazwy pliku
    osoba = safe_file_id.replace("loc_", "").replace(".json", "").replace("_", " ")

    # ---------------------------------------------------------------------------------------------------------
    # [BEST PRACTICE Z PRODUKCJI - CONTEXT THREADING / TRACEABILITY]
    # LLM wysłał nam tylko 'file_id', więc ryzykujemy, że zapomni do kogo należał plik w nawale danych.
    # Wstrzykujemy wydobytą personę ręcznie w prefix odpowiedzi, redukując Context Drift.
    # ---------------------------------------------------------------------------------------------------------
    prefix = f"[Śledztwo: {osoba}]"
                
    if closest_distance < 20:  # Zwykle elektrownia to bliskość paru kilometrów, bezpieczny buffor 20km
        return f"{prefix} Znaleziono powiązanie! Osoba znajdowała się zaledwie {closest_distance:.1f} km od elektrowni '{closest_city}'. Jej kod, którego będziesz potrzebować do zweryfikowania śledczego to: {plant_code}."
    else:
        return f"{prefix} Ta osoba jest 'czysta'. Najbliższa elektrownia znajdowała się aż {closest_distance:.1f} km od jej miejsc logowania, nie stanowi podejrzeń."
