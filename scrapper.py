import requests
from bs4 import BeautifulSoup
import re
import time
import random
import json

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("   [!] Selenium not available, using requests-only mode")

class RealTimeScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.session = requests.Session()
        # Randomize User-Agent to avoid immediate bot detection
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        self.session.headers.update({
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/"
        })
        self._init_selenium()

    def _init_selenium(self):
        """Initialize Selenium WebDriver for dynamic content scraping"""
        if not SELENIUM_AVAILABLE:
            return
            
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument(f'user-agent={random.choice(self.user_agents)}')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--log-level=3')  # Suppress INFO, WARNING, ERROR logs
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--silent')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # Try to use webdriver-manager if available, otherwise use system Chrome
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except:
                # Fallback to system Chrome
                self.driver = webdriver.Chrome(options=chrome_options)
            
            self.driver.set_page_load_timeout(30)
        except Exception as e:
            print(f"   [!] Warning: Selenium initialization failed: {e}")
            print(f"   [!] Falling back to requests-only mode")
            self.driver = None

    def _scrape_walmart(self, item_name, city):
        """Scrape Walmart.com for product prices"""
        prices = []
        
        # Try Selenium first
        if self.driver:
            try:
                search_url = f"https://www.walmart.com/search?q={item_name.replace(' ', '+')}"
                self.driver.get(search_url)
                time.sleep(3)
                
                # Extract prices
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                prices.extend(self._extract_prices_from_soup(soup))
            except Exception as e:
                pass
        
        # Fallback: Try requests-based scraping
        if not prices:
            try:
                search_url = f"https://www.walmart.com/search?q={item_name.replace(' ', '+')}"
                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Referer': 'https://www.google.com/'
                }
                response = self.session.get(search_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    prices.extend(self._extract_prices_from_soup(soup))
            except Exception as e:
                pass
        
        return prices
    
    def _extract_prices_from_soup(self, soup):
        """Helper method to extract prices from BeautifulSoup object"""
        prices = []
        
        # Multiple selectors for price elements
        price_selectors = [
            '[data-automation-id="product-price"]',
            '.price-current',
            '[itemprop="price"]',
            '[data-testid="price"]',
            '.price',
            '[class*="price"]',
            '[class*="Price"]',
            'span[class*="currency"]',
            '[data-price]'
        ]
        
        for selector in price_selectors:
            price_elements = soup.select(selector)
            for elem in price_elements[:15]:  # Limit to first 15 results
                text = elem.get_text()
                # Extract price using regex - matches $X.XX format
                price_matches = re.findall(r'\$?\s*(\d+\.?\d{0,2})', text.replace(',', ''))
                for price_str in price_matches:
                    try:
                        price = float(price_str)
                        if 0.50 < price < 200:  # Reasonable price range for groceries
                            prices.append(price)
                    except:
                        continue
        
        # Also try JSON-LD structured data
        json_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if 'offers' in data and isinstance(data['offers'], dict):
                        if 'price' in data['offers']:
                            price = float(data['offers']['price'])
                            if 0.50 < price < 200:
                                prices.append(price)
                    elif 'price' in data:
                        price = float(data['price'])
                        if 0.50 < price < 200:
                            prices.append(price)
            except:
                continue
        
        # Also search for price patterns in all text
        all_text = soup.get_text()
        price_pattern = re.compile(r'\$\s*(\d+\.\d{2})')
        matches = price_pattern.findall(all_text)
        for match in matches[:20]:  # Limit matches
            try:
                price = float(match)
                if 0.50 < price < 200:
                    prices.append(price)
            except:
                continue
        
        return prices

    def _scrape_target(self, item_name, city):
        """Scrape Target.com for product prices"""
        prices = []
        
        # Try Selenium first
        if self.driver:
            try:
                search_url = f"https://www.target.com/s?searchTerm={item_name.replace(' ', '+')}"
                self.driver.get(search_url)
                time.sleep(3)
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                prices.extend(self._extract_prices_from_soup(soup))
            except Exception as e:
                pass
        
        # Fallback: Try requests
        if not prices:
            try:
                search_url = f"https://www.target.com/s?searchTerm={item_name.replace(' ', '+')}"
                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
                response = self.session.get(search_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    prices.extend(self._extract_prices_from_soup(soup))
            except Exception as e:
                pass
        
        return prices

    def _scrape_publix_api(self, item_name):
        """Try to get Publix prices via their API or web interface"""
        prices = []
        
        # Publix website is often behind login, try Instacart Publix section instead
        if self.driver:
            try:
                # Try Instacart Publix
                search_url = f"https://www.instacart.com/store/publix/search_v3/{item_name.replace(' ', '%20')}"
                self.driver.get(search_url)
                time.sleep(3)
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                prices.extend(self._extract_prices_from_soup(soup))
            except Exception as e:
                pass
        
        # Also try direct Publix site
        if not prices:
            try:
                search_url = f"https://www.publix.com/shop/search?query={item_name.replace(' ', '+')}"
                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
                response = self.session.get(search_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    prices.extend(self._extract_prices_from_soup(soup))
            except Exception as e:
                pass
        
        return prices

    def _scrape_instacart(self, item_name, city):
        """Scrape Instacart for Publix/Walmart prices in Florida"""
        prices = []
        
        if self.driver:
            try:
                # Instacart search with location
                search_url = f"https://www.instacart.com/store/publix/search_v3/{item_name.replace(' ', '%20')}"
                self.driver.get(search_url)
                time.sleep(3)
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                prices.extend(self._extract_prices_from_soup(soup))
            except Exception as e:
                pass
        
        return prices

    def _scrape_google_shopping(self, item_name, city):
        """Fallback: Scrape Google Shopping for prices"""
        prices = []
        
        try:
            search_query = f"{item_name} price {city} Florida grocery store"
            search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=shop"
            
            if self.driver:
                self.driver.get(search_url)
                time.sleep(2)
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            else:
                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
                response = self.session.get(search_url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
            
            prices.extend(self._extract_prices_from_soup(soup))
        except Exception as e:
            pass
        
        return prices

    def _filter_prices_by_product_type(self, prices, item_name):
        """Filter prices based on product type to exclude bulk packs when searching for single items"""
        item_lower = item_name.lower()
        filtered_prices = []
        
        # Determine expected price range based on product type
        if any(x in item_lower for x in ['coke', 'coca cola', 'cola', 'soda', 'drink', 'beverage']):
            # For drinks: single can/bottle $0.50-$5, 2-liter $1-$4, 12-pack $5-$15
            # If user searches "coke" without "pack" or "case", prefer single-item prices
            if not any(x in item_lower for x in ['pack', 'case', '12', '24', 'family', 'bulk']):
                # Prefer prices in single-item range
                single_item_prices = [p for p in prices if 0.50 <= p <= 5.00]
                if single_item_prices:
                    filtered_prices = single_item_prices
                else:
                    # Fallback to all prices if no single items found
                    filtered_prices = prices
            else:
                filtered_prices = prices
        elif 'chip' in item_lower:
            # For chips: single bag $1-$6, family size $3-$8
            if 'family' in item_lower or 'large' in item_lower:
                filtered_prices = [p for p in prices if 2.50 <= p <= 10.00]
            else:
                # Regular bag
                filtered_prices = [p for p in prices if 1.00 <= p <= 7.00]
            if not filtered_prices:
                filtered_prices = prices
        elif 'chocolate' in item_lower:
            # For chocolate: single bar $0.50-$5, multi-pack $3-$15
            if not any(x in item_lower for x in ['pack', 'case', 'multi']):
                single_item_prices = [p for p in prices if 0.50 <= p <= 5.00]
                if single_item_prices:
                    filtered_prices = single_item_prices
                else:
                    filtered_prices = prices
            else:
                filtered_prices = prices
        else:
            # Default: use all prices
            filtered_prices = prices
        
        return filtered_prices if filtered_prices else prices

    def fetch_price_data(self, item_name, city):
        """Main method to fetch price data from multiple sources"""
        print(f"[Scraper] searching for '{item_name}' in {city}, FL...")
        
        all_prices = []
        
        # Normalize item name for better search results
        item_lower = item_name.lower()
        
        # Handle common product name variations - expand search terms intelligently
        search_terms = [item_name]
        
        # Add variations for drinks - coke/coca cola is a common issue
        if any(x in item_lower for x in ['coke', 'coca cola', 'cola']) and 'coca cola' not in item_lower:
            # If user searches "coke", try "coca cola" variations
            if not any(x in item_lower for x in ['pack', 'case', '12', '24']):
                search_terms.extend(['coca cola 20 oz', 'coca cola can', 'coca cola bottle'])
            search_terms.extend(['coca cola', 'coca cola 2 liter'])
        elif 'coca cola' in item_lower:
            search_terms.extend(['coca cola 2 liter', 'coca cola 20 oz', 'coca cola can', 'coke'])
        elif 'soda' in item_lower or 'pop' in item_lower:
            search_terms.append('soda 2 liter')
        
        # Add variations for chips
        if 'chip' in item_lower:
            if 'bag' not in item_lower and 'family' not in item_lower:
                search_terms.append(f'{item_name} bag')
            search_terms.append('potato chips')
        
        # Add variations for chocolate
        if 'chocolate' in item_lower:
            if 'bar' not in item_lower:
                search_terms.append(f'{item_name} bar')
            search_terms.append('chocolate bar')
        
        # Try each search term
        for search_term in search_terms[:3]:  # Try up to 3 variations
            print(f"   [→] Trying: '{search_term}'...")
            
            # Scrape from multiple sources in parallel (but sequentially to avoid rate limits)
            sources = [
                ("Walmart", lambda: self._scrape_walmart(search_term, city)),
                ("Target", lambda: self._scrape_target(search_term, city)),
                ("Instacart", lambda: self._scrape_instacart(search_term, city)),
                ("Publix", lambda: self._scrape_publix_api(search_term)),
            ]
            
            for source_name, scrape_func in sources:
                try:
                    prices = scrape_func()
                    if prices:
                        print(f"   [✓] Found {len(prices)} prices from {source_name}")
                        all_prices.extend(prices)
                        time.sleep(0.5)  # Be polite between requests
                except Exception as e:
                    continue
            
            # If we found enough prices, break early
            if len(all_prices) >= 5:
                break
        
        # Fallback to Google Shopping if no prices found
        if not all_prices:
            print(f"   [→] Trying Google Shopping as fallback...")
            all_prices = self._scrape_google_shopping(item_name, city)
        
        # Process and return average price
        if all_prices:
            # Filter prices based on product type (exclude bulk packs for single items)
            all_prices = self._filter_prices_by_product_type(all_prices, item_name)
            
            # Remove outliers (prices that are too far from median)
            all_prices.sort()
            if len(all_prices) > 4:
                # Remove top and bottom 20%
                trim = len(all_prices) // 5
                all_prices = all_prices[trim:-trim] if trim > 0 else all_prices
            
            # Calculate average
            avg_price = sum(all_prices) / len(all_prices)
            print(f"   [✓] Collected {len(all_prices)} valid prices")
            return round(avg_price, 2)
        
        return None

    def close(self):
        """Clean up resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.session.close()
