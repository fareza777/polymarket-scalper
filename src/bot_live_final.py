"""
Polymarket Scalper Bot - LIVE FINAL VERSION
Uses Gamma API + CLOB for real market data
"""
import asyncio
import logging
import signal
import sys
import os
from datetime import datetime
from typing import List

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/live_bot_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)

from polymarket_gamma_api import PolymarketGammaAPI


class LiveTrader:
    def __init__(self, api: PolymarketGammaAPI):
        self.api = api
        self.positions = {}
        self.trades = []
        self.daily_pnl = 0.0
    
    async def execute_signal(self, token_id: str, signal_data: dict, trade_size: float = 5.0):
        if token_id in self.positions:
            return None
        
        entry_price = signal_data['entry_price']
        size = trade_size / entry_price
        
        self.positions[token_id] = {
            "entry": entry_price,
            "size": size,
            "side": "buy",
            "time": datetime.now(),
            "pnl": 0.0,
            "market": signal_data.get('market_name', 'Unknown')
        }
        
        logger.info(f"[TRADE] Buy {token_id[:30]}... @ {entry_price:.4f} | Spread: {signal_data['spread_pct']:.2f}%")
        
        return {
            "asset_id": token_id,
            "side": "buy",
            "price": entry_price,
            "size": trade_size,
            "timestamp": datetime.now().isoformat(),
            "pnl": 0.0,
            "market": signal_data.get('market_name', 'Unknown')
        }
    
    async def update_positions(self):
        for token_id, pos in list(self.positions.items()):
            try:
                orderbook = await self.api.get_orderbook(token_id)
                if orderbook and orderbook.get("asks"):
                    current_price = float(orderbook["asks"][0]["price"])
                    pos["pnl"] = (current_price - pos["entry"]) * pos["size"]
            except Exception as e:
                logger.debug(f"Error updating position: {e}")
    
    async def check_exits(self) -> List[dict]:
        closed_trades = []
        
        for token_id, pos in list(self.positions.items()):
            pnl = pos.get("pnl", 0)
            hold_time = (datetime.now() - pos["time"]).total_seconds() / 60
            
            exit_reason = None
            if pnl > 0.50:
                exit_reason = "take_profit"
            elif pnl < -1.00:
                exit_reason = "stop_loss"
            elif hold_time > 30:
                exit_reason = "timeout"
            
            if exit_reason:
                self.daily_pnl += pnl
                
                trade = {
                    "asset_id": token_id,
                    "side": "sell",
                    "price": pos["entry"],
                    "size": pos["size"] * pos["entry"],
                    "timestamp": datetime.now().isoformat(),
                    "pnl": pnl,
                    "exit_reason": exit_reason,
                    "market": pos.get("market", "Unknown")
                }
                
                self.trades.append(trade)
                closed_trades.append(trade)
                del self.positions[token_id]
                
                logger.info(f"[CLOSE] {token_id[:30]}... | {exit_reason} | P&L: ${pnl:.2f}")
        
        return closed_trades
    
    def get_stats(self) -> dict:
        open_pnl = sum(p.get("pnl", 0) for p in self.positions.values())
        closed = [t for t in self.trades if t.get("pnl") is not None]
        wins = sum(1 for t in closed if t["pnl"] > 0)
        win_rate = (wins / len(closed) * 100) if closed else 0.0
        
        return {
            "open": len(self.positions),
            "trades": len(self.trades),
            "daily_pnl": self.daily_pnl,
            "open_pnl": open_pnl,
            "total_pnl": self.daily_pnl + open_pnl,
            "win_rate": win_rate
        }


