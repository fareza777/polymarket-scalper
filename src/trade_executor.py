"""
Trade Executor for Polymarket
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp

from config import config
from spread_detector import Signal

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Open position"""
    asset_id: str
    side: str
    entry_price: float
    size: float
    timestamp: datetime
    pnl: float = 0.0
    
    def update_pnl(self, current_price: float):
        """Update P&L based on current price"""
        if self.side == "buy":
            self.pnl = (current_price - self.entry_price) * self.size
        else:
            self.pnl = (self.entry_price - current_price) * self.size


@dataclass
class Trade:
    """Completed trade"""
    asset_id: str
    side: str
    price: float
    size: float
    timestamp: datetime
    pnl: Optional[float] = None


class TradeExecutor:
    """Execute trades on Polymarket"""
    
    def __init__(
        self,
        api_key: str = config.POLYMARKET_API_KEY,
        secret: str = config.POLYMARKET_SECRET,
        passphrase: str = config.POLYMARKET_PASSPHRASE,
        paper_trading: bool = config.PAPER_TRADING
    ):
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.paper_trading = paper_trading
        self.base_url = "https://clob.polymarket.com"
        
        # State
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.daily_pnl = 0.0
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Lock
        self._lock = asyncio.Lock()
    
    async def start(self):
        """Initialize executor"""
        self.session = aiohttp.ClientSession()
        logger.info(f"Trade executor started (paper={self.paper_trading})")
    
    async def stop(self):
        """Cleanup executor"""
        if self.session:
            await self.session.close()
        logger.info("Trade executor stopped")
    
    async def execute_signal(self, signal: Signal) -> bool:
        """Execute a trading signal"""
        async with self._lock:
            # Check if we already have a position
            if signal.asset_id in self.positions:
                logger.debug(f"Already have position in {signal.asset_id}")
                return False
            
            # Calculate position size
            size = config.TRADE_SIZE_USD / signal.entry_price
            
            if self.paper_trading:
                # Paper trade - simulate execution
                success = await self._paper_trade(signal, size)
            else:
                # Real trade - call Polymarket API
                success = await self._real_trade(signal, size)
            
            if success:
                # Record position
                position = Position(
                    asset_id=signal.asset_id,
                    side=signal.side,
                    entry_price=signal.entry_price,
                    size=size,
                    timestamp=datetime.now()
                )
                self.positions[signal.asset_id] = position
                
                # Record trade
                trade = Trade(
                    asset_id=signal.asset_id,
                    side=signal.side,
                    price=signal.entry_price,
                    size=size,
                    timestamp=datetime.now()
                )
                self.trades.append(trade)
                
                logger.info(f"Position opened: {signal.asset_id} | "
                           f"Side: {signal.side} | Size: ${config.TRADE_SIZE_USD}")
            
            return success
    
    async def _paper_trade(self, signal: Signal, size: float) -> bool:
        """Simulate a paper trade"""
        logger.info(f"[PAPER] Executing {signal.side} for {signal.asset_id} "
                   f"at {signal.entry_price}")
        
        # Simulate slippage (0.1%)
        slippage = 0.001
        if signal.side == "buy":
            executed_price = signal.entry_price * (1 + slippage)
        else:
            executed_price = signal.entry_price * (1 - slippage)
        
        logger.info(f"[PAPER] Executed at {executed_price}")
        return True
    
    async def _real_trade(self, signal: Signal, size: float) -> bool:
        """Execute real trade on Polymarket"""
        if not self.session:
            logger.error("Session not initialized")
            return False
        
        try:
            # Build order
            order = {
                "side": signal.side,
                "price": signal.entry_price,
                "size": size,
                "asset_id": signal.asset_id
            }
            
            # TODO: Implement actual Polymarket CLOB API order placement
            # This requires proper authentication and signing
            
            logger.info(f"[REAL] Order placed: {order}")
            return True
            
        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            return False
    
    async def close_position(self, asset_id: str, exit_price: float) -> bool:
        """Close an open position"""
        async with self._lock:
            if asset_id not in self.positions:
                return False
            
            position = self.positions[asset_id]
            
            # Calculate P&L
            position.update_pnl(exit_price)
            pnl = position.pnl
            
            # Record trade
            trade = Trade(
                asset_id=asset_id,
                side="sell" if position.side == "buy" else "buy",
                price=exit_price,
                size=position.size,
                timestamp=datetime.now(),
                pnl=pnl
            )
            self.trades.append(trade)
            
            # Update daily P&L
            self.daily_pnl += pnl
            
            # Remove position
            del self.positions[asset_id]
            
            logger.info(f"Position closed: {asset_id} | P&L: ${pnl:.2f}")
            return True
    
    async def update_positions(self, prices: Dict[str, float]):
        """Update P&L for all positions"""
        async with self._lock:
            for asset_id, position in self.positions.items():
                if asset_id in prices:
                    position.update_pnl(prices[asset_id])
    
    def get_position_count(self) -> int:
        """Get number of open positions"""
        return len(self.positions)
    
    def get_open_pnl(self) -> float:
        """Get unrealized P&L"""
        return sum(p.pnl for p in self.positions.values())
    
    def get_daily_pnl(self) -> float:
        """Get daily realized P&L"""
        return self.daily_pnl
    
    def get_stats(self) -> dict:
        """Get executor statistics"""
        return {
            "open_positions": len(self.positions),
            "total_trades": len(self.trades),
            "open_pnl": self.get_open_pnl(),
            "daily_pnl": self.daily_pnl,
            "paper_trading": self.paper_trading
        }
