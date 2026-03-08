"""
Configuration for Polymarket Scalper Bot
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Bot configuration"""
    
    # Polymarket API
    POLYMARKET_API_KEY: str = os.getenv("POLYMARKET_API_KEY", "")
    POLYMARKET_SECRET: str = os.getenv("POLYMARKET_SECRET", "")
    POLYMARKET_PASSPHRASE: str = os.getenv("POLYMARKET_PASSPHRASE", "")
    
    # WebSocket
    WS_URL: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    WS_HEARTBEAT_INTERVAL: int = 10  # seconds
    WS_RECONNECT_DELAY: int = 5  # seconds
    
    # Trading
    TRADE_SIZE_USD: float = 5.0
    MIN_SPREAD_PCT: float = 1.0  # Minimum 1% spread
    MIN_LIQUIDITY: float = 1000.0  # Minimum $1000 liquidity
    
    # Risk Management
    MAX_POSITIONS: int = 3
    MAX_LOSS_PER_POSITION: float = 2.0
    DAILY_LOSS_LIMIT: float = 20.0
    TRADE_COOLDOWN_SECONDS: int = 30
    
    # Markets to monitor (crypto-related)
    CRYPTO_MARKETS: list = None
    
    # Mode
    PAPER_TRADING: bool = os.getenv("PAPER_TRADING", "true").lower() == "true"
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    def __post_init__(self):
        if self.CRYPTO_MARKETS is None:
            # Default crypto markets (condition IDs)
            # These are examples - need to be updated with actual market IDs
            self.CRYPTO_MARKETS = [
                "0x1234...",  # BTC price market
                "0x5678...",  # ETH price market
            ]


# Global config instance
config = Config()
