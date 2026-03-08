"""
Polymarket Gamma API Client
Uses Gamma API for market discovery + CLOB for orderbook
"""
import asyncio
import logging
from typing import Dict, List, Optional
import requests
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class PolymarketGammaAPI:
    """Client using Gamma API for markets + CLOB for orderbook"""
    
    def __init__(self):
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.clob_url = "https://clob.polymarket.com"
        self.session = requests.Session()
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    async def start(self):
        """Initialize"""
        logger.info("Polymarket Gamma API client started")
    
    async def stop(self):
        """Cleanup"""
        self.session.close()
        self.executor.shutdown()
        logger.info("Polymarket Gamma API client stopped")
    
    def _get_sync(self, url: str, params: dict = None) -> Optional[Dict]:
        """Synchronous GET request"""
        try:
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.debug(f"HTTP {response.status_code}: {url}")
                return None
        except Exception as e:
            logger.debug(f"Request error: {e}")
            return None
    
    async def get_events(self, active: bool = True, limit: int = 50) -> List[Dict]:
        """Get events from Gamma API"""
        url = f"{self.gamma_url}/events"
        params = {"active": str(active).lower(), "limit": limit}
        
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(self.executor, self._get_sync, url, params)
        
        if isinstance(data, list):
            return data
        return []
    
    async def get_markets_from_event(self, event_id: str) -> List[Dict]:
        """Get markets for a specific event"""
        url = f"{self.gamma_url}/events/{event_id}"
        
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(self.executor, self._get_sync, url, None)
        
        if data and isinstance(data, dict):
            return data.get("markets", [])
        return []
    
    async def get_all_markets(self, limit: int = 100) -> List[Dict]:
        """Get all active markets directly from Gamma API"""
        url = f"{self.gamma_url}/markets"
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false"
        }
        
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(self.executor, self._get_sync, url, params)
        
        if isinstance(data, list):
            logger.info(f"Found {len(data)} active markets from Gamma API")
            return data
        
        logger.warning("No active markets found")
        return []
    
    async def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook from CLOB API"""
        url = f"{self.clob_url}/orderbook/{token_id}"
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._get_sync, url, None)
    
    def extract_token_ids(self, market: Dict) -> List[str]:
        """Extract token IDs from market data"""
        # Gamma API markets use conditionId for CLOB
        condition_id = market.get("conditionId") or market.get("condition_id")
        if condition_id:
            return [condition_id]
        
        # Fallback: try outcomes if it's a list
        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, list):
            token_ids = []
            for outcome in outcomes:
                if isinstance(outcome, dict):
                    token_id = outcome.get("token_id") or outcome.get("tokenId") or outcome.get("id")
                    if token_id:
                        token_ids.append(token_id)
            return token_ids
        
        return []
    
    def get_market_display_name(self, market: Dict) -> str:
        """Get display name for market"""
        question = market.get("question", "Unknown Market")
        if len(question) > 60:
            question = question[:57] + "..."
        return question
