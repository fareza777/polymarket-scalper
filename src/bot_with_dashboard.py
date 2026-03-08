"""
Polymarket Scalper Bot with Dashboard Integration
"""
import asyncio
import logging
import signal
import sys
import os
import random
import json
from datetime import datetime
from typing import Dict, List
import aiohttp

# Setup logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/bot_dashboard_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)


class DashboardClient:
    """Client to send data to dashboard"""
    
    def __init__(self, dashboard_url="http://localhost:5555"):
        self.dashboard_url = dashboard_url
        self.session = None
        self.enabled = True
    
    async def start(self):
        try:
            self.session = aiohttp.ClientSession()
            # Test connection
            async with self.session.get(f"{self.dashboard_url}/api/stats", timeout=2) as resp:
                if resp.status == 200:
                    logger.info("Dashboard connected")
                else:
                    logger.warning("Dashboard not responding, running without dashboard")
                    self.enabled = False
        except Exception as e:
            logger.warning(f"Dashboard not available: {e}")
            self.enabled = False
    
    async def stop(self):
        if self.session:
            await self.session.close()
    
    async def update_stats(self, stats: dict):
        """Send stats to dashboard"""
        if not self.enabled or not self.session:
            return
        
        try:
            async with self.session.post(
                f"{self.dashboard_url}/api/update",
                json=stats,
                timeout=1
            ) as resp:
                pass
        except:
            pass  # Silent fail
    
    async def add_trade(self, trade: dict):
        """Add trade to dashboard"""
        if not self.enabled or not self.session:
            return
        
        try:
            async with self.session.post(
                f"{self.dashboard_url}/api/trade",
                json=trade,
                timeout=1
            ) as resp:
                pass
        except:
            pass
    
    async def add_signal(self, signal: dict):
        """Add signal to dashboard"""
        if not self.enabled or not self.session:
            return
        
        try:
            async with self.session.post(
                f"{self.dashboard_url}/api/signal",
                json=signal,
                timeout=1
            ) as resp:
                pass
        except:
            pass


class SimpleMockAPI:
    """Simple mock API"""
    
    def __init__(self):
        self.markets = [
            {"id": "BTC-100K", "name": "Bitcoin > $100K", "price": 0.65},
            {"id": "ETH-5K", "name": "Ethereum > $5K", "price": 0.45},
            {"id": "SOL-200", "name": "Solana > $200", "price": 0.35},
        ]
        self.prices = {m["id"]: m["price"] for m in self.markets}
    
    async def start(self):
        logger.info("Mock API started")
    
    async def stop(self):
        logger.info("Mock API stopped")
    
    async def get_crypto_markets(self):
        return self.markets
    
    def extract_token_ids(self, market):
        return [market["id"]]
    
    async def get_orderbook(self, token_id):
        base = self.prices.get(token_id, 0.5)
        spread = random.uniform(0.01, 0.03)
        
        return {
            "bids": [{"price": round(base - spread/2, 4), "size": random.randint(100, 1000)}],
            "asks": [{"price": round(base + spread/2, 4), "size": random.randint(100, 1000)}]
        }
    
    def update_prices(self):
        for m in self.markets:
            change = random.uniform(-0.02, 0.02)
            self.prices[m["id"]] = max(0.01, min(0.99, self.prices[m["id"]] * (1 + change)))


class SimpleTrader:
    """Simple paper trader"""
    
    def __init__(self):
        self.positions = {}
        self.trades = []
        self.daily_pnl = 0.0
    
    async def execute_signal(self, signal, trade_size=5.0):
        if signal.asset_id in self.positions:
            return None
        
        size = trade_size / signal.entry_price
        self.positions[signal.asset_id] = {
            "entry": signal.entry_price,
            "size": size,
            "side": "buy",
            "time": datetime.now(),
            "pnl": 0.0
        }
        
        logger.info(f"TRADE: Buy {signal.asset_id} @ {signal.entry_price:.4f}")
        
        return {
            "asset_id": signal.asset_id,
            "side": "buy",
            "price": signal.entry_price,
            "size": trade_size,
            "timestamp": datetime.now().isoformat(),
            "pnl": 0.0
        }
    
    async def update_positions(self, api):
        for asset_id, pos in list(self.positions.items()):
            ob = await api.get_orderbook(asset_id)
            if ob and ob["asks"]:
                current = ob["asks"][0]["price"]
                pos["pnl"] = (current - pos["entry"]) * pos["size"]
    
    async def check_exits(self):
        closed_trades = []
        for asset_id, pos in list(self.positions.items()):
            pnl = pos.get("pnl", 0)
            
            if pnl > 0.5 or pnl < -1.0:
                self.daily_pnl += pnl
                trade = {
                    "asset_id": asset_id,
                    "side": "sell",
                    "price": pos["entry"],
                    "size": pos["size"] * pos["entry"],
                    "timestamp": datetime.now().isoformat(),
                    "pnl": pnl
                }
                self.trades.append(trade)
                closed_trades.append(trade)
                del self.positions[asset_id]
                logger.info(f"CLOSE: {asset_id} P&L: ${pnl:.2f}")
        
        return closed_trades
    
    def get_stats(self):
        open_pnl = sum(p.get("pnl", 0) for p in self.positions.values())
        
        wins = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        total = len(self.trades)
        win_rate = (wins / total * 100) if total > 0 else 0.0
        
        return {
            "open": len(self.positions),
            "trades": len(self.trades),
            "daily_pnl": self.daily_pnl,
            "open_pnl": open_pnl,
            "total_pnl": self.daily_pnl + open_pnl,
            "win_rate": win_rate,
            "total_volume": sum(t.get("size", 0) for t in self.trades)
        }


