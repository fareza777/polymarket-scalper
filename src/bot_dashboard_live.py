"""
Polymarket Scalper Bot - LIVE with Dashboard
"""
import asyncio
import logging
import signal
import sys
import os
import aiohttp
from datetime import datetime
from typing import List, Dict

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/dashboard_live_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)

from polymarket_gamma_api import PolymarketGammaAPI


class DashboardClient:
    """Send data to dashboard"""
    
    def __init__(self, url="http://localhost:5555"):
        self.url = url
        self.session = None
    
    async def start(self):
        self.session = aiohttp.ClientSession()
        logger.info("Dashboard client started")
    
    async def stop(self):
        if self.session:
            await self.session.close()
    
    async def send_stats(self, stats: dict):
        if not self.session:
            return
        try:
            await self.session.post(f"{self.url}/api/update", json=stats, timeout=2)
        except:
            pass
    
    async def send_trade(self, trade: dict):
        if not self.session:
            return
        try:
            await self.session.post(f"{self.url}/api/trade", json=trade, timeout=2)
        except:
            pass
    
    async def send_signal(self, signal: dict):
        if not self.session:
            return
        try:
            await self.session.post(f"{self.url}/api/signal", json=signal, timeout=2)
        except:
            pass


class LiveTrader:
    def __init__(self, api: PolymarketGammaAPI, dashboard: DashboardClient):
        self.api = api
        self.dashboard = dashboard
        self.positions: Dict[str, dict] = {}
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
        
        trade = {
            "asset_id": token_id,
            "side": "buy",
            "price": entry_price,
            "size": trade_size,
            "timestamp": datetime.now().isoformat(),
            "pnl": 0.0,
            "market": signal_data.get('market_name', 'Unknown')
        }
        
        await self.dashboard.send_trade(trade)
        logger.info(f"[TRADE] {token_id[:30]}... @ {entry_price:.4f}")
        return trade
    
    async def update_positions(self):
        for token_id, pos in list(self.positions.items()):
            # Simulate P&L update (in real bot, fetch current price)
            import random
            change = random.uniform(-0.02, 0.02)
            current = pos["entry"] * (1 + change)
            pos["pnl"] = (current - pos["entry"]) * pos["size"]
    
    async def check_exits(self):
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
                await self.dashboard.send_trade(trade)
                del self.positions[token_id]
                
                logger.info(f"[CLOSE] {token_id[:30]}... | {exit_reason} | P&L: ${pnl:.2f}")
    
    def get_stats(self) -> dict:
        open_pnl = sum(p.get("pnl", 0) for p in self.positions.values())
        wins = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        total = len([t for t in self.trades if t.get("pnl") is not None])
        win_rate = (wins / total * 100) if total > 0 else 0.0
        
        return {
            "open": len(self.positions),
            "trades": len(self.trades),
            "daily_pnl": self.daily_pnl,
            "open_pnl": open_pnl,
            "total_pnl": self.daily_pnl + open_pnl,
            "win_rate": win_rate
        }


class Bot:
    def __init__(self):
        self.api = PolymarketGammaAPI()
        self.dashboard = DashboardClient()
        self.trader = None
        self.running = False
        self.markets = []
        self.signals_count = 0
        self.scan_count = 0
        self.start_time = None
    
    async def start(self):
        logger.info("=" * 70)
        logger.info("BOT LIVE + DASHBOARD")
        logger.info("=" * 70)
        
        self.running = True
        self.start_time = datetime.now()
        
        await self.api.start()
        await self.dashboard.start()
        
        self.trader = LiveTrader(self.api, self.dashboard)
        
        logger.info("Fetching markets...")
        self.markets = await self.api.get_all_markets(limit=50)
        
        if not self.markets:
            logger.error("No markets!")
            await self.stop()
            return
        
        logger.info(f"Monitoring {len(self.markets)} markets")
        
        # Send initial stats
        await self.dashboard.send_stats({
            "status": "running",
            "markets_monitored": len(self.markets),
            "runtime": "00:00:00"
        })
        
        while self.running:
            try:
                self.scan_count += 1
                await self.scan()
                await self.trader.update_positions()
                closed = await self.trader.check_exits()
                
                # Send stats every scan
                stats = self.trader.get_stats()
                runtime = datetime.now() - self.start_time
                await self.dashboard.send_stats({
                    "status": "running",
                    "runtime": str(runtime).split('.')[0],
                    "signals_generated": self.signals_count,
                    "trades_executed": stats["trades"],
                    "open_positions": stats["open"],
                    "daily_pnl": stats["daily_pnl"],
                    "open_pnl": stats["open_pnl"],
                    "total_pnl": stats["total_pnl"],
                    "win_rate": stats["win_rate"],
                    "last_update": datetime.now().isoformat()
                })
                
                if self.scan_count % 12 == 0:
                    self.print_stats()
                
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(5)
    
    async def scan(self):
        for market in self.markets[:20]:
            try:
                best_bid = market.get("bestBid")
                best_ask = market.get("bestAsk")
                spread = market.get("spread", 0)
                liquidity = market.get("liquidityNum", 0)
                market_name = self.api.get_market_display_name(market)
                
                if best_bid is None or best_ask is None:
                    continue
                
                mid_price = (best_bid + best_ask) / 2
                spread_pct = (spread / mid_price) * 100 if mid_price > 0 else 0
                
                if spread_pct >= 0.3 and liquidity >= 100:
                    self.signals_count += 1
                    
                    signal_data = {
                        'entry_price': best_bid,
                        'target_price': best_ask,
                        'spread_pct': spread_pct,
                        'liquidity': liquidity,
                        'market_name': market_name
                    }
                    
                    # Send signal to dashboard
                    await self.dashboard.send_signal({
                        "asset_id": market.get("conditionId", ""),
                        "side": "buy",
                        "spread_pct": spread_pct,
                        "confidence": min(spread_pct / 5, 1.0),
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    logger.info(f"[SIGNAL] {market_name[:40]}... | Spread: {spread_pct:.2f}%")
                    
                    token_id = market.get("conditionId", "")
                    if token_id:
                        await self.trader.execute_signal(token_id, signal_data)
            except Exception as e:
                logger.debug(f"Scan error: {e}")
    
    def print_stats(self):
        stats = self.trader.get_stats()
        runtime = datetime.now() - self.start_time
        logger.info("-" * 70)
        logger.info(f"Runtime: {runtime}")
        logger.info(f"Scans: {self.scan_count} | Signals: {self.signals_count} | Trades: {stats['trades']}")
        logger.info(f"Daily P&L: ${stats['daily_pnl']:.2f} | Open P&L: ${stats['open_pnl']:.2f}")
        logger.info("-" * 70)
    
    async def stop(self):
        self.running = False
        await self.api.stop()
        await self.dashboard.stop()
        self.print_stats()
        logger.info("Bot stopped")


async def main():
    bot = Bot()
    
    def handler(s, f):
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, handler)
    
    try:
        await bot.start()
    except Exception as e:
        logger.error(f"Fatal: {e}")
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
