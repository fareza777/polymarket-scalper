"""
Paper Trading Module - Simulates trades with real market data
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from spread_detector import Signal

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    """Paper trading position"""
    asset_id: str
    side: str
    entry_price: float
    size: float
    timestamp: datetime
    pnl: float = 0.0
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    status: str = "open"  # open, closed


class PaperTrader:
    """Execute paper trades with real market data"""
    
    def __init__(self, api):
        self.api = api
        self.positions: Dict[str, PaperPosition] = {}
        self.trade_history: List[PaperPosition] = []
        self.daily_pnl = 0.0
        self.total_volume = 0.0
        
        # Lock
        self._lock = asyncio.Lock()
    
    async def execute_signal(self, signal: Signal, trade_size: float = 5.0) -> bool:
        """Execute a paper trade based on signal"""
        async with self._lock:
            # Check if already have position
            if signal.asset_id in self.positions:
                logger.debug(f"Already have position in {signal.asset_id}")
                return False
            
            # Get current orderbook for realistic fill price
            orderbook = await self.api.get_orderbook(signal.asset_id)
            if not orderbook:
                logger.warning(f"No orderbook for {signal.asset_id}")
                return False
            
            # Calculate realistic fill price with slippage
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            
            if not bids or not asks:
                logger.warning(f"Empty orderbook for {signal.asset_id}")
                return False
            
            # Simulate fill at best available price with small slippage
            if signal.side == "buy":
                best_price = float(bids[0]["price"])
                slippage = 0.001  # 0.1% slippage
                fill_price = best_price * (1 + slippage)
            else:
                best_price = float(asks[0]["price"])
                slippage = 0.001
                fill_price = best_price * (1 - slippage)
            
            # Calculate position size
            size = trade_size / fill_price
            
            # Create position
            position = PaperPosition(
                asset_id=signal.asset_id,
                side=signal.side,
                entry_price=fill_price,
                size=size,
                timestamp=datetime.now()
            )
            
            self.positions[signal.asset_id] = position
            self.total_volume += trade_size
            
            logger.info(
                f"[PAPER TRADE] {signal.side.upper()} {signal.asset_id} | "
                f"Price: {fill_price:.4f} | Size: ${trade_size:.2f} | "
                f"Spread: {signal.spread_pct:.2f}%"
            )
            
            return True
    
    async def update_positions(self):
        """Update P&L for all open positions"""
        async with self._lock:
            for asset_id, position in list(self.positions.items()):
                # Get current price
                orderbook = await self.api.get_orderbook(asset_id)
                if not orderbook:
                    continue
                
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                
                if not bids or not asks:
                    continue
                
                # Calculate current price (mid)
                best_bid = float(bids[0]["price"])
                best_ask = float(asks[0]["price"])
                mid_price = (best_bid + best_ask) / 2
                
                # Update P&L
                if position.side == "buy":
                    position.pnl = (mid_price - position.entry_price) * position.size
                else:
                    position.pnl = (position.entry_price - mid_price) * position.size
    
    async def close_position(self, asset_id: str, reason: str = "signal") -> Optional[float]:
        """Close a position"""
        async with self._lock:
            if asset_id not in self.positions:
                return None
            
            position = self.positions[asset_id]
            
            # Get exit price
            orderbook = await self.api.get_orderbook(asset_id)
            if orderbook:
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                
                if bids and asks:
                    best_bid = float(bids[0]["price"])
                    best_ask = float(asks[0]["price"])
                    
                    if position.side == "buy":
                        # Sell at bid
                        exit_price = best_bid * 0.999  # Small slippage
                    else:
                        # Buy at ask
                        exit_price = best_ask * 1.001
                    
                    # Calculate final P&L
                    if position.side == "buy":
                        position.pnl = (exit_price - position.entry_price) * position.size
                    else:
                        position.pnl = (position.entry_price - exit_price) * position.size
                    
                    position.exit_price = exit_price
            
            position.exit_time = datetime.now()
            position.status = "closed"
            
            # Record in history
            self.trade_history.append(position)
            
            # Update daily P&L
            self.daily_pnl += position.pnl
            
            # Remove from open positions
            del self.positions[asset_id]
            
            logger.info(
                f"[PAPER CLOSE] {asset_id} | Reason: {reason} | "
                f"P&L: ${position.pnl:.2f} | Total Daily: ${self.daily_pnl:.2f}"
            )
            
            return position.pnl
    
    async def check_exit_conditions(self, max_hold_time_minutes: int = 30):
        """Check if positions should be closed"""
        async with self._lock:
            now = datetime.now()
            
            for asset_id, position in list(self.positions.items()):
                hold_time = (now - position.timestamp).total_seconds() / 60
                
                # Close if held too long
                if hold_time > max_hold_time_minutes:
                    await self.close_position(asset_id, "timeout")
                    continue
                
                # Close if profitable (take profit)
                if position.pnl > 0.50:  # $0.50 profit
                    await self.close_position(asset_id, "take_profit")
                    continue
                
                # Close if losing too much (stop loss)
                if position.pnl < -1.00:  # $1.00 loss
                    await self.close_position(asset_id, "stop_loss")
    
    def get_stats(self) -> Dict:
        """Get trading statistics"""
        open_pnl = sum(p.pnl for p in self.positions.values())
        
        # Calculate win rate
        closed_trades = [t for t in self.trade_history if t.status == "closed"]
        if closed_trades:
            wins = sum(1 for t in closed_trades if t.pnl > 0)
            win_rate = (wins / len(closed_trades)) * 100
            avg_pnl = sum(t.pnl for t in closed_trades) / len(closed_trades)
        else:
            win_rate = 0.0
            avg_pnl = 0.0
        
        return {
            "open_positions": len(self.positions),
            "total_trades": len(self.trade_history),
            "daily_pnl": self.daily_pnl,
            "open_pnl": open_pnl,
            "total_pnl": self.daily_pnl + open_pnl,
            "win_rate": win_rate,
            "avg_trade_pnl": avg_pnl,
            "total_volume": self.total_volume
        }
