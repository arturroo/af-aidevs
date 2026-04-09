import os
import json
from pathlib import Path
from geopy.geocoders import Nominatim
import time

def main():
    base_dir = Path(__file__).parent.absolute()
    source_file = base_dir / "data" / "findhim_locations.json"
    cache_dir = base_dir / "data" / "cache"
    cache_file = cache_dir / "power_plants_augmented.json"
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {source_file}: {e}")
        return

    plants = data.get("power_plants", {})
    geolocator = Nominatim(user_agent="ai_devs_s01e02_agent")
    
    print("Inicjalizacja cache elektrowni...")
    augmented_plants = {}
    
    for city, info in plants.items():
        # Żarnowiec is tricky, appending Poland helps Geopy accurately find it.
        if city == "Żarnowiec":
            search_query = "Elektrownia Jądrowa Żarnowiec, Poland"
        elif city == "Chelmno":
            search_query = "Chełmno, Poland"
        else:
            search_query = f"{city}, Poland"
            
        print(f" Szukam współrzędnych dla: {search_query}")
        try:
            location = geolocator.geocode(search_query)
            if location:
                augmented_plants[city] = {
                    **info,
                    "lat": location.latitude,
                    "lon": location.longitude
                }
                print(f"   Znaleziono: {location.latitude}, {location.longitude}")
            else:
                print("   Nie znaleziono dokładnych koordynatów!")
                augmented_plants[city] = info
                
            time.sleep(1) # Zabezpieczenie przed rate limitem nominatim
        except Exception as e:
            print(f"Błąd przy geokodowaniu {city}: {e}")
            augmented_plants[city] = info
    
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(augmented_plants, f, indent=4, ensure_ascii=False)
        
    print(f"\nCache utworzono pomyślnie i zapisano do {cache_file}")

if __name__ == "__main__":
    main()