class LiveBot:
    def __init__(self):
        self.api = PolymarketGammaAPI()
        self.trader = LiveTrader(self.api)
        self.running = False
        self.markets = []
        self.monitored_tokens = {}
        self.signals_count = 0
        self.start_time = None
        self.scan_count = 0
    
    async def start(self):
        logger.info("=" * 70)
        logger.info("POLYMARKET SCALPER BOT - LIVE FINAL")
        logger.info("Using Gamma API + CLOB")
        logger.info("=" * 70)
        
        self.running = True
        self.start_time = datetime.now()
        
        await self.api.start()
        
        logger.info("Fetching active markets from Gamma API...")
        self.markets = await self.api.get_all_markets(limit=50)
        
        if not self.markets:
            logger.error("No active markets found!")
            await self.stop()
            return
        
        logger.info(f"Monitoring {len(self.markets)} markets:")
        for market in self.markets[:5]:
            name = self.api.get_market_display_name(market)
            logger.info(f"  - {name}")
        
        for market in self.markets:
            tokens = self.api.extract_token_ids(market)
            market_name = self.api.get_market_display_name(market)
            for token in tokens:
                self.monitored_tokens[token] = market_name
        
        logger.info(f"Total tokens: {len(self.monitored_tokens)}")
        logger.info("Starting main loop...")
        logger.info("=" * 70)
        
        while self.running:
            try:
                self.scan_count += 1
                await self.scan_opportunities()
                await self.trader.update_positions()
                await self.trader.check_exits()
                
                # Print stats every minute OR if there are open positions
                if self.scan_count % 12 == 0 or self.trader.positions:
                    self.print_stats()
                
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(10)
    
    async def scan_opportunities(self):
        logger.info(f"Scan {self.scan_count}: Checking {len(self.markets)} markets...")
        for market in self.markets[:20]:  # Check top 20 markets
            try:
                # Use data directly from Gamma API (bestBid, bestAsk, spread)
                best_bid = market.get("bestBid")
                best_ask = market.get("bestAsk")
                spread = market.get("spread", 0)
                liquidity = market.get("liquidityNum", 0) or market.get("liquidity", 0)
                market_name = self.api.get_market_display_name(market)
                
                if best_bid is None or best_ask is None:
                    continue
                
                # Calculate spread percentage
                mid_price = (best_bid + best_ask) / 2
                spread_pct = (spread / mid_price) * 100 if mid_price > 0 else 0
                
                # Debug: Log all spreads
                if self.scan_count <= 3 or spread_pct >= 0.3:
                    logger.info(f"Scan {market_name[:30]}... | Spread: {spread_pct:.3f}% | Liq: ${liquidity:.0f}")
                
                # Signal threshold
                if spread_pct >= 0.3 and liquidity >= 100:
                    self.signals_count += 1
                    
                    signal_data = {
                        'entry_price': best_bid,
                        'target_price': best_ask,
                        'spread_pct': spread_pct,
                        'liquidity': liquidity,
                        'market_name': market_name
                    }
                    
                    logger.info(f"[SIGNAL] {market_name[:40]}... | Spread: {spread_pct:.2f}%")
                    
                    # Use conditionId as token_id for tracking
                    token_id = market.get("conditionId", "")
                    if token_id:
                        await self.trader.execute_signal(token_id, signal_data)
                
            except Exception as e:
                logger.debug(f"Error scanning: {e}")
    
    def print_stats(self):
        stats = self.trader.get_stats()
        runtime = datetime.now() - self.start_time if self.start_time else None
        
        # Calculate open positions P&L
        open_positions_detail = []
        for token_id, pos in self.trader.positions.items():
            pnl = pos.get('pnl', 0)
            open_positions_detail.append(f"{pos.get('market', 'Unknown')[:20]}...: ${pnl:.2f}")
        
        logger.info("=" * 70)
        logger.info(f"STATS - Runtime: {runtime}")
        logger.info(f"Scans: {self.scan_count} | Signals: {self.signals_count} | Trades: {stats['trades']}")
        logger.info(f"Daily P&L: ${stats['daily_pnl']:.2f} | Open P&L: ${stats['open_pnl']:.2f} | Total: ${stats['total_pnl']:.2f}")
        logger.info(f"Win Rate: {stats['win_rate']:.1f}% | Open Positions: {stats['open']}")
        
        if open_positions_detail:
            logger.info("Open Positions:")
            for detail in open_positions_detail[:5]:  # Show max 5
                logger.info(f"  - {detail}")
        
        logger.info("=" * 70)
    
    async def stop(self):
        self.running = False
        await self.api.stop()
        self.print_stats()
        logger.info("Bot stopped")


async def main():
    bot = LiveBot()
    
    def handler(s, f):
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    
    try:
        await bot.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await bot.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
