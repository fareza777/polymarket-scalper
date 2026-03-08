"""
Test connection to Polymarket API
"""
import asyncio
import aiohttp
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_connection():
    """Test basic connection to Polymarket"""
    url = "https://clob.polymarket.com/markets?active=true&limit=10"
    
    logger.info("Testing connection to Polymarket...")
    logger.info(f"URL: {url}")
    
    try:
        # Test with different timeout settings
        timeout = aiohttp.ClientTimeout(total=60, connect=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            logger.info("Session created, sending request...")
            
            async with session.get(url) as resp:
                logger.info(f"Response status: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    markets = data.get("markets", [])
                    logger.info(f"SUCCESS! Found {len(markets)} markets")
                    
                    if markets:
                        logger.info(f"First market: {markets[0].get('question', 'N/A')}")
                    return True
                else:
                    logger.error(f"Failed with status: {resp.status}")
                    return False
                    
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Connection error: {e}")
        return False
    except asyncio.TimeoutError:
        logger.error("Timeout error")
        return False
    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e}")
        return False


async def test_with_proxy():
    """Test with system proxy settings"""
    url = "https://clob.polymarket.com/markets?active=true&limit=10"
    
    logger.info("\nTesting with trust_env=True (system proxy)...")
    
    try:
        timeout = aiohttp.ClientTimeout(total=60, connect=30)
        
        # trust_env=True will use system proxy settings
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    markets = data.get("markets", [])
                    logger.info(f"SUCCESS with proxy! Found {len(markets)} markets")
                    return True
                else:
                    logger.error(f"Failed: {resp.status}")
                    return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_connection())
    
    if not result:
        # Try with proxy
        result2 = asyncio.run(test_with_proxy())
