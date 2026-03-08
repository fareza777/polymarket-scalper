"""
Polymarket API Client using requests (sync) with asyncio wrapper
"""
import asyncio
import logging
from typing import Dict, List, Optional
import requests
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class PolymarketRequestsAPI:
    """Live client using requests library"""
    
    def __init__(self):
        self.base_url = "https://clob.polymarket.com"
        self.session = requests.Session()
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    async def start(self):
        """Initialize"""
        logger.info("Polymarket Requests API client started")
    
    async def stop(self):
        """Cleanup"""
        self.session.close()
        self.executor.shutdown()
        logger.info("Polymarket Requests API client stopped")
    
    def _get_sync(self, url: str, params: dict = None) -> Optional[Dict]:
        """Synchronous GET request"""
        try:
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"HTTP {response.status_code}: {url}")
                return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
    
    async def get_markets(self, active: bool = True, limit: int = 100) -> List[Dict]:
        """Get list of markets"""
        url = f"{self.base_url}/markets"
        params = {"active": str(active).lower(), "limit": limit}
        
        # Run sync request in thread pool
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            self.executor, 
            self._get_sync, 
            url, 
            params
        )
        
        if data:
            # API returns 'data' key, not 'markets'
            markets = data.get("data", [])
            logger.info(f"Fetched {len(markets)} markets from Polymarket")
            return markets
        
        return []
    
    async def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook for a token"""
        url = f"{self.base_url}/orderbook/{token_id}"
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._get_sync, url, None)
    
    async def get_crypto_markets(self) -> List[Dict]:
        """Get crypto-related markets"""
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
        
        if not crypto_markets:
            logger.warning("No crypto markets found, using first 10 active markets")
            return markets[:10]
        
        logger.info(f"Found {len(crypto_markets)} crypto-related markets")
        return crypto_markets[:15]
    
    def extract_token_ids(self, market: Dict) -> List[str]:
        """Extract token IDs from market data"""
        tokens = market.get("tokens", [])
        return [t.get("token_id") for t in tokens if t.get("token_id")]
    
    def get_market_display_name(self, market: Dict) -> str:
        """Get display name for market"""
        question = market.get("question", "Unknown Market")
        if len(question) > 60:
            question = question[:57] + "..."
        return question
