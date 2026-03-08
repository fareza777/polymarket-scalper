"""
Risk Manager for Polymarket Scalper
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from config import config
from trade_executor import TradeExecutor
from spread_detector import Signal

logger = logging.getLogger(__name__)


class RiskManager:
    """Manage trading risk"""
    
    def __init__(
        self,
        executor: TradeExecutor,
        max_positions: int = config.MAX_POSITIONS,
        max_loss_per_position: float = config.MAX_LOSS_PER_POSITION,
        daily_loss_limit: float = config.DAILY_LOSS_LIMIT
    ):
        self.executor = executor
        self.max_positions = max_positions
        self.max_loss_per_position = max_loss_per_position
        self.daily_loss_limit = daily_loss_limit
        
        # State
        self.emergency_stop = False
        self.daily_loss = 0.0
        self.last_reset = datetime.now()
        self.position_entry_prices: Dict[str, float] = {}
        
        # Lock
        self._lock = asyncio.Lock()
    
    async def can_trade(self) -> bool:
        """Check if trading is allowed"""
        async with self._lock:
            # Check emergency stop
            if self.emergency_stop:
                logger.warning("Trading halted: Emergency stop")
                return False
            
            # Reset daily loss if new day
            await self._check_daily_reset()
            
            # Check daily loss limit
            if self.daily_loss >= self.daily_loss_limit:
                logger.warning(f"Trading halted: Daily loss limit reached (${self.daily_loss:.2f})")
                return False
            
            # Check max positions
            if self.executor.get_position_count() >= self.max_positions:
                logger.debug("Max positions reached")
                return False
            
            return True
    
    async def check_signal(self, signal: Signal) -> bool:
        """Check if signal passes risk checks"""
        async with self._lock:
            if not await self.can_trade():
                return False
            
            # Additional signal-specific checks
            if signal.confidence < 0.5:
                logger.debug(f"Signal rejected: Low confidence ({signal.confidence:.2f})")
                return False
            
            if signal.spread_pct < config.MIN_SPREAD_PCT:
                logger.debug(f"Signal rejected: Spread too small ({signal.spread_pct:.2f}%)")
                return False
            
            return True
    
    async def check_stop_loss(self, asset_id: str, current_price: float) -> bool:
        """Check if position should be stopped out"""
        async with self._lock:
            if asset_id not in self.executor.positions:
                return False
            
            position = self.executor.positions[asset_id]
            
            # Calculate loss
            if position.side == "buy":
                loss = (position.entry_price - current_price) * position.size
            else:
                loss = (current_price - position.entry_price) * position.size
            
            # Check stop loss
            if loss >= self.max_loss_per_position:
                logger.warning(f"Stop loss triggered for {asset_id}: ${loss:.2f}")
                await self.executor.close_position(asset_id, current_price)
                self.daily_loss += loss
                return True
            
            return False
    
    async def on_trade_closed(self, pnl: float):
        """Handle closed trade"""
        async with self._lock:
            await self._check_daily_reset()
            
            if pnl < 0:
                self.daily_loss += abs(pnl)
                logger.info(f"Loss recorded: ${abs(pnl):.2f} | Daily loss: ${self.daily_loss:.2f}")
            
            # Check if we should emergency stop
            if self.daily_loss >= self.daily_loss_limit:
                await self.trigger_emergency_stop()
    
    async def trigger_emergency_stop(self):
        """Trigger emergency stop"""
        self.emergency_stop = True
        logger.critical("EMERGENCY STOP TRIGGERED - All trading halted")
        
        # Close all positions
        for asset_id in list(self.executor.positions.keys()):
            # Use last known price or entry price
            position = self.executor.positions[asset_id]
            await self.executor.close_position(asset_id, position.entry_price)
    
    async def reset_emergency_stop(self):
        """Reset emergency stop (manual)"""
        self.emergency_stop = False
        self.daily_loss = 0.0
        self.last_reset = datetime.now()
        logger.info("Emergency stop reset")
    
    async def _check_daily_reset(self):
        """Check if we need to reset daily stats"""
        now = datetime.now()
        if now.date() != self.last_reset.date():
            logger.info("New day - resetting daily stats")
            self.daily_loss = 0.0
            self.last_reset = now
    
    def get_stats(self) -> dict:
        """Get risk manager statistics"""
        return {
            "emergency_stop": self.emergency_stop,
            "daily_loss": self.daily_loss,
            "daily_loss_limit": self.daily_loss_limit,
            "max_positions": self.max_positions,
            "open_positions": self.executor.get_position_count(),
            "can_trade": not self.emergency_stop and self.daily_loss < self.daily_loss_limit
        }
