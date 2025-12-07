from flask import Flask, request, jsonify
from flask_cors import CORS
from scrapper import RealTimeScraper
from region_model import ReferenceModel
from geocoding import GeocodingService
import threading

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize models (thread-safe)
ref_model = ReferenceModel()
geocoding = GeocodingService()

# Thread-local storage for scraper instances
thread_local = threading.local()

def get_scraper():
    """Get or create a scraper instance for the current thread"""
    if not hasattr(thread_local, 'scraper'):
        thread_local.scraper = RealTimeScraper(headless=True)
    return thread_local.scraper

@app.route('/')
def home():
    """API home endpoint"""
    return jsonify({
        "name": "Florida Regional Pricing API",
        "version": "1.0.0",
        "description": "Real-time price checking and vendor pricing recommendations for Florida",
        "endpoints": {
            "/api/health": "Health check",
            "/api/price/check": "Check price for a product (Consumer Mode)",
            "/api/price/vendor": "Get pricing recommendations (Vendor Mode)",
            "/api/cities": "List supported Florida cities"
        }
    })

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Florida Pricing Engine"
    })

@app.route('/api/price/check', methods=['POST', 'GET'])
def check_price():
    """
    Consumer Mode: Check price of a product in a Florida city
    
    POST/GET Parameters (use either city OR lat/lon):
    - product (required): Product name (e.g., "Coca Cola", "Lays Chips")
    - city (optional): City name in Florida (e.g., "Miami", "Clearwater")
    - latitude (optional): GPS latitude coordinate
    - longitude (optional): GPS longitude coordinate
    
    Returns:
    - price: Average market price
    - city: City name (from GPS if provided)
    - product: Product name
    - location_type: HIGH/MEDIUM/LOW cost area
    - multiplier: Regional price multiplier
    - coordinates: GPS coordinates if provided
    """
    try:
        # Support both GET and POST
        if request.method == 'POST':
            data = request.get_json() or {}
            product = data.get('product') or request.form.get('product')
            city = data.get('city') or request.form.get('city')
            latitude = data.get('latitude') or data.get('lat') or request.form.get('latitude') or request.form.get('lat')
            longitude = data.get('longitude') or data.get('lon') or request.form.get('longitude') or request.form.get('lon')
        else:
            product = request.args.get('product')
            city = request.args.get('city')
            latitude = request.args.get('latitude') or request.args.get('lat')
            longitude = request.args.get('longitude') or request.args.get('lon')
        
        # Validate inputs
        if not product:
            return jsonify({
                "error": "Missing required parameter: 'product'",
                "example": "/api/price/check?product=coca%20cola&city=miami"
            }), 400
        
        # Handle GPS coordinates
        lat = None
        lon = None
        if latitude and longitude:
            try:
                lat = float(latitude)
                lon = float(longitude)
                # Validate coordinate ranges (Florida is roughly 24-31°N, 80-87°W)
                if not (24 <= lat <= 31) or not (-87 <= lon <= -80):
                    return jsonify({
                        "error": "Coordinates are outside Florida bounds",
                        "note": "Florida coordinates: 24-31°N, 80-87°W"
                    }), 400
                
                # Reverse geocode to get city name
                geo_result = geocoding.reverse_geocode(lat, lon)
                if not geo_result.get('success'):
                    return jsonify({
                        "error": "Failed to geocode coordinates",
                        "details": geo_result.get('error', 'Unknown error')
                    }), 400
                
                city = geo_result.get('city')
                if not city:
                    return jsonify({
                        "error": "Could not determine city from coordinates",
                        "details": geo_result
                    }), 400
                    
            except ValueError:
                return jsonify({
                    "error": "Invalid coordinate format. Use decimal numbers."
                }), 400
        
        # Validate city is provided (either directly or from GPS)
        if not city:
            return jsonify({
                "error": "Missing location: provide either 'city' or 'latitude'/'longitude'",
                "example_city": "/api/price/check?product=coca%20cola&city=miami",
                "example_gps": "/api/price/check?product=coca%20cola&latitude=25.7617&longitude=-80.1918"
            }), 400
        
        # Get scraper instance
        scraper = get_scraper()
        
        # Fetch price data
        live_price = scraper.fetch_price_data(product, city)
        
        if live_price is None:
            return jsonify({
                "success": False,
                "error": "Could not find reliable price data",
                "suggestion": "Try a broader product name (e.g., 'Soda' instead of 'Coke')",
                "product": product,
                "city": city
            }), 404
        
        # Get regional multiplier (use GPS if available, otherwise city name)
        if lat is not None and lon is not None:
            multiplier = ref_model.get_regional_multiplier(latitude=lat, longitude=lon)
        else:
            multiplier = ref_model.get_regional_multiplier(city=city)
        
        # Determine location type
        if multiplier > 1.05:
            location_type = "HIGH"
        elif multiplier < 0.98:
            location_type = "LOW"
        else:
            location_type = "MEDIUM"
        
        response = {
            "success": True,
            "product": product,
            "city": city,
            "price": round(live_price, 2),
            "currency": "USD",
            "location_type": location_type,
            "multiplier": round(multiplier, 3),
            "state": "Florida"
        }
        
        # Include coordinates if GPS was used
        if lat is not None and lon is not None:
            response["coordinates"] = {
                "latitude": lat,
                "longitude": lon
            }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/price/vendor', methods=['POST', 'GET'])
