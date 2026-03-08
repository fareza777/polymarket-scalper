"""
Spread Detector for Scalping Opportunities
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from orderbook import OrderbookAggregator, MarketData
from config import config

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Trading signal"""
    asset_id: str
    side: str  # "buy" or "sell"
    entry_price: float
    target_price: float
    spread_pct: float
    liquidity: float
    confidence: float
    timestamp: datetime
    
    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "side": self.side,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "spread_pct": self.spread_pct,
            "liquidity": self.liquidity,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat()
        }


class SpreadDetector:
    """Detect scalping opportunities based on spread"""
    
    def __init__(
        self,
        orderbook: OrderbookAggregator,
        on_signal: Optional[Callable] = None,
        min_spread_pct: float = config.MIN_SPREAD_PCT,
        min_liquidity: float = config.MIN_LIQUIDITY,
        cooldown_seconds: int = config.TRADE_COOLDOWN_SECONDS
    ):
        self.orderbook = orderbook
        self.on_signal = on_signal
        self.min_spread_pct = min_spread_pct
        self.min_liquidity = min_liquidity
        self.cooldown = timedelta(seconds=cooldown_seconds)
        
        # Track last trade time per asset
        self.last_trade_time: Dict[str, datetime] = {}
        self._running = False
        self._task = None
    
    async def start(self):
        """Start detection loop"""
        self._running = True
        self._task = asyncio.create_task(self._detection_loop())
        logger.info("Spread detector started")
    
    async def stop(self):
        """Stop detection loop"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Spread detector stopped")
    
    async def _detection_loop(self):
        """Main detection loop"""
        while self._running:
            try:
                await self._scan_opportunities()
                await asyncio.sleep(1)  # Scan every second
            except Exception as e:
                logger.error(f"Detection error: {e}")
                await asyncio.sleep(5)
    
    async def _scan_opportunities(self):
        """Scan all markets for opportunities"""
        markets = await self.orderbook.get_all_markets()
        
        for asset_id, market in markets.items():
            signal = await self._analyze_market(asset_id, market)
            if signal and self.on_signal:
                await self.on_signal(signal)
    
    async def _analyze_market(self, asset_id: str, market: MarketData) -> Optional[Signal]:
        """Analyze a single market for opportunity"""
        # Check cooldown
        if asset_id in self.last_trade_time:
            if datetime.now() - self.last_trade_time[asset_id] < self.cooldown:
                return None
        
        # Get spread
        spread_pct = market.spread_pct()
        if not spread_pct or spread_pct < self.min_spread_pct:
            return None
        
        # Check liquidity
        liquidity = await self.orderbook.get_liquidity(asset_id)
        if liquidity < self.min_liquidity:
            return None
        
        # Get best prices
        best_bid = market.best_bid()
        best_ask = market.best_ask()
        mid_price = market.mid_price()
        
        if not best_bid or not best_ask or not mid_price:
            return None
        
        # Calculate confidence based on spread and liquidity
        # Higher spread = higher confidence, higher liquidity = higher confidence
        spread_score = min(spread_pct / 5.0, 1.0)  # Max at 5% spread
        liquidity_score = min(liquidity / 10000.0, 1.0)  # Max at $10k liquidity
        confidence = (spread_score * 0.6 + liquidity_score * 0.4)
        
        # Determine side (buy at bid, sell at ask)
        # For scalping, we want to buy low and sell high quickly
        side = "buy"
        entry_price = best_bid[0]
        target_price = best_ask[0]
        
        # Create signal
        signal = Signal(
            asset_id=asset_id,
            side=side,
            entry_price=entry_price,
            target_price=target_price,
            spread_pct=spread_pct,
            liquidity=liquidity,
            confidence=confidence,
            timestamp=datetime.now()
        )
        
        logger.info(f"Signal detected: {asset_id} | Spread: {spread_pct:.2f}% | "
                   f"Confidence: {confidence:.2f}")
        
        return signal
    
    def record_trade(self, asset_id: str):
        """Record trade time for cooldown"""
        self.last_trade_time[asset_id] = datetime.now()
    
    def get_stats(self) -> dict:
        """Get detector statistics"""
        return {
            "min_spread_pct": self.min_spread_pct,
            "min_liquidity": self.min_liquidity,
            "cooldown_seconds": self.cooldown.total_seconds(),
            "recent_trades": len(self.last_trade_time)
        }
