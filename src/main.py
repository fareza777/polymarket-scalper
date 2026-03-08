"""
Polymarket Scalper Bot - Main Entry Point
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime

from config import config
from websocket_client import PolymarketWebSocket, WSConfig
from orderbook import OrderbookAggregator
from spread_detector import SpreadDetector
from trade_executor import TradeExecutor
from risk_manager import RiskManager

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/scalper_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)


class ScalperBot:
    """Main bot orchestrator"""
    
    def __init__(self):
        self.running = False
        
        # Components
        self.orderbook = OrderbookAggregator()
        self.executor = TradeExecutor()
        self.risk_manager = RiskManager(self.executor)
        self.detector = SpreadDetector(
            self.orderbook,
            on_signal=self._on_signal
        )
        self.ws = PolymarketWebSocket(
            WSConfig(
                url=config.WS_URL,
                heartbeat_interval=config.WS_HEARTBEAT_INTERVAL,
                reconnect_delay=config.WS_RECONNECT_DELAY
            ),
            on_book=self._on_book,
            on_price_change=self._on_price_change,
            on_last_trade=self._on_last_trade,
            on_error=self._on_error
        )
        
        # Stats
        self.signals_generated = 0
        self.trades_executed = 0
        self.start_time = None
    
    async def start(self):
        """Start the bot"""
        logger.info("=" * 60)
        logger.info("Polymarket Scalper Bot Starting...")
        logger.info(f"Mode: {'PAPER' if config.PAPER_TRADING else 'LIVE'}")
        logger.info(f"Trade Size: ${config.TRADE_SIZE_USD}")
        logger.info(f"Min Spread: {config.MIN_SPREAD_PCT}%")
        logger.info("=" * 60)
        
        self.running = True
        self.start_time = datetime.now()
        
        # Initialize components
        await self.executor.start()
        await self.detector.start()
        
        # Connect WebSocket
        if await self.ws.connect():
            # Subscribe to markets
            # TODO: Get actual crypto market asset IDs from Polymarket API
            # For now using placeholder
            await self.ws.subscribe(config.CRYPTO_MARKETS)
            
            # Run main loop
            await self._main_loop()
        else:
            logger.error("Failed to connect to WebSocket")
    
    async def stop(self):
        """Stop the bot gracefully"""
        logger.info("Stopping bot...")
        self.running = False
        
        await self.ws.disconnect()
        await self.detector.stop()
        await self.executor.stop()
        
        self._print_stats()
        logger.info("Bot stopped")
    
    async def _main_loop(self):
        """Main bot loop"""
        while self.running:
            try:
                # Check risk limits
                if not await self.risk_manager.can_trade():
                    await asyncio.sleep(5)
                    continue
                
                # Check stop losses for open positions
                await self._check_stop_losses()
                
                # Print periodic stats
                await self._print_periodic_stats()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(5)
    
    async def _on_book(self, data):
        """Handle orderbook update"""
        try:
            asset_id = data.get("asset_id")
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            await self.orderbook.update_book(asset_id, bids, asks)
        except Exception as e:
            logger.error(f"Book update error: {e}")
    
    async def _on_price_change(self, data):
        """Handle price change"""
        try:
            asset_id = data.get("asset_id")
            # Price change events may contain updates to specific price levels
            # For now, we'll rely on book updates for orderbook state
            pass
        except Exception as e:
            logger.error(f"Price change error: {e}")
    
    async def _on_last_trade(self, data):
        """Handle last trade price"""
        try:
            asset_id = data.get("asset_id")
            price = data.get("price")
            
            if asset_id and price:
                await self.orderbook.update_last_trade(asset_id, price)
        except Exception as e:
            logger.error(f"Last trade error: {e}")
    
    async def _on_error(self, error):
        """Handle WebSocket error"""
        logger.error(f"WebSocket error: {error}")
    
    async def _on_signal(self, signal):
        """Handle trading signal"""
        logger.info(f"Signal received: {signal.asset_id} | "
                   f"Spread: {signal.spread_pct:.2f}% | Confidence: {signal.confidence:.2f}")
        
        self.signals_generated += 1
        
        # Check risk
        if not await self.risk_manager.check_signal(signal):
            return
        
        # Execute trade
        if await self.executor.execute_signal(signal):
            self.trades_executed += 1
            self.detector.record_trade(signal.asset_id)
    
    async def _check_stop_losses(self):
        """Check stop losses for all positions"""
        for asset_id in list(self.executor.positions.keys()):
            market = await self.orderbook.get_market(asset_id)
            if market and market.mid_price():
                await self.risk_manager.check_stop_loss(asset_id, market.mid_price())
    
    async def _print_periodic_stats(self):
        """Print stats every 60 seconds"""
        if not hasattr(self, '_last_stats_time'):
            self._last_stats_time = datetime.now()
        
        elapsed = (datetime.now() - self._last_stats_time).total_seconds()
        if elapsed >= 60:
            self._print_stats()
            self._last_stats_time = datetime.now()
    
    def _print_stats(self):
        """Print bot statistics"""
        runtime = datetime.now() - self.start_time if self.start_time else None
        
        logger.info("=" * 60)
        logger.info("BOT STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Runtime: {runtime}")
        logger.info(f"Signals Generated: {self.signals_generated}")
        logger.info(f"Trades Executed: {self.trades_executed}")
        logger.info(f"Open Positions: {self.executor.get_position_count()}")
        logger.info(f"Open P&L: ${self.executor.get_open_pnl():.2f}")
        logger.info(f"Daily P&L: ${self.executor.get_daily_pnl():.2f}")
        logger.info(f"Risk Status: {'OK' if not self.risk_manager.emergency_stop else 'STOPPED'}")
        logger.info("=" * 60)


def signal_handler(bot):
    """Handle shutdown signals"""
    def handler(signum, frame):
        logger.info(f"Received signal {signum}")
        asyncio.create_task(bot.stop())
    return handler


async def main():
    """Main entry point"""
    # Create logs directory
    import os
    os.makedirs('logs', exist_ok=True)
    
    bot = ScalperBot()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler(bot))
    signal.signal(signal.SIGTERM, signal_handler(bot))
    
    try:
        await bot.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await bot.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
