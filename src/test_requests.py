"""
Test connection using requests library
"""
import requests
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_requests():
    """Test with requests library"""
    url = "https://clob.polymarket.com/markets?active=true&limit=10"
    
    logger.info("Testing with requests library...")
    
    try:
        response = requests.get(url, timeout=30)
        logger.info(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            markets = data.get("markets", [])
            logger.info(f"SUCCESS! Found {len(markets)} markets")
            
            if markets:
                logger.info(f"First market: {markets[0].get('question', 'N/A')[:50]}...")
            return True
        else:
            logger.error(f"Failed: {response.status_code}")
            logger.error(f"Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("Timeout")
        return False
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    test_requests()