class Signal:
    def __init__(self, asset_id, side, entry_price, target_price, spread_pct, liquidity, confidence):
        self.asset_id = asset_id
        self.side = side
        self.entry_price = entry_price
        self.target_price = target_price
        self.spread_pct = spread_pct
        self.liquidity = liquidity
        self.confidence = confidence
        self.timestamp = datetime.now()


class Bot:
    def __init__(self):
        self.api = SimpleMockAPI()
        self.trader = SimpleTrader()
        self.dashboard = DashboardClient()
        self.running = False
        self.signals = 0
        self.start_time = None
    
    async def start(self):
        logger.info("=" * 60)
        logger.info("BOT STARTING - With Dashboard Integration")
        logger.info("=" * 60)
        
        self.running = True
        self.start_time = datetime.now()
        
        await self.api.start()
        await self.dashboard.start()
        
        markets = await self.api.get_crypto_markets()
        logger.info(f"Markets: {len(markets)}")
        for m in markets:
            logger.info(f"  - {m['name']}")
        
        # Update dashboard status
        await self.dashboard.update_stats({
            "status": "running",
            "markets_monitored": len(markets),
            "runtime": "00:00:00"
        })
        
        while self.running:
            try:
                self.api.update_prices()
                
                # Scan and trade
                new_signals = await self.scan()
                for sig in new_signals:
                    await self.dashboard.add_signal({
                        "asset_id": sig.asset_id,
                        "side": sig.side,
                        "spread_pct": sig.spread_pct,
                        "confidence": sig.confidence,
                        "timestamp": sig.timestamp.isoformat()
                    })
                
                # Update positions
                await self.trader.update_positions(self.api)
                
                # Check exits
                closed_trades = await self.trader.check_exits()
                for trade in closed_trades:
                    await self.dashboard.add_trade(trade)
                
                # Update dashboard stats
                if self.signals % 5 == 0:
                    await self.update_dashboard()
                
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(5)
    
    async def scan(self):
        """Scan for opportunities"""
        new_signals = []
        markets = await self.api.get_crypto_markets()
        
        for market in markets:
            token_id = market["id"]
            ob = await self.api.get_orderbook(token_id)
            
            if not ob or not ob["bids"] or not ob["asks"]:
                continue
            
            bid = ob["bids"][0]["price"]
            ask = ob["asks"][0]["price"]
            spread = ((ask - bid) / ((ask + bid) / 2)) * 100
            
            if spread >= 1.0:
                self.signals += 1
                signal = Signal(
                    asset_id=token_id,
                    side="buy",
                    entry_price=bid,
                    target_price=ask,
                    spread_pct=spread,
                    liquidity=1000,
                    confidence=min(spread / 5, 1.0)
                )
                
                logger.info(f"SIGNAL: {token_id} | Spread: {spread:.2f}%")
                new_signals.append(signal)
                
                # Execute trade
                trade = await self.trader.execute_signal(signal)
                if trade:
                    await self.dashboard.add_trade(trade)
        
        return new_signals
    
    async def update_dashboard(self):
        """Update dashboard with current stats"""
        stats = self.trader.get_stats()
        runtime = datetime.now() - self.start_time if self.start_time else None
        
        await self.dashboard.update_stats({
            "status": "running",
            "runtime": str(runtime).split('.')[0] if runtime else "00:00:00",
            "signals_generated": self.signals,
            "trades_executed": stats["trades"],
            "open_positions": stats["open"],
            "daily_pnl": stats["daily_pnl"],
            "open_pnl": stats["open_pnl"],
            "total_pnl": stats["total_pnl"],
            "win_rate": stats["win_rate"],
            "total_volume": stats["total_volume"],
            "last_update": datetime.now().isoformat()
        })
    
    async def stop(self):
        self.running = False
        await self.api.stop()
        await self.dashboard.stop()
        
        stats = self.trader.get_stats()
        logger.info("-" * 60)
        logger.info(f"FINAL STATS - Signals: {self.signals} | Trades: {stats['trades']}")
        logger.info(f"Daily P&L: ${stats['daily_pnl']:.2f} | Win Rate: {stats['win_rate']:.1f}%")
        logger.info("-" * 60)
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
