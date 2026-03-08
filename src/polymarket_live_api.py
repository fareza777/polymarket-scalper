"""
Polymarket Live API Client
Real connection to Polymarket CLOB API
"""
import asyncio
import logging
from typing import Dict, List, Optional
import aiohttp

logger = logging.getLogger(__name__)


class PolymarketLiveAPI:
    """Live client for Polymarket REST API"""
    
    def __init__(self):
        self.base_url = "https://clob.polymarket.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self.markets_cache = []
        self.last_market_fetch = None
    
    async def start(self):
        """Initialize session"""
        # Create session with longer timeout
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("Polymarket Live API client started")
    
    async def stop(self):
        """Cleanup session"""
        if self.session:
            await self.session.close()
        logger.info("Polymarket Live API client stopped")
    
    async def _get_with_retry(self, url: str, params: dict = None, max_retries: int = 3) -> Optional[Dict]:
        """Make GET request with retry logic"""
        if not self.session:
            return None
        
        for attempt in range(max_retries):
            try:
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:  # Rate limited
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"HTTP {resp.status}: {url}")
                        return None
                        
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"Connection error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Request error: {e}")
                return None
        
        return None
    
    async def get_markets(self, active: bool = True, limit: int = 100) -> List[Dict]:
        """Get list of markets from Polymarket"""
        url = f"{self.base_url}/markets"
        params = {
            "active": str(active).lower(),
            "limit": limit
        }
        
        data = await self._get_with_retry(url, params)
        if data:
            markets = data.get("markets", [])
            logger.info(f"Fetched {len(markets)} markets from Polymarket")
            return markets
        
        logger.error("Failed to fetch markets")
        return []
    
    async def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook for a token"""
        url = f"{self.base_url}/orderbook/{token_id}"
        
        data = await self._get_with_retry(url)
        if data:
            return data
        
        logger.debug(f"Failed to fetch orderbook for {token_id[:20]}...")
        return None
    
    async def get_market_info(self, condition_id: str) -> Optional[Dict]:
        """Get market info by condition ID"""
        url = f"{self.base_url}/markets/{condition_id}"
        
        return await self._get_with_retry(url)
    
    async def get_crypto_markets(self) -> List[Dict]:
        """Get crypto-related markets"""
        # Fetch all active markets
        markets = await self.get_markets(active=True, limit=200)
        
        if not markets:
            logger.error("No markets returned from Polymarket API")
            return []
        
        # Filter crypto markets
        crypto_keywords = [
            "bitcoin", "btc", "ethereum", "eth", "crypto",
            "solana", "sol", "cardano", "ada", "binance", "bnb",
            "price", "above", "below", "reach", "exceed"
        ]
        
        crypto_markets = []
        for market in markets:
            title = market.get("question", "").lower()
            description = market.get("description", "").lower()
            
            if any(keyword in title or keyword in description 
                   for keyword in crypto_keywords):
                crypto_markets.append(market)
        
        # If no crypto markets found, return first 10 active markets
        if not crypto_markets:
            logger.warning("No crypto markets found, using first 10 active markets")
            return markets[:10]
        
        logger.info(f"Found {len(crypto_markets)} crypto-related markets")
        return crypto_markets[:15]  # Limit to 15 markets
    
    def extract_token_ids(self, market: Dict) -> List[str]:
        """Extract token IDs from market data"""
        tokens = market.get("tokens", [])
        return [t.get("token_id") for t in tokens if t.get("token_id")]
    
    def get_market_display_name(self, market: Dict) -> str:
        """Get display name for market"""
        question = market.get("question", "Unknown Market")
        # Truncate if too long
        if len(question) > 60:
            question = question[:57] + "..."
        return question
