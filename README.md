# Polymarket Scalper Bot

Bot scalping spread real-time untuk Polymarket menggunakan Antfarm multi-agent workflow.

## Fitur
- WebSocket real-time ke Polymarket
- Scalping spread detection
- Auto-trading dengan risk management
- Multi-market monitoring

## Arsitektur

```
WebSocket Polymarket → Data Aggregator → Spread Detector → Trade Executor
```

## Agents
1. **Connector** - Setup WebSocket connection
2. **DataAggregator** - Aggregate orderbook data
3. **SpreadDetector** - Detect arbitrage opportunities
4. **TradeExecutor** - Execute trades
5. **RiskManager** - Monitor risk & P&L
6. **Monitor** - Dashboard & alerts

## Quick Start

```bash
antfarm workflow run polymarket-scalper "Start scalping bot"
```
