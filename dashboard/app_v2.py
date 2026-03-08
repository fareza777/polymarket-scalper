"""
Dashboard Monitoring for Polymarket Scalper Bot - V2
With API endpoints for bot integration
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

from flask import Flask, render_template, jsonify, request
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


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stats')
def get_stats():
    return jsonify(bot_stats)


@app.route('/api/update', methods=['POST'])
def update_stats():
    """Receive stats update from bot"""
    global bot_stats
    try:
        data = request.get_json()
        bot_stats.update(data)
        bot_stats['last_update'] = datetime.now().isoformat()
        
        # Emit to all connected clients
        socketio.emit('stats_update', bot_stats)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Update error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/trade', methods=['POST'])
def add_trade():
    """Receive new trade from bot"""
    global trade_history, bot_stats
    try:
        data = request.get_json()
        trade_history.append(data)
        
        # Keep only last 100 trades
        if len(trade_history) > 100:
            trade_history = trade_history[-100:]
        
        bot_stats['trades_executed'] = len(trade_history)
        
        # Calculate win rate
        closed = [t for t in trade_history if t.get('pnl') is not None]
        if closed:
            wins = sum(1 for t in closed if t['pnl'] > 0)
            bot_stats['win_rate'] = (wins / len(closed)) * 100
        
        socketio.emit('new_trade', data)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Trade error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/signal', methods=['POST'])
def add_signal():
    """Receive new signal from bot"""
    global signals_history, bot_stats
    try:
        data = request.get_json()
        signals_history.append(data)
        
        # Keep only last 100 signals
        if len(signals_history) > 100:
            signals_history = signals_history[-100:]
        
        bot_stats['signals_generated'] = len(signals_history)
        
        socketio.emit('new_signal', data)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Signal error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


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
    emit('init', {
        'stats': bot_stats,
        'markets': market_data,
        'trades': trade_history[-10:],
        'signals': signals_history[-10:]
    })


@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5555))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