def vendor_pricing():
    """
    Vendor Mode: Get pricing recommendations for a product
    
    POST/GET Parameters (use either city OR lat/lon):
    - item (required): Item name you're selling
    - city (optional): City name in Florida
    - latitude (optional): GPS latitude coordinate
    - longitude (optional): GPS longitude coordinate
    
    Returns:
    - competitor_avg: Average competitor price
    - recommended_min: Minimum recommended price
    - recommended_max: Maximum recommended price
    - location_type: HIGH/MEDIUM/LOW cost area
    - coordinates: GPS coordinates if provided
    """
    try:
        # Support both GET and POST
        if request.method == 'POST':
            data = request.get_json() or {}
            item = data.get('item') or request.form.get('item')
            city = data.get('city') or request.form.get('city')
            latitude = data.get('latitude') or data.get('lat') or request.form.get('latitude') or request.form.get('lat')
            longitude = data.get('longitude') or data.get('lon') or request.form.get('longitude') or request.form.get('lon')
        else:
            item = request.args.get('item')
            city = request.args.get('city')
            latitude = request.args.get('latitude') or request.args.get('lat')
            longitude = request.args.get('longitude') or request.args.get('lon')
        
        # Validate inputs
        if not item:
            return jsonify({
                "error": "Missing required parameter: 'item'",
                "example": "/api/price/vendor?item=coca%20cola&city=miami"
            }), 400
        
        # Handle GPS coordinates
        lat = None
        lon = None
        if latitude and longitude:
            try:
                lat = float(latitude)
                lon = float(longitude)
                # Validate coordinate ranges (Florida is roughly 24-31°N, 80-87°W)
                if not (24 <= lat <= 31) or not (-87 <= lon <= -80):
                    return jsonify({
                        "error": "Coordinates are outside Florida bounds",
                        "note": "Florida coordinates: 24-31°N, 80-87°W"
                    }), 400
                
                # Reverse geocode to get city name
                geo_result = geocoding.reverse_geocode(lat, lon)
                if not geo_result.get('success'):
                    return jsonify({
                        "error": "Failed to geocode coordinates",
                        "details": geo_result.get('error', 'Unknown error')
                    }), 400
                
                city = geo_result.get('city')
                if not city:
                    return jsonify({
                        "error": "Could not determine city from coordinates",
                        "details": geo_result
                    }), 400
                    
            except ValueError:
                return jsonify({
                    "error": "Invalid coordinate format. Use decimal numbers."
                }), 400
        
        # Validate city is provided (either directly or from GPS)
        if not city:
            return jsonify({
                "error": "Missing location: provide either 'city' or 'latitude'/'longitude'",
                "example_city": "/api/price/vendor?item=coca%20cola&city=miami",
                "example_gps": "/api/price/vendor?item=coca%20cola&latitude=25.7617&longitude=-80.1918"
            }), 400
        
        # Get scraper instance
        scraper = get_scraper()
        
        # Fetch market price
        market_price = scraper.fetch_price_data(item, city)
        
        if market_price is None:
            return jsonify({
                "success": False,
                "error": "Data unavailable for this item",
                "item": item,
                "city": city
            }), 404
        
        # Get regional multiplier (use GPS if available, otherwise city name)
        if lat is not None and lon is not None:
            multiplier = ref_model.get_regional_multiplier(latitude=lat, longitude=lon)
        else:
            multiplier = ref_model.get_regional_multiplier(city=city)
        
        # Calculate recommended pricing range (±5%)
        min_price = market_price * 0.95
        max_price = market_price * 1.05
        
        # Determine location type
        if multiplier > 1.05:
            location_type = "HIGH"
        elif multiplier < 0.98:
            location_type = "LOW"
        else:
            location_type = "MEDIUM"
        
        response = {
            "success": True,
            "item": item,
            "city": city,
            "competitor_avg": round(market_price, 2),
            "recommended_min": round(min_price, 2),
            "recommended_max": round(max_price, 2),
            "location_type": location_type,
            "multiplier": round(multiplier, 3),
            "state": "Florida"
        }
        
        # Include coordinates if GPS was used
        if lat is not None and lon is not None:
            response["coordinates"] = {
                "latitude": lat,
                "longitude": lon
            }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/cities', methods=['GET'])
def list_cities():
    """List supported Florida cities"""
    cities = {
        "major_hubs": ["miami", "orlando", "tampa", "jacksonville", "tallahassee", "key west"],
        "other_cities": [
            "naples", "sarasota", "gainesville", "pensacola", 
            "clearwater", "fort lauderdale", "daytona beach"
        ],
        "note": "Any Florida city can be used, but major hubs have more accurate pricing data"
    }
    return jsonify(cities)

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "/api/health",
            "/api/price/check",
            "/api/price/vendor",
            "/api/cities"
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal server error",
        "message": str(error) if app.debug else "An error occurred"
    }), 500

if __name__ == '__main__':
    print("="*60)
    print("   FLORIDA PRICING API SERVER")
    print("="*60)
    print("\nStarting API server on http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  GET  /api/health          - Health check")
    print("  GET  /api/cities           - List supported cities")
    print("  GET  /api/price/check      - Check product price")
    print("  POST /api/price/check      - Check product price")
    print("  GET  /api/price/vendor     - Get vendor pricing")
    print("  POST /api/price/vendor     - Get vendor pricing")
    print("\nExample requests:")
    print("  curl 'http://localhost:5000/api/price/check?product=coca%20cola&city=miami'")
    print("  curl -X POST http://localhost:5000/api/price/vendor -H 'Content-Type: application/json' -d '{\"item\":\"chips\",\"city\":\"tampa\"}'")
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

