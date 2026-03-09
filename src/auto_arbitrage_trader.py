"""
Polymarket Auto Arbitrage Trader
Automatically executes arbitrage opportunities
"""
import asyncio
import logging
import signal
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/auto_arbitrage_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)

from polymarket_gamma_api import PolymarketGammaAPI


@dataclass
class TradeConfig:
    """Trading configuration"""
    PAPER_TRADING: bool = True  # Set False for live trading
    TRADE_SIZE_USD: float = 5.0
    MIN_PROFIT_PCT: float = 2.0
    MAX_DAILY_TRADES: int = 10
    RISK_LEVEL: str = "low"  # low, medium, high


class AutoArbitrageTrader:
    """Auto-trader for arbitrage opportunities"""
    
    def __init__(self, config: TradeConfig = None):
        self.config = config or TradeConfig()
        self.api = PolymarketGammaAPI()
        self.running = False
        self.markets = []
        self.daily_trades = 0
        self.total_profit = 0.0
        self.trade_history = []
    
    async def start(self):
        """Start auto-trader"""
        logger.info("=" * 70)
        logger.info("POLYMARKET AUTO ARBITRAGE TRADER")
        logger.info("=" * 70)
        logger.info(f"Mode: {'PAPER' if self.config.PAPER_TRADING else 'LIVE'} TRADING")
        logger.info(f"Trade Size: ${self.config.TRADE_SIZE_USD}")
        logger.info(f"Min Profit: {self.config.MIN_PROFIT_PCT}%")
        logger.info(f"Risk Level: {self.config.RISK_LEVEL}")
        logger.info("=" * 70)
        
        self.running = True
        await self.api.start()
        
        while self.running:
            try:
                # Fetch fresh markets
                self.markets = await self.api.get_all_markets(limit=200)
                
                # Scan for arbitrage
                opportunity = await self._find_best_arbitrage()
                
                if opportunity:
                    logger.info(f"\n[FOUND ARBITRAGE] Profit: {opportunity['profit_pct']:.2f}%")
                    
                    # Check if we should trade
                    if self._should_trade(opportunity):
                        await self._execute_trade(opportunity)
                    else:
                        logger.info("[SKIP] Does not meet criteria")
                else:
                    logger.debug("[SCAN] No arbitrage found")
                
                # Wait before next scan
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(5)
    
    async def _find_best_arbitrage(self) -> Optional[Dict]:
        """Find best arbitrage opportunity"""
        best_opportunity = None
        best_profit = 0.0
        
        # Group markets by event
        event_groups = self._group_by_event()
        
        for event_key, markets in event_groups.items():
            if len(markets) < 2:
                continue
            
            # Calculate total price
            total_price = 0.0
            valid_markets = []
            
            for market in markets:
                best_ask = market.get('bestAsk', 0) or 0
                if best_ask > 0:
                    total_price += best_ask
                    valid_markets.append(market)
            
            # Check arbitrage: total < $1
            if total_price > 0 and total_price < 0.99:
                profit = 1.0 - total_price
                profit_pct = (profit / total_price) * 100
                
                if profit_pct >= self.config.MIN_PROFIT_PCT:
                    if profit_pct > best_profit:
                        best_profit = profit_pct
                        best_opportunity = {
                            'type': 'single_market',
                            'event': event_key,
                            'markets': valid_markets,
                            'investment': total_price * self.config.TRADE_SIZE_USD,
                            'profit': profit * self.config.TRADE_SIZE_USD,
                            'profit_pct': profit_pct,
                            'risk': 'low'
                        }
        
        return best_opportunity
    
    def _group_by_event(self) -> Dict[str, List[Dict]]:
        """Group markets by event"""
        groups = {}
        for market in self.markets:
            slug = market.get('slug', '')
            event_key = slug if slug else market.get('question', '')[:50]
            
            if event_key not in groups:
                groups[event_key] = []
            groups[event_key].append(market)
        return groups
    
    def _should_trade(self, opportunity: Dict) -> bool:
        """Check if opportunity meets trading criteria"""
        # Check daily trade limit
        if self.daily_trades >= self.config.MAX_DAILY_TRADES:
            logger.info("[LIMIT] Daily trade limit reached")
            return False
        
        # Check minimum profit
        if opportunity['profit_pct'] < self.config.MIN_PROFIT_PCT:
            logger.info(f"[PROFIT] Too low: {opportunity['profit_pct']:.2f}%")
            return False
        
        # Check risk level
        if self.config.RISK_LEVEL == 'low' and opportunity['risk'] != 'low':
            logger.info(f"[RISK] Too high: {opportunity['risk']}")
            return False
        
        return True
    
    async def _execute_trade(self, opportunity: Dict):
        """Execute arbitrage trade"""
        logger.info("\n" + "=" * 70)
        logger.info("[EXECUTING TRADE]")
        logger.info("=" * 70)
        logger.info(f"Type: {opportunity['type']}")
        logger.info(f"Event: {opportunity['event'][:50]}...")
        logger.info(f"Investment: ${opportunity['investment']:.2f}")
        logger.info(f"Expected Profit: ${opportunity['profit']:.2f} ({opportunity['profit_pct']:.2f}%)")
        
        if self.config.PAPER_TRADING:
            # Paper trade - simulate execution
            logger.info("[PAPER TRADE] Simulating execution...")
            
            for market in opportunity['markets']:
                question = market.get('question', 'N/A')[:40]
                best_ask = market.get('bestAsk', 0) or 0
                logger.info(f"  BUY: {question}... @ ${best_ask:.4f}")
            
            # Record trade
            trade = {
                'timestamp': datetime.now().isoformat(),
                'type': opportunity['type'],
                'event': opportunity['event'],
                'investment': opportunity['investment'],
                'expected_profit': opportunity['profit'],
                'profit_pct': opportunity['profit_pct'],
                'markets': [m.get('question', 'N/A') for m in opportunity['markets']],
                'status': 'open'
            }
            
            self.trade_history.append(trade)
            self.daily_trades += 1
            self.total_profit += opportunity['profit']
            
            logger.info(f"[SUCCESS] Paper trade recorded!")
            logger.info(f"[STATS] Daily trades: {self.daily_trades} | Total profit: ${self.total_profit:.2f}")
            
        else:
            # Live trading - would execute real orders here
            logger.info("[LIVE TRADE] Would execute real orders...")
            logger.warning("[NOTE] Live trading not yet implemented - need API key")
            # TODO: Implement actual order execution with Polymarket API
    
    def get_stats(self) -> Dict:
        """Get trading statistics"""
        return {
            'daily_trades': self.daily_trades,
            'total_profit': self.total_profit,
            'trade_history': len(self.trade_history)
        }
    
    async def stop(self):
        """Stop trader"""
        self.running = False
        await self.api.stop()
        
        logger.info("\n" + "=" * 70)
        logger.info("[FINAL STATS]")
        logger.info("=" * 70)
        logger.info(f"Total Trades: {self.daily_trades}")
        logger.info(f"Total Profit: ${self.total_profit:.2f}")
        logger.info("Trader stopped")


async def main():
    # Configuration
    config = TradeConfig(
        PAPER_TRADING=True,      # Set to False for live trading
        TRADE_SIZE_USD=5.0,      # $5 per trade
        MIN_PROFIT_PCT=2.0,      # 2% minimum profit
        MAX_DAILY_TRADES=10,     # Max 10 trades per day
        RISK_LEVEL="low"         # Low risk only
    )
    
    trader = AutoArbitrageTrader(config)
    
    def handler(s, f):
        asyncio.create_task(trader.stop())
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    
    try:
        await trader.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await trader.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
