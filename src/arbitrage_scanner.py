"""
Polymarket Arbitrage Scanner
Detects mispricing and arbitrage opportunities
"""
import asyncio
import logging
import signal
import sys
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/arbitrage_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)

from polymarket_gamma_api import PolymarketGammaAPI


@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity data"""
    type: str  # 'single_market', 'cross_market', 'time'
    description: str
    markets: List[Dict]
    investment: float
    profit: float
    profit_pct: float
    risk: str  # 'risk_free', 'low', 'medium'
    confidence: float


class ArbitrageScanner:
    """Scan for arbitrage opportunities in Polymarket"""
    
    def __init__(self):
        self.api = PolymarketGammaAPI()
        self.running = False
        self.markets = []
        self.opportunities = []
        self.scan_count = 0
    
    async def start(self):
        """Start arbitrage scanner"""
        logger.info("=" * 70)
        logger.info("POLYMARKET ARBITRAGE SCANNER")
        logger.info("=" * 70)
        
        self.running = True
        await self.api.start()
        
        logger.info("Fetching markets...")
        self.markets = await self.api.get_all_markets(limit=200)
        logger.info(f"Loaded {len(self.markets)} markets")
        
        # Build market groups by event
        self.event_groups = self._group_by_event()
        logger.info(f"Found {len(self.event_groups)} event groups")
        
        while self.running:
            try:
                self.scan_count += 1
                logger.info(f"\n{'='*70}")
                logger.info(f"SCAN #{self.scan_count}")
                logger.info(f"{'='*70}")
                
                # Refresh markets
                self.markets = await self.api.get_all_markets(limit=200)
                self.event_groups = self._group_by_event()
                
                # Scan for arbitrage
                opportunities = []
                
                # 1. Single market mispricing
                opps = await self._scan_single_market()
                opportunities.extend(opps)
                
                # 2. Cross-market correlation
                opps = await self._scan_cross_market()
                opportunities.extend(opps)
                
                # 3. Time arbitrage
                opps = await self._scan_time_arbitrage()
                opportunities.extend(opps)
                
                # Display results
                if opportunities:
                    logger.info(f"\n[FOUND {len(opportunities)} ARBITRAGE OPPORTUNITIES]")
                    for i, opp in enumerate(opportunities[:5], 1):
                        self._display_opportunity(i, opp)
                else:
                    logger.info("\n[NO ARB] No arbitrage opportunities found")
                
                # Wait before next scan
                await asyncio.sleep(30)  # Scan every 30 seconds
                
            except Exception as e:
                logger.error(f"Scan error: {e}")
                await asyncio.sleep(10)
    
    def _group_by_event(self) -> Dict[str, List[Dict]]:
        """Group markets by event/slug"""
        groups = {}
        for market in self.markets:
            # Try to extract event name from slug or question
            slug = market.get('slug', '')
            question = market.get('question', '')
            
            # Use slug if available, otherwise use first 50 chars of question
            event_key = slug if slug else question[:50]
            
            if event_key not in groups:
                groups[event_key] = []
            groups[event_key].append(market)
        
        return groups
    
    async def _scan_single_market(self) -> List[ArbitrageOpportunity]:
        """Scan for single market mispricing (outcomes sum != $1)"""
        opportunities = []
        
        for event_key, markets in self.event_groups.items():
            if len(markets) < 2:
                continue
            
            # Calculate total price of all outcomes
            total_price = 0.0
            valid_markets = []
            
            for market in markets:
                best_bid = market.get('bestBid', 0) or 0
                best_ask = market.get('bestAsk', 0) or 0
                
                if best_bid > 0 and best_ask > 0:
                    # Use ask price for buying
                    total_price += best_ask
                    valid_markets.append(market)
            
            # Check if total < $1 (arbitrage opportunity)
            if total_price > 0 and total_price < 0.99 and len(valid_markets) >= 2:
                profit = 1.0 - total_price
                profit_pct = (profit / total_price) * 100
                
                opp = ArbitrageOpportunity(
                    type='single_market',
                    description=f"Buy all outcomes in '{event_key[:50]}...'",
                    markets=valid_markets,
                    investment=total_price,
                    profit=profit,
                    profit_pct=profit_pct,
                    risk='risk_free',
                    confidence=0.95
                )
                opportunities.append(opp)
        
        return opportunities
    
    async def _scan_cross_market(self) -> List[ArbitrageOpportunity]:
        """Scan for cross-market correlation arbitrage"""
        opportunities = []
        
        # Look for markets with similar keywords but different prices
        keywords = ['trump', 'biden', 'fed', 'bitcoin', 'btc', 'election']
        
        for keyword in keywords:
            related_markets = []
            
            for market in self.markets:
                question = market.get('question', '').lower()
                if keyword in question:
                    best_bid = market.get('bestBid', 0) or 0
                    best_ask = market.get('bestAsk', 0) or 0
                    
                    if best_bid > 0 and best_ask > 0:
                        related_markets.append({
                            'market': market,
                            'bid': best_bid,
                            'ask': best_ask,
                            'question': question
                        })
            
            # Sort by price
            related_markets.sort(key=lambda x: x['ask'])
            
            # Look for price inversions
            for i in range(len(related_markets) - 1):
                market_a = related_markets[i]
                market_b = related_markets[i + 1]
                
                # Check if logic is violated
                # Example: "BTC > $100k" should be cheaper than "BTC > $90k"
                if self._is_logic_violation(market_a, market_b):
                    profit = abs(market_b['ask'] - market_a['bid'])
                    
                    if profit > 0.02:  # Minimum 2% profit
                        opp = ArbitrageOpportunity(
                            type='cross_market',
                            description=f"Price inversion: {market_a['question'][:40]} vs {market_b['question'][:40]}",
                            markets=[market_a['market'], market_b['market']],
                            investment=max(market_a['ask'], market_b['ask']),
                            profit=profit,
                            profit_pct=(profit / max(market_a['ask'], market_b['ask'])) * 100,
                            risk='low',
                            confidence=0.85
                        )
                        opportunities.append(opp)
        
        return opportunities
    
    def _is_logic_violation(self, market_a: Dict, market_b: Dict) -> bool:
        """Check if there's a logic violation between two markets"""
        q_a = market_a['question'].lower()
        q_b = market_b['question'].lower()
        
        # Example: BTC > $100k should have lower price than BTC > $90k
        if 'btc' in q_a and 'btc' in q_b:
            threshold_a = self._extract_threshold(q_a)
            threshold_b = self._extract_threshold(q_b)
            
            if threshold_a and threshold_b:
                # Higher threshold should have lower price
                if threshold_a > threshold_b and market_a['ask'] > market_b['ask']:
                    return True
        
        return False
    
    def _extract_threshold(self, question: str) -> Optional[float]:
        """Extract price threshold from question"""
        import re
        # Look for patterns like $100k, $90,000, etc.
        matches = re.findall(r'\$([\d,]+)(k?)', question)
        if matches:
            num_str, k_suffix = matches[0]
            num = float(num_str.replace(',', ''))
            if k_suffix:
                num *= 1000
            return num
        return None
    
    async def _scan_time_arbitrage(self) -> List[ArbitrageOpportunity]:
        """Scan for time-based arbitrage (same event, different expiry)"""
        opportunities = []
        
        # Group by event type
        time_keywords = ['march', 'april', 'june', '2026', '2025', 'q1', 'q2']
        
        for keyword in time_keywords:
            time_markets = []
            
            for market in self.markets:
                question = market.get('question', '').lower()
                if keyword in question:
                    best_bid = market.get('bestBid', 0) or 0
                    best_ask = market.get('bestAsk', 0) or 0
                    
                    if best_bid > 0 and best_ask > 0:
                        time_markets.append({
                            'market': market,
                            'bid': best_bid,
                            'ask': best_ask,
                            'question': question,
                            'time': keyword
                        })
            
            # Sort by time (shorter time should have higher price for same event)
            if len(time_markets) >= 2:
                time_markets.sort(key=lambda x: x['ask'], reverse=True)
                
                # Check for opportunities
                for i in range(len(time_markets) - 1):
                    short_term = time_markets[i]  # e.g., March
                    long_term = time_markets[i + 1]  # e.g., Q1
                    
                    # If short-term is cheaper than long-term, it's wrong
                    if short_term['ask'] < long_term['bid']:
                        profit = long_term['bid'] - short_term['ask']
                        
                        if profit > 0.02:
                            opp = ArbitrageOpportunity(
                                type='time',
                                description=f"Time arb: {short_term['time']} vs {long_term['time']}",
                                markets=[short_term['market'], long_term['market']],
                                investment=short_term['ask'],
                                profit=profit,
                                profit_pct=(profit / short_term['ask']) * 100,
                                risk='medium',
                                confidence=0.80
                            )
                            opportunities.append(opp)
        
        return opportunities
    
    def _display_opportunity(self, index: int, opp: ArbitrageOpportunity):
        """Display arbitrage opportunity"""
        logger.info(f"\n{'='*70}")
        logger.info(f"[OPPORTUNITY #{index}]: {opp.type.upper()}")
        logger.info(f"{'='*70}")
        logger.info(f"Description: {opp.description}")
        logger.info(f"Risk Level: {opp.risk.upper()}")
        logger.info(f"Confidence: {opp.confidence*100:.0f}%")
        logger.info(f"Investment: ${opp.investment:.4f}")
        logger.info(f"Profit: ${opp.profit:.4f} ({opp.profit_pct:.2f}%)")
        logger.info(f"ROI: {opp.profit_pct:.2f}%")
        
        logger.info(f"\nMarkets:")
        for market in opp.markets:
            q = market.get('question', 'N/A')[:60]
            bid = market.get('bestBid', 0) or 0
            ask = market.get('bestAsk', 0) or 0
            logger.info(f"  - {q}...")
            logger.info(f"    Bid: ${bid:.4f} | Ask: ${ask:.4f}")
    
    async def stop(self):
        """Stop scanner"""
        self.running = False
        await self.api.stop()
        logger.info("Scanner stopped")


async def main():
    scanner = ArbitrageScanner()
    
    def handler(s, f):
        asyncio.create_task(scanner.stop())
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    
    try:
        await scanner.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await scanner.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
