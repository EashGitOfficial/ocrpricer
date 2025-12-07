import math
import sys
from scrapper import RealTimeScraper

# ==========================================
# PART 1: THE REFERENCE MODEL (BASELINE)
# ==========================================

class ReferenceModel:
    def __init__(self):
        self.hubs = {
            "miami":        {"coords": (25.7617, -80.1918), "index": 1.15},
            "orlando":      {"coords": (28.5383, -81.3792), "index": 1.02},
            "tampa":        {"coords": (27.9506, -82.4572), "index": 1.03},
            "jacksonville": {"coords": (30.3322, -81.6557), "index": 0.95},
            "tallahassee":  {"coords": (30.4383, -84.2807), "index": 0.93},
            "key west":     {"coords": (24.5551, -81.7800), "index": 1.25},
        }
        self.florida_center = (28.5383, -81.3792)

    def get_coordinates(self, city_name):
        city_name = city_name.lower().strip()
        if city_name in self.hubs:
            return self.hubs[city_name]["coords"]
        
        known_others = {
            "naples": (26.1420, -81.7948),
            "sarasota": (27.3364, -82.5307),
            "gainesville": (29.6516, -82.3248),
            "pensacola": (30.4213, -87.2169),
            "clearwater": (27.9659, -82.8001),
            "fort lauderdale": (26.1224, -80.1373)
        }
        return known_others.get(city_name, self.florida_center)

    def get_regional_multiplier(self, city=None, latitude=None, longitude=None):
        """
        Get regional price multiplier based on city name or GPS coordinates
        
        Args:
            city: City name (optional if lat/lon provided)
            latitude: Latitude coordinate (optional if city provided)
            longitude: Longitude coordinate (optional if city provided)
        """
        if latitude is not None and longitude is not None:
            # Use provided coordinates directly
            lat, lon = latitude, longitude
        else:
            # Get coordinates from city name
            coords = self.get_coordinates(city)
            lat, lon = coords
        
        total_weight = 0
        weighted_index = 0
        p = 2 
        
        for hub, data in self.hubs.items():
            h_lat, h_lon = data["coords"]
            dist = math.sqrt((lat - h_lat)**2 + (lon - h_lon)**2)
            if dist == 0: return data["index"]
            weight = 1 / (dist ** p)
            weighted_index += data["index"] * weight
            total_weight += weight
            
        return weighted_index / total_weight

# ==========================================
# PART 2: THE UI & LOGIC
# ==========================================

def main():
    print("="*60)
    print("   FLORIDA LIVE PRICING ENGINE (ROBUST)")
    print("   Data Source: Multi-Stage Web Scraping")
    print("="*60)
    
    scraper = RealTimeScraper()
    ref_model = ReferenceModel()
    
    try:
        while True:
            print("\nSelect Mode:")
            print("1. Consumer Mode (Check price of ANY item)")
            print("2. Vendor Mode (Set pricing strategy)")
            print("3. Exit")
            
            choice = input("\nChoice (1-3): ").strip()
            
            if choice == '3':
                print("Exiting...")
                break
                
            city = input("Enter City in Florida: ").strip()
            
            if choice == '1':
                product = input("What product do you want to check? (e.g. 'Milk', 'PS5'): ").strip()
                if not product: continue

                print(f"\n--- ⚡ FETCHING DATA FOR '{product.upper()}' ---")
                live_price = scraper.fetch_price_data(product, city)
                
                if live_price:
                    multiplier = ref_model.get_regional_multiplier(city)
                    print(f"\n✅ Result found for: {product.title()}")
                    print(f"💰 Market Average: ${live_price:.2f}")
                    
                    if multiplier > 1.05:
                        print(f"📍 Location Info: {city} is a HIGH cost area.")
                    elif multiplier < 0.98:
                        print(f"📍 Location Info: {city} is a LOW cost area.")
                else:
                    print(f"❌ Could not find reliable data. Try a broader term (e.g. 'Soda' instead of 'Coke').")

            elif choice == '2':
                item = input("What item are you selling?: ").strip()
                print(f"\n[System] Analysing market for '{item}'...")
                market_price = scraper.fetch_price_data(item, city)
                
                if market_price:
                    multiplier = ref_model.get_regional_multiplier(city)
                    print(f"\n--- MARKET ANALYSIS ---")
                    print(f"Competitor Avg: ${market_price:.2f}")
                    min_p = market_price * 0.95
                    max_p = market_price * 1.05
                    print(f"✅ Recommended Range: ${min_p:.2f} - ${max_p:.2f}")
                else:
                    print(f"(!) Data unavailable for '{item}'.")

    except KeyboardInterrupt:
        print("\nForce closing...")
    finally:
        scraper.close()

if __name__ == "__main__":
    main()