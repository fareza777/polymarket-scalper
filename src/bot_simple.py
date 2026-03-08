"""
Polymarket Scalper Bot - Simple Working Version
"""
import asyncio
import logging
import signal
import sys
import os
import random
from datetime import datetime

# Setup logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)


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
        # Generate orderbook with spread
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
            return False
        
        size = trade_size / signal.entry_price
        self.positions[signal.asset_id] = {
            "entry": signal.entry_price,
            "size": size,
            "side": "buy",
            "time": datetime.now()
        }
        
        logger.info(f"TRADE: Buy {signal.asset_id} @ {signal.entry_price:.4f}")
        return True
    
    async def update_positions(self, api):
        for asset_id, pos in list(self.positions.items()):
            ob = await api.get_orderbook(asset_id)
            if ob and ob["asks"]:
                current = ob["asks"][0]["price"]
                pos["pnl"] = (current - pos["entry"]) * pos["size"]
    
    async def check_exits(self):
        for asset_id, pos in list(self.positions.items()):
            pnl = pos.get("pnl", 0)
            
            if pnl > 0.5 or pnl < -1.0:
                self.daily_pnl += pnl
                self.trades.append({"asset": asset_id, "pnl": pnl})
                del self.positions[asset_id]
                logger.info(f"CLOSE: {asset_id} P&L: ${pnl:.2f}")
    
    def get_stats(self):
        return {
            "open": len(self.positions),
            "trades": len(self.trades),
            "daily_pnl": self.daily_pnl,
            "open_pnl": sum(p.get("pnl", 0) for p in self.positions.values())
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
        self.running = False
        self.signals = 0
    
    async def start(self):
        logger.info("=" * 60)
        logger.info("BOT STARTING - Paper Trading Mode")
        logger.info("=" * 60)
        
        self.running = True
        await self.api.start()
        
        markets = await self.api.get_crypto_markets()
        logger.info(f"Markets: {len(markets)}")
        for m in markets:
            logger.info(f"  - {m['name']}")
        
        while self.running:
            try:
                self.api.update_prices()
                await self.scan()
                await self.trader.update_positions(self.api)
                await self.trader.check_exits()
                
                if random.randint(1, 12) == 1:  # Every ~1 min
                    self.print_stats()
                
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(5)
    
    async def scan(self):
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
                await self.trader.execute_signal(signal)
    
    def print_stats(self):
        stats = self.trader.get_stats()
        logger.info("-" * 60)
        logger.info(f"Signals: {self.signals} | Trades: {stats['trades']} | Open: {stats['open']}")
        logger.info(f"Daily P&L: ${stats['daily_pnl']:.2f} | Open P&L: ${stats['open_pnl']:.2f}")
        logger.info("-" * 60)
    
    async def stop(self):
        self.running = False
        await self.api.stop()
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
