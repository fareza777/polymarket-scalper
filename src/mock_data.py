"""
Mock Data Generator for Polymarket Scalper Bot
Generates realistic market data for testing without API
"""
import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MockMarketData:
    """Generate realistic mock market data"""
    
    def __init__(self):
        # Crypto markets with realistic data
        self.markets = {
            "BTC-100K-DEC": {
                "condition_id": "0xbd31e1eb3baf757f0b3de99d9ad1234567890abcdef",
                "title": "Will Bitcoin exceed $100,000 by December 31, 2025?",
                "token_yes": "21742633143463906290569050155826241533067272736897614950488156847949938836455",
                "token_no": "48331043336612883890938759509493159234755048973500640148014422747788308965732",
                "base_price": 0.65,
                "volatility": 0.02
            },
            "ETH-5K-JAN": {
                "condition_id": "0xabc123def456789012345678901234567890abcd",
                "title": "Will Ethereum exceed $5,000 by January 31, 2026?",
                "token_yes": "31742633143463906290569050155826241533067272736897614950488156847949938836456",
                "token_no": "58331043336612883890938759509493159234755048973500640148014422747788308965733",
                "base_price": 0.45,
                "volatility": 0.025
            },
            "SOL-200-DEC": {
                "condition_id": "0xdef789abc0123456789012345678901234567890",
                "title": "Will Solana exceed $200 by December 31, 2025?",
                "token_yes": "41742633143463906290569050155826241533067272736897614950488156847949938836457",
                "token_no": "68331043336612883890938759509493159234755048973500640148014422747788308965734",
                "base_price": 0.35,
                "volatility": 0.03
            },
            "BTC-90K-NOV": {
                "condition_id": "0x1234567890abcdef1234567890abcdef12345678",
                "title": "Will Bitcoin exceed $90,000 by November 30, 2025?",
                "token_yes": "51742633143463906290569050155826241533067272736897614950488156847949938836458",
                "token_no": "78331043336612883890938759509493159234755048973500640148014422747788308965735",
                "base_price": 0.72,
                "volatility": 0.015
            },
            "ETH-4K-DEC": {
                "condition_id": "0xfedcba0987654321fedcba0987654321fedcba09",
                "title": "Will Ethereum exceed $4,000 by December 31, 2025?",
                "token_yes": "61742633143463906290569050155826241533067272736897614950488156847949938836459",
                "token_no": "88331043336612883890938759509493159234755048973500640148014422747788308965736",
                "base_price": 0.58,
                "volatility": 0.02
            }
        }
        
        # Current prices (will fluctuate)
        self.current_prices = {}
        self.orderbooks = {}
        
        # Initialize
        for market_id, market in self.markets.items():
            self.current_prices[market_id] = market["base_price"]
            self._generate_orderbook(market_id)
    
    def _generate_orderbook(self, market_id: str):
        """Generate realistic orderbook for a market"""
        market = self.markets[market_id]
        base_price = self.current_prices[market_id]
        
        # Generate spread (0.5% to 2.5%)
        spread_pct = random.uniform(0.005, 0.025)
        half_spread = spread_pct / 2
        
        best_bid = base_price * (1 - half_spread)
        best_ask = base_price * (1 + half_spread)
        
        # Generate orderbook levels
        bids = []
        asks = []
        
        # Bids (descending)
        for i in range(5):
            price = best_bid * (1 - i * 0.001)
            size = random.uniform(100, 1000)
            bids.append({"price": round(price, 4), "size": round(size, 2)})
        
        # Asks (ascending)
        for i in range(5):
            price = best_ask * (1 + i * 0.001)
            size = random.uniform(100, 1000)
            asks.append({"price": round(price, 4), "size": round(size, 2)})
        
        self.orderbooks[market_id] = {
            "bids": bids,
            "asks": asks,
            "timestamp": datetime.now().isoformat()
        }
    
    def update_prices(self):
        """Update all prices with random walk"""
        for market_id, market in self.markets.items():
            volatility = market["volatility"]
            change = random.uniform(-volatility, volatility)
            
            new_price = self.current_prices[market_id] * (1 + change)
            # Keep within 0.01 to 0.99
            new_price = max(0.01, min(0.99, new_price))
            
            self.current_prices[market_id] = new_price
            self._generate_orderbook(market_id)
    
    def get_markets(self) -> List[Dict]:
        """Get list of markets"""
        markets = []
        for market_id, market in self.markets.items():
            markets.append({
                "condition_id": market["condition_id"],
                "title": market["title"],
                "tokens": [
                    {"token_id": market["token_yes"]},
                    {"token_id": market["token_no"]}
                ]
            })
        return markets
    
    def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook for a token"""
        # Find which market this token belongs to
        for market_id, market in self.markets.items():
            if token_id in [market["token_yes"], market["token_no"]]:
                return self.orderbooks.get(market_id)
        return None
    
    def get_crypto_markets(self) -> List[Dict]:
        """Get crypto markets"""
        return self.get_markets()
    
    def extract_token_ids(self, market: Dict) -> List[str]:
        """Extract token IDs from market"""
        tokens = market.get("tokens", [])
        return [t.get("token_id") for t in tokens if t.get("token_id")]


class MockPolymarketAPI:
    """Mock API that simulates Polymarket API"""
    
    def __init__(self):
        self.mock_data = MockMarketData()
        self.running = False
        self.update_task = None
    
    async def start(self):
        """Start mock API with price updates"""
        self.running = True
        self.update_task = asyncio.create_task(self._update_loop())
        logger.info("Mock Polymarket API started")
    
    async def stop(self):
        """Stop mock API"""
        self.running = False
        if self.update_task:
            self.update_task.cancel()
        logger.info("Mock Polymarket API stopped")
    
    async def _update_loop(self):
        """Update prices every 2 seconds"""
        while self.running:
            try:
                self.mock_data.update_prices()
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Update error: {e}")
                await asyncio.sleep(5)
    
    async def get_markets(self, active: bool = True, limit: int = 100) -> List[Dict]:
        """Get markets"""
        await asyncio.sleep(0.1)  # Simulate network delay
        return self.mock_data.get_markets()
    
    async def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook"""
        await asyncio.sleep(0.05)  # Simulate network delay
        return self.mock_data.get_orderbook(token_id)
    
    async def get_crypto_markets(self) -> List[Dict]:
        """Get crypto markets"""
        await asyncio.sleep(0.1)
        return self.mock_data.get_crypto_markets()
    
    def extract_token_ids(self, market: Dict) -> List[str]:
        """Extract token IDs"""
        return self.mock_data.extract_token_ids(market)
