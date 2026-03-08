"""
Polymarket Scalper Bot - Paper Trading Version
Uses real market data from Polymarket API
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime

from config import config
from polymarket_api import PolymarketAPI
from paper_trader import PaperTrader
from spread_detector import SpreadDetector, Signal

# Setup logging
# Create logs directory
import os
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/paper_bot_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)


class PaperTradingBot:
    """Paper trading bot with real market data"""
    
    def __init__(self):
        self.running = False
        
        # Components
        self.api = PolymarketAPI()
        self.trader = PaperTrader(self.api)
        self.detector = None
        
        # Market data
        self.crypto_markets = []
        self.monitored_tokens = set()
        
        # Stats
        self.start_time = None
        self.signals_generated = 0
    
    async def start(self):
        """Start the bot"""
        logger.info("=" * 60)
        logger.info("Polymarket Paper Trading Bot Starting...")
        logger.info("=" * 60)
        
        self.running = True
        self.start_time = datetime.now()
        
        # Initialize API
        await self.api.start()
        
        # Get crypto markets
        logger.info("Fetching crypto markets...")
        self.crypto_markets = await self.api.get_crypto_markets()
        
        if not self.crypto_markets:
            logger.error("No crypto markets found!")
            await self.stop()
            return
        
        # Extract token IDs to monitor
        for market in self.crypto_markets[:10]:  # Monitor top 10
            tokens = self.api.extract_token_ids(market)
            self.monitored_tokens.update(tokens)
        
        logger.info(f"Monitoring {len(self.monitored_tokens)} tokens")
        
        # Initialize spread detector with custom handler
        self.detector = SpreadDetector(
            orderbook=None,  # We'll fetch fresh data each cycle
            on_signal=self._on_signal,
            min_spread_pct=config.MIN_SPREAD_PCT,
            min_liquidity=config.MIN_LIQUIDITY
        )
        
        # Start trader
        await self.trader.update_positions()
        
        # Run main loop
        await self._main_loop()
    
    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping bot...")
        self.running = False
        
        if self.api:
            await self.api.stop()
        
        self._print_stats()
        logger.info("Bot stopped")
    
    async def _main_loop(self):
        """Main bot loop"""
        logger.info("Starting main loop (scanning every 5 seconds)...")
        
        while self.running:
            try:
                # Scan all monitored tokens
                await self._scan_opportunities()
                
                # Update positions
                await self.trader.update_positions()
                
                # Check exit conditions
                await self.trader.check_exit_conditions()
                
                # Print stats
                await self._print_periodic_stats()
                
                # Wait before next scan
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(10)
    
    async def _scan_opportunities(self):
        """Scan for trading opportunities"""
        for token_id in list(self.monitored_tokens)[:5]:  # Scan 5 at a time
            try:
                # Get orderbook
                orderbook = await self.api.get_orderbook(token_id)
                if not orderbook:
                    continue
                
                # Parse orderbook
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                
                if not bids or not asks:
                    continue
                
                # Calculate spread
                best_bid = float(bids[0]["price"])
                best_ask = float(asks[0]["price"])
                mid_price = (best_bid + best_ask) / 2
                spread_pct = ((best_ask - best_bid) / mid_price) * 100
                
                # Calculate liquidity
                bid_liquidity = sum(float(b["size"]) * float(b["price"]) for b in bids[:5])
                ask_liquidity = sum(float(a["size"]) * float(a["price"]) for a in asks[:5])
                total_liquidity = bid_liquidity + ask_liquidity
                
                # Check if opportunity exists
                if spread_pct >= config.MIN_SPREAD_PCT and total_liquidity >= config.MIN_LIQUIDITY:
                    # Calculate confidence
                    spread_score = min(spread_pct / 5.0, 1.0)
                    liquidity_score = min(total_liquidity / 10000.0, 1.0)
                    confidence = (spread_score * 0.6 + liquidity_score * 0.4)
                    
                    if confidence >= 0.5:
                        signal = Signal(
                            asset_id=token_id,
                            side="buy",
                            entry_price=best_bid,
                            target_price=best_ask,
                            spread_pct=spread_pct,
                            liquidity=total_liquidity,
                            confidence=confidence,
                            timestamp=datetime.now()
                        )
                        
                        await self._on_signal(signal)
                
            except Exception as e:
                logger.error(f"Error scanning {token_id}: {e}")
    
    async def _on_signal(self, signal: Signal):
        """Handle trading signal"""
        logger.info(
            f"SIGNAL | {signal.asset_id[:20]}... | "
            f"Spread: {signal.spread_pct:.2f}% | Confidence: {signal.confidence:.2f}"
        )
        
        self.signals_generated += 1
        
        # Check if we can trade
        stats = self.trader.get_stats()
        if stats["open_positions"] >= config.MAX_POSITIONS:
            logger.debug("Max positions reached, skipping signal")
            return
        
        # Execute paper trade
        success = await self.trader.execute_signal(signal, config.TRADE_SIZE_USD)
        
        if success:
            logger.info(f"Paper trade executed for {signal.asset_id}")
    
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
        stats = self.trader.get_stats()
        runtime = datetime.now() - self.start_time if self.start_time else None
        
        logger.info("=" * 60)
        logger.info("PAPER TRADING STATS")
        logger.info("=" * 60)
        logger.info(f"Runtime: {runtime}")
        logger.info(f"Signals Generated: {self.signals_generated}")
        logger.info(f"Daily P&L: ${stats['daily_pnl']:.2f}")
        logger.info(f"Open P&L: ${stats['open_pnl']:.2f}")
        logger.info(f"Win Rate: {stats['win_rate']:.1f}%")
        logger.info(f"Total Trades: {stats['total_trades']}")
        logger.info(f"Open Positions: {stats['open_positions']}/{config.MAX_POSITIONS}")
        logger.info("=" * 60)


def signal_handler(bot):
    """Handle shutdown signals"""
    def handler(signum, frame):
        logger.info(f"Received signal {signum}")
        asyncio.create_task(bot.stop())
    return handler


async def main():
    """Main entry point"""
    import os
    os.makedirs('logs', exist_ok=True)
    
    bot = PaperTradingBot()
    
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
