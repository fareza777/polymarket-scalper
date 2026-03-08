# Dashboard Monitoring

Dashboard real-time untuk Polymarket Scalper Bot.

## Fitur

- 📊 Real-time P&L tracking
- 📈 Charts (P&L over time, trade volume)
- 📋 Recent trades & signals
- 🎮 Start/Stop bot controls
- 🔄 Auto-refresh via WebSocket

## Cara Menjalankan

```bash
# Install dependencies
pip install -r requirements.txt

# Jalankan dashboard (default port 5555)
python app.py

# Atau pilih port lain
set PORT=5556
python app.py

# Buka browser
http://localhost:5555
```

## Screenshot

Dashboard menampilkan:
- Daily P&L
- Open P&L
- Win Rate
- Open Positions
- Trade history
- Signal history
- Real-time charts
