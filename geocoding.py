"""
Geocoding service for converting GPS coordinates to city names
Uses OpenStreetMap Nominatim API (free, no API key required)
"""
import requests
import time

class GeocodingService:
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org/reverse"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Florida-Pricing-Engine/1.0"  # Required by Nominatim
        })
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Rate limit: 1 request per second
    
    def _rate_limit(self):
        """Respect Nominatim's rate limit"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def reverse_geocode(self, latitude, longitude):
        """
        Convert GPS coordinates to city/state information
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            dict with city, state, county, and full address info
            Returns None if geocoding fails
        """
        try:
            self._rate_limit()
            
            params = {
                'lat': latitude,
                'lon': longitude,
                'format': 'json',
                'addressdetails': 1,
                'zoom': 10  # City-level detail
            }
            
            response = self.session.get(self.base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'address' in data:
                    address = data['address']
                    
                    # Extract city information (different regions use different fields)
                    city = (
                        address.get('city') or
                        address.get('town') or
                        address.get('village') or
                        address.get('municipality') or
                        address.get('county', '').replace(' County', '')
                    )
                    
                    state = address.get('state', '')
                    state_code = address.get('state_code', '')
                    county = address.get('county', '').replace(' County', '')
                    
                    # Check if in Florida
                    if state_code.upper() != 'FL' and 'florida' not in state.lower():
                        return {
                            'error': 'Location is not in Florida',
                            'state': state,
                            'state_code': state_code
                        }
                    
                    return {
                        'success': True,
                        'city': city,
                        'state': state,
                        'state_code': state_code,
                        'county': county,
                        'latitude': latitude,
                        'longitude': longitude,
                        'full_address': data.get('display_name', ''),
                        'raw': address
                    }
            
            return {'success': False, 'error': 'Geocoding failed'}
            
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': f'Network error: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': f'Geocoding error: {str(e)}'}
    
    def geocode_city(self, city_name, state='Florida'):
        """
        Convert city name to coordinates (forward geocoding)
        
        Args:
            city_name: Name of the city
            state: State name (default: Florida)
            
        Returns:
            dict with latitude, longitude, and address info
        """
        try:
            self._rate_limit()
            
            query = f"{city_name}, {state}, USA"
            params = {
                'q': query,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            }
            
            response = self.session.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                results = response.json()
                if results:
                    result = results[0]
                    return {
                        'success': True,
                        'latitude': float(result['lat']),
                        'longitude': float(result['lon']),
                        'display_name': result.get('display_name', ''),
                        'city': city_name
                    }
            
            return {'success': False, 'error': 'City not found'}
            
        except Exception as e:
            return {'success': False, 'error': f'Geocoding error: {str(e)}'}


