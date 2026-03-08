"""
Polymarket API Client for Paper Trading
Fetches real market data without executing trades
"""
import asyncio
import logging
from typing import Dict, List, Optional
import aiohttp

logger = logging.getLogger(__name__)


class PolymarketAPI:
    """Client for Polymarket REST API"""
    
    def __init__(self):
        self.base_url = "https://clob.polymarket.com"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def start(self):
        """Initialize session"""
        self.session = aiohttp.ClientSession()
        logger.info("Polymarket API client started")
    
    async def stop(self):
        """Cleanup session"""
        if self.session:
            await self.session.close()
        logger.info("Polymarket API client stopped")
    
    async def get_markets(self, active: bool = True, limit: int = 100) -> List[Dict]:
        """Get list of markets"""
        if not self.session:
            return []
        
        # Try with retries
        for attempt in range(3):
            try:
                url = f"{self.base_url}/markets"
                params = {
                    "active": str(active).lower(),
                    "limit": limit
                }
                
                async with self.session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("markets", [])
                    else:
                        logger.error(f"Failed to get markets: {resp.status}")
                        return []
                        
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"All attempts failed: {e}")
                    return []
    
    async def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook for a token"""
        if not self.session:
            return None
        
        # Try with retries
        for attempt in range(3):
            try:
                url = f"{self.base_url}/orderbook/{token_id}"
                
                async with self.session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Failed to get orderbook: {resp.status}")
                        return None
                        
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {token_id[:20]}: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"All attempts failed: {e}")
                    return None
    
    async def get_market_info(self, condition_id: str) -> Optional[Dict]:
        """Get market info by condition ID"""
        if not self.session:
            return None
        
        try:
            url = f"{self.base_url}/markets/{condition_id}"
            
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Failed to get market info: {resp.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching market info: {e}")
            return None
    
    async def get_crypto_markets(self) -> List[Dict]:
        """Get crypto-related markets"""
        markets = await self.get_markets(active=True, limit=200)
        
        if not markets:
            logger.warning("No markets returned from API, using fallback")
            # Return some default markets for testing
            return self._get_fallback_markets()
        
        # Filter crypto markets
        crypto_keywords = [
            "bitcoin", "btc", "ethereum", "eth", "crypto", 
            "solana", "sol", "cardano", "ada", "binance", "bnb"
        ]
        
        crypto_markets = []
        for market in markets:
            title = market.get("title", "").lower()
            description = market.get("description", "").lower()
            
            if any(keyword in title or keyword in description 
                   for keyword in crypto_keywords):
                crypto_markets.append(market)
        
        # If no crypto markets found, return all active markets
        if not crypto_markets:
            logger.warning("No crypto markets found, using all active markets")
            return markets[:10]
        
        logger.info(f"Found {len(crypto_markets)} crypto markets")
        return crypto_markets
    
    def _get_fallback_markets(self) -> List[Dict]:
        """Fallback markets for testing"""
        return [
            {
                "condition_id": "0x1234567890abcdef",
                "title": "Bitcoin above $100k by end of 2025",
                "tokens": [
                    {"token_id": "21742633143463906290569050155826241533067272736897614950488156847949938836455"}
                ]
            }
        ]
    
    def extract_token_ids(self, market: Dict) -> List[str]:
        """Extract token IDs from market data"""
        tokens = market.get("tokens", [])
        return [t.get("token_id") for t in tokens if t.get("token_id")]
