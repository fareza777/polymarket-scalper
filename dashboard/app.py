"""
Dashboard Monitoring for Polymarket Scalper Bot
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'polymarket-scalper-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
bot_stats = {
    "status": "stopped",
    "runtime": "00:00:00",
    "signals_generated": 0,
    "trades_executed": 0,
    "open_positions": 0,
    "open_pnl": 0.0,
    "daily_pnl": 0.0,
    "total_volume": 0.0,
    "win_rate": 0.0,
    "avg_trade_pnl": 0.0,
    "markets_monitored": 0,
    "last_update": None
}

market_data: Dict[str, dict] = {}
trade_history: List[dict] = []
signals_history: List[dict] = []

# Mock data generator for demo
class MockDataGenerator:
    def __init__(self):
        self.running = False
        self.markets = [
            "BTC-100K-DEC", "ETH-5K-JAN", "SOL-200-DEC",
            "BTC-90K-NOV", "ETH-4K-DEC", "Crypto-Market-1"
        ]
        self.prices = {m: 0.5 for m in self.markets}
    
    def start(self):
        self.running = True
        thread = threading.Thread(target=self._generate)
        thread.daemon = True
        thread.start()
    
    def _generate(self):
        import random
        import time
        
        while self.running:
            time.sleep(2)
            
            # Update prices
            for market in self.markets:
                change = random.uniform(-0.02, 0.02)
                self.prices[market] = max(0.01, min(0.99, self.prices[market] + change))
                
                market_data[market] = {
                    "price": self.prices[market],
                    "bid": self.prices[market] - 0.005,
                    "ask": self.prices[market] + 0.005,
                    "spread": 1.0,
                    "volume": random.uniform(1000, 50000),
                    "last_update": datetime.now().isoformat()
                }
            
            # Random signal
            if random.random() < 0.3:
                market = random.choice(self.markets)
                signal = {
                    "asset_id": market,
                    "side": random.choice(["buy", "sell"]),
                    "spread_pct": random.uniform(1.0, 3.5),
                    "confidence": random.uniform(0.5, 0.95),
                    "timestamp": datetime.now().isoformat()
                }
                signals_history.append(signal)
                bot_stats["signals_generated"] += 1
                
                # Random trade
                if random.random() < 0.5:
                    trade = {
                        "asset_id": market,
                        "side": signal["side"],
                        "price": self.prices[market],
                        "size": 5.0,
                        "pnl": random.uniform(-2, 5),
                        "timestamp": datetime.now().isoformat()
                    }
                    trade_history.append(trade)
                    bot_stats["trades_executed"] += 1
                    bot_stats["daily_pnl"] += trade["pnl"]
                    bot_stats["total_volume"] += trade["size"]
            
            # Update stats
            bot_stats["markets_monitored"] = len(self.markets)
            bot_stats["last_update"] = datetime.now().isoformat()
            bot_stats["open_positions"] = min(3, len(trade_history) % 4)
            bot_stats["open_pnl"] = sum(t.get("pnl", 0) for t in trade_history[-5:])
            
            # Calculate win rate
            if trade_history:
                wins = sum(1 for t in trade_history if t.get("pnl", 0) > 0)
                bot_stats["win_rate"] = (wins / len(trade_history)) * 100
                bot_stats["avg_trade_pnl"] = sum(t.get("pnl", 0) for t in trade_history) / len(trade_history)
            
            # Emit update
            socketio.emit('update', {
                'stats': bot_stats,
                'markets': market_data,
                'trades': trade_history[-10:],
                'signals': signals_history[-10:]
            })

mock_generator = MockDataGenerator()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    return jsonify(bot_stats)

@app.route('/api/markets')
def get_markets():
    return jsonify(market_data)

@app.route('/api/trades')
def get_trades():
    return jsonify(trade_history[-50:])

@app.route('/api/signals')
def get_signals():
    return jsonify(signals_history[-50:])

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')
    emit('update', {
        'stats': bot_stats,
        'markets': market_data,
        'trades': trade_history[-10:],
        'signals': signals_history[-10:]
    })

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

@socketio.on('start_bot')
def handle_start_bot():
    bot_stats["status"] = "running"
    mock_generator.start()
    emit('bot_status', {'status': 'running'})

@socketio.on('stop_bot')
def handle_stop_bot():
    bot_stats["status"] = "stopped"
    mock_generator.running = False
    emit('bot_status', {'status': 'stopped'})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5555))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
