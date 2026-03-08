"""
WebSocket Client for Polymarket CLOB API
"""
import asyncio
import json
import logging
from typing import Callable, Optional
from dataclasses import dataclass
import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


@dataclass
class WSConfig:
    url: str
    heartbeat_interval: int = 10
    reconnect_delay: int = 5


class PolymarketWebSocket:
    """WebSocket client for Polymarket market data"""
    
    def __init__(
        self,
        config: WSConfig,
        on_book: Optional[Callable] = None,
        on_price_change: Optional[Callable] = None,
        on_last_trade: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        self.config = config
        self.ws = None
        self.running = False
        self.subscribed_assets = set()
        
        # Callbacks
        self.on_book = on_book
        self.on_price_change = on_price_change
        self.on_last_trade = on_last_trade
        self.on_error = on_error
        
        # Tasks
        self.heartbeat_task = None
        self.receive_task = None
    
    async def connect(self):
        """Connect to WebSocket"""
        try:
            logger.info(f"Connecting to {self.config.url}")
            self.ws = await websockets.connect(self.config.url)
            self.running = True
            
            # Start tasks
            self.heartbeat_task = asyncio.create_task(self._heartbeat())
            self.receive_task = asyncio.create_task(self._receive())
            
            logger.info("WebSocket connected")
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            if self.on_error:
                await self.on_error(e)
            return False
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        self.running = False
        
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.receive_task:
            self.receive_task.cancel()
        
        if self.ws:
            await self.ws.close()
        
        logger.info("WebSocket disconnected")
    
    async def subscribe(self, asset_ids: list, custom_features: bool = True):
        """Subscribe to market data"""
        if not self.ws:
            logger.error("WebSocket not connected")
            return
        
        message = {
            "assets_ids": asset_ids,
            "type": "market",
            "custom_feature_enabled": custom_features
        }
        
        await self.ws.send(json.dumps(message))
        self.subscribed_assets.update(asset_ids)
        logger.info(f"Subscribed to {len(asset_ids)} assets")
    
    async def unsubscribe(self, asset_ids: list):
        """Unsubscribe from assets"""
        if not self.ws:
            return
        
        message = {
            "assets_ids": asset_ids,
            "operation": "unsubscribe"
        }
        
        await self.ws.send(json.dumps(message))
        self.subscribed_assets.difference_update(asset_ids)
        logger.info(f"Unsubscribed from {len(asset_ids)} assets")
    
    async def _heartbeat(self):
        """Send PING every 10 seconds"""
        while self.running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                if self.ws:
                    await self.ws.send("PING")
                    logger.debug("Heartbeat sent")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
    
    async def _receive(self):
        """Receive and process messages"""
        while self.running:
            try:
                if not self.ws:
                    await asyncio.sleep(1)
                    continue
                
                message = await self.ws.recv()
                await self._handle_message(message)
                
            except ConnectionClosed:
                logger.warning("Connection closed, reconnecting...")
                await self._reconnect()
            except Exception as e:
                logger.error(f"Receive error: {e}")
                if self.on_error:
                    await self.on_error(e)
    
    async def _handle_message(self, message):
        """Handle incoming message"""
        try:
            # Handle PONG
            if message == "PONG":
                logger.debug("Heartbeat received")
                return
            
            # Parse JSON
            data = json.loads(message)
            event_type = data.get("event_type")
            
            if event_type == "book" and self.on_book:
                await self.on_book(data)
            elif event_type == "price_change" and self.on_price_change:
                await self.on_price_change(data)
            elif event_type == "last_trade_price" and self.on_last_trade:
                await self.on_last_trade(data)
            else:
                logger.debug(f"Unknown event type: {event_type}")
                
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON message: {message}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    async def _reconnect(self):
        """Reconnect with delay"""
        await self.disconnect()
        await asyncio.sleep(self.config.reconnect_delay)
        
        # Reconnect and resubscribe
        if await self.connect():
            if self.subscribed_assets:
                await self.subscribe(list(self.subscribed_assets))
