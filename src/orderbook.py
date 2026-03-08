"""
Orderbook Aggregator for Polymarket
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """Market data for a single asset"""
    asset_id: str
    bids: List[Tuple[float, float]] = field(default_factory=list)  # (price, size)
    asks: List[Tuple[float, float]] = field(default_factory=list)  # (price, size)
    last_trade_price: Optional[float] = None
    last_update: Optional[datetime] = None
    
    def best_bid(self) -> Optional[Tuple[float, float]]:
        """Get best bid (highest price)"""
        return self.bids[0] if self.bids else None
    
    def best_ask(self) -> Optional[Tuple[float, float]]:
        """Get best ask (lowest price)"""
        return self.asks[0] if self.asks else None
    
    def spread(self) -> Optional[float]:
        """Get absolute spread"""
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid and best_ask:
            return best_ask[0] - best_bid[0]
        return None
    
    def spread_pct(self) -> Optional[float]:
        """Get spread percentage"""
        spread = self.spread()
        best_bid = self.best_bid()
        if spread and best_bid:
            return (spread / best_bid[0]) * 100
        return None
    
    def mid_price(self) -> Optional[float]:
        """Get mid price"""
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid and best_ask:
            return (best_bid[0] + best_ask[0]) / 2
        return None


class OrderbookAggregator:
    """Aggregate orderbook data from WebSocket"""
    
    def __init__(self):
        self.markets: Dict[str, MarketData] = {}
        self._lock = asyncio.Lock()
    
    async def update_book(self, asset_id: str, bids: List[list], asks: List[list]):
        """Update orderbook for an asset"""
        async with self._lock:
            if asset_id not in self.markets:
                self.markets[asset_id] = MarketData(asset_id=asset_id)
            
            market = self.markets[asset_id]
            # Sort bids descending, asks ascending
            market.bids = sorted([(float(p), float(s)) for p, s in bids], 
                                key=lambda x: x[0], reverse=True)
            market.asks = sorted([(float(p), float(s)) for p, s in asks], 
                                key=lambda x: x[0])
            market.last_update = datetime.now()
    
    async def update_last_trade(self, asset_id: str, price: float):
        """Update last trade price"""
        async with self._lock:
            if asset_id not in self.markets:
                self.markets[asset_id] = MarketData(asset_id=asset_id)
            
            self.markets[asset_id].last_trade_price = float(price)
            self.markets[asset_id].last_update = datetime.now()
    
    async def get_market(self, asset_id: str) -> Optional[MarketData]:
        """Get market data for an asset"""
        async with self._lock:
            return self.markets.get(asset_id)
    
    async def get_all_markets(self) -> Dict[str, MarketData]:
        """Get all market data"""
        async with self._lock:
            return dict(self.markets)
    
    async def get_best_bid_ask(self, asset_id: str) -> Optional[Tuple]:
        """Get best bid and ask for an asset"""
        async with self._lock:
            market = self.markets.get(asset_id)
            if market:
                return market.best_bid(), market.best_ask()
            return None
    
    async def get_spread(self, asset_id: str) -> Optional[float]:
        """Get spread for an asset"""
        async with self._lock:
            market = self.markets.get(asset_id)
            if market:
                return market.spread()
            return None
    
    async def get_spread_pct(self, asset_id: str) -> Optional[float]:
        """Get spread percentage for an asset"""
        async with self._lock:
            market = self.markets.get(asset_id)
            if market:
                return market.spread_pct()
            return None
    
    async def get_liquidity(self, asset_id: str) -> float:
        """Get total liquidity (bid + ask volume)"""
        async with self._lock:
            market = self.markets.get(asset_id)
            if not market:
                return 0.0
            
            bid_liquidity = sum(size for _, size in market.bids)
            ask_liquidity = sum(size for _, size in market.asks)
            return bid_liquidity + ask_liquidity
    
    def get_stats(self) -> dict:
        """Get aggregator statistics"""
        return {
            "markets_tracked": len(self.markets),
            "last_updates": {
                aid: m.last_update.isoformat() if m.last_update else None
                for aid, m in self.markets.items()
            }
        }
