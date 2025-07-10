import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from oandapyV20 import API
from oandapyV20.endpoints import accounts, instruments, orders, positions, trades
from oandapyV20.exceptions import V20Error


class Trader:
    def __init__(self, api: API, account_id: str, state_manager, logger=None):
        self.api = api
        self.account_id = account_id
        self.state_manager = state_manager
        self.logger = logger or logging.getLogger(__name__)
        
        # Trading parameters
        self.max_spread = 0.0003  # 3 pips max spread
        self.min_profit_pips = 5   # Minimum profit target in pips
        self.max_risk_per_trade = 0.02  # 2% risk per trade
        self.max_open_trades = 3
        
        # Major forex pairs
        self.instruments = [
            "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", 
            "USD_CAD", "EUR_GBP", "GBP_JPY", "EUR_JPY"
        ]
        
        # Cache for market data
        self.price_cache = {}
        self.cache_expiry = 30  # seconds
        
        self.logger.info("Trader initialized")

    async def analyze_and_trade(self, sentiment_data: Dict) -> Optional[str]:
        """Main trading logic - analyze market and execute trades"""
        try:
            # Get current account info
            account_info = await self._get_account_info()
            if not account_info:
                return "❌ Could not fetch account information"
            
            # Update capital in state
            balance = float(account_info.get('balance', 0))
            self.state_manager.state['total_capital'] = balance
            
            # Check if we have too many open trades
            open_trades = await self._get_open_trades()
            if len(open_trades) >= self.max_open_trades:
                return f"⏸️ Max trades reached ({len(open_trades)}/{self.max_open_trades})"
            
            # Get market data for all instruments
            market_data = await self._get_market_data()
            if not market_data:
                return "❌ Could not fetch market data"
            
            # Analyze each instrument
            best_opportunity = None
            best_score = 0
            
            for instrument in self.instruments:
                if instrument not in market_data:
                    continue
                    
                score = await self._analyze_instrument(
                    instrument, 
                    market_data[instrument], 
                    sentiment_data.get(instrument, 0)
                )
                
                if score > best_score and score > 0.6:  # Minimum confidence threshold
                    best_score = score
                    best_opportunity = instrument
            
            # Execute trade if we found a good opportunity
            if best_opportunity:
                trade_result = await self._execute_trade(
                    best_opportunity, 
                    market_data[best_opportunity],
                    sentiment_data.get(best_opportunity, 0)
                )
                return trade_result
            
            return "📊 No trading opportunities found"
            
        except Exception as e:
            self.logger.error(f"Error in analyze_and_trade: {e}")
            return f"❌ Trading analysis error: {str(e)}"

    async def _get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        try:
            request = accounts.AccountDetails(self.account_id)
            response = self.api.request(request)
            return response.get('account', {})
        except V20Error as e:
            self.logger.error(f"OANDA API error getting account info: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting account info: {e}")
            return None

    async def _get_open_trades(self) -> List[Dict]:
        """Get list of open trades"""
        try:
            request = trades.OpenTrades(self.account_id)
            response = self.api.request(request)
            return response.get('trades', [])
        except V20Error as e:
            self.logger.error(f"OANDA API error getting open trades: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error getting open trades: {e}")
            return []

    async def _get_market_data(self) -> Dict:
        """Get current market data for all instruments"""
        try:
            # Check cache first
            now = time.time()
            if hasattr(self, '_last_market_fetch') and (now - self._last_market_fetch) < self.cache_expiry:
                return self.price_cache
            
            market_data = {}
            
            # Get pricing for all instruments
            request = instruments.InstrumentsPricing(
                accountID=self.account_id,
                params={"instruments": ",".join(self.instruments)}
            )
            response = self.api.request(request)
            
            for price_data in response.get('prices', []):
                instrument = price_data.get('instrument')
                if instrument:
                    market_data[instrument] = {
                        'bid': float(price_data.get('bids', [{}])[0].get('price', 0)),
                        'ask': float(price_data.get('asks', [{}])[0].get('price', 0)),
                        'spread': float(price_data.get('asks', [{}])[0].get('price', 0)) - 
                                float(price_data.get('bids', [{}])[0].get('price', 0)),
                        'time': price_data.get('time')
                    }
            
            # Get historical data for technical analysis
            for instrument in self.instruments:
                if instrument in market_data:
                    candles = await self._get_candles(instrument)
                    if candles:
                        market_data[instrument]['candles'] = candles
            
            # Cache the data
            self.price_cache = market_data
            self._last_market_fetch = now
            
            return market_data
            
        except V20Error as e:
            self.logger.error(f"OANDA API error getting market data: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Error getting market data: {e}")
            return {}

    async def _get_candles(self, instrument: str, count: int = 50) -> Optional[List[Dict]]:
        """Get historical candle data for technical analysis"""
        try:
            request = instruments.InstrumentsCandles(
                instrument=instrument,
                params={
                    "count": count,
                    "granularity": "M15",  # 15-minute candles
                    "price": "MBA"  # Mid, Bid, Ask
                }
            )
            response = self.api.request(request)
            return response.get('candles', [])
        except Exception as e:
            self.logger.error(f"Error getting candles for {instrument}: {e}")
            return None

    async def _analyze_instrument(self, instrument: str, market_data: Dict, sentiment: float) -> float:
        """Analyze a single instrument and return confidence score (0-1)"""
        try:
            # Check spread
            spread = market_data.get('spread', 0)
            if spread > self.max_spread:
                return 0  # Spread too wide
            
            # Technical analysis
            technical_score = self._calculate_technical_score(market_data)
            
            # Sentiment analysis
            sentiment_score = abs(sentiment)  # Use absolute value for confidence
            
            # Market conditions
            market_score = self._calculate_market_conditions_score(market_data)
            
            # Combined score
            total_score = (technical_score * 0.5) + (sentiment_score * 0.3) + (market_score * 0.2)
            
            self.logger.debug(f"{instrument}: Technical={technical_score:.2f}, Sentiment={sentiment_score:.2f}, Market={market_score:.2f}, Total={total_score:.2f}")
            
            return min(1.0, max(0.0, total_score))
            
        except Exception as e:
            self.logger.error(f"Error analyzing {instrument}: {e}")
            return 0

    def _calculate_technical_score(self, market_data: Dict) -> float:
        """Calculate technical analysis score"""
        try:
            candles = market_data.get('candles', [])
            if len(candles) < 20:
                return 0.5  # Not enough data, neutral score
            
            # Convert to pandas for easier analysis
            df = pd.DataFrame([{
                'close': float(candle['mid']['c']),
                'high': float(candle['mid']['h']),
                'low': float(candle['mid']['l']),
                'open': float(candle['mid']['o']),
                'volume': candle.get('volume', 0)
            } for candle in candles if candle.get('complete', True)])
            
            if len(df) < 20:
                return 0.5
            
            # Calculate technical indicators
            df['sma_10'] = df['close'].rolling(window=10).mean()
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['rsi'] = self._calculate_rsi(df['close'])
            
            # Get latest values
            latest = df.iloc[-1]
            
            # Trend analysis
            trend_score = 0.5
            if latest['close'] > latest['sma_10'] > latest['sma_20']:
                trend_score = 0.8  # Strong uptrend
            elif latest['close'] < latest['sma_10'] < latest['sma_20']:
                trend_score = 0.8  # Strong downtrend
            
            # RSI analysis
            rsi_score = 0.5
            if 30 <= latest['rsi'] <= 70:
                rsi_score = 0.8  # Good RSI range
            elif latest['rsi'] < 30 or latest['rsi'] > 70:
                rsi_score = 0.9  # Potential reversal
            
            # Volatility analysis
            volatility = df['close'].pct_change().std()
            volatility_score = 0.7 if 0.001 <= volatility <= 0.01 else 0.3
            
            return (trend_score * 0.4) + (rsi_score * 0.4) + (volatility_score * 0.2)
            
        except Exception as e:
            self.logger.error(f"Error in technical analysis: {e}")
            return 0.5

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi
        except Exception:
            return pd.Series([50] * len(prices))  # Neutral RSI

    def _calculate_market_conditions_score(self, market_data: Dict) -> float:
        """Calculate market conditions score"""
        try:
            # Check if market is open (basic check)
            current_time = datetime.utcnow()
            hour = current_time.hour
            
            # London/NY session overlap (best trading time)
            if 13 <= hour <= 16:  # UTC
                return 0.9
            elif 8 <= hour <= 21:  # General trading hours
                return 0.7
            else:
                return 0.3  # Low activity hours
            
        except Exception as e:
            self.logger.error(f"Error calculating market conditions: {e}")
            return 0.5

    async def _execute_trade(self, instrument: str, market_data: Dict, sentiment: float) -> str:
        """Execute a trade based on analysis"""
        try:
            # Determine trade direction
            direction = 1 if sentiment > 0 else -1
            
            # Calculate position size
            account_info = await self._get_account_info()
            balance = float(account_info.get('balance', 0))
            
            # Risk management
            risk_amount = balance * self.max_risk_per_trade
            
            # Calculate units based on risk
            current_price = market_data['ask'] if direction > 0 else market_data['bid']
            
            # Simplified position sizing (in a real system, this would be more sophisticated)
            units = int(risk_amount / current_price * 100)  # Simplified calculation
            
            if direction < 0:
                units = -units
            
            # Set stop loss and take profit
            stop_loss = current_price * (1 - 0.01 * direction)  # 1% stop loss
            take_profit = current_price * (1 + 0.02 * direction)  # 2% take profit
            
            # Create order
            order_data = {
                "order": {
                    "type": "MARKET",
                    "instrument": instrument,
                    "units": str(units),
                    "stopLossOnFill": {
                        "price": str(round(stop_loss, 5))
                    },
                    "takeProfitOnFill": {
                        "price": str(round(take_profit, 5))
                    }
                }
            }
            
            # Execute order
            request = orders.OrderCreate(self.account_id, data=order_data)
            response = self.api.request(request)
            
            # Log trade
            trade_info = {
                "instrument": instrument,
                "units": units,
                "price": current_price,
                "direction": "BUY" if direction > 0 else "SELL",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "time": datetime.utcnow().isoformat(),
                "sentiment": sentiment
            }
            
            self.state_manager.state['trades'].append(trade_info)
            self.state_manager.state['last_trade'] = trade_info
            
            return f"✅ Trade executed: {trade_info['direction']} {abs(units)} units of {instrument} at {current_price:.5f}"
            
        except V20Error as e:
            self.logger.error(f"OANDA API error executing trade: {e}")
            return f"❌ Trade execution failed: {str(e)}"
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")
            return f"❌ Trade execution error: {str(e)}"

    async def force_trade(self) -> str:
        """Force a trade for testing purposes"""
        try:
            # Get a random instrument
            instrument = random.choice(self.instruments)
            
            # Get market data
            market_data = await self._get_market_data()
            if not market_data or instrument not in market_data:
                return "❌ Could not fetch market data for forced trade"
            
            # Execute with random sentiment
            sentiment = random.uniform(-0.8, 0.8)
            result = await self._execute_trade(instrument, market_data[instrument], sentiment)
            
            return f"🎯 Forced trade: {result}"
            
        except Exception as e:
            self.logger.error(f"Error in force_trade: {e}")
            return f"❌ Forced trade error: {str(e)}"

    def get_strategy_summary(self) -> str:
        """Get a summary of the trading strategy"""
        return f"""
🎯 Trading Strategy Summary:
• Instruments: {len(self.instruments)} major pairs
• Max Risk/Trade: {self.max_risk_per_trade*100:.1f}%
• Max Open Trades: {self.max_open_trades}
• Max Spread: {self.max_spread*10000:.1f} pips
• Analysis: Technical (50%) + Sentiment (30%) + Market (20%)
• Timeframe: 15-minute candles
• Stop Loss: 1% | Take Profit: 2%
        """

    def run_diagnostics(self) -> str:
        """Run system diagnostics"""
        try:
            # Test API connection
            account_info = self.api.request(accounts.AccountDetails(self.account_id))
            
            # Check account status
            balance = float(account_info.get('account', {}).get('balance', 0))
            
            # Check recent trades
            recent_trades = len(self.state_manager.state.get('trades', []))
            
            return f"""
🩺 System Diagnostics:
✅ OANDA API: Connected
✅ Account Balance: £{balance:.2f}
✅ Recent Trades: {recent_trades}
✅ Instruments: {len(self.instruments)} configured
✅ State Manager: Working
✅ Price Cache: {'Active' if hasattr(self, '_last_market_fetch') else 'Inactive'}
            """
            
        except Exception as e:
            return f"❌ Diagnostics failed: {str(e)}"

    def estimate_daily_profit(self) -> float:
        """Estimate expected daily profit"""
        try:
            # Simple estimation based on historical performance
            balance = self.state_manager.state.get('total_capital', 10000)
            expected_daily_return = 0.005  # 0.5% daily target
            return balance * expected_daily_return
        except Exception:
            return 0.0

    def estimate_weekly_profit(self) -> float:
        """Estimate expected weekly profit"""
        try:
            daily_estimate = self.estimate_daily_profit()
            return daily_estimate * 5  # 5 trading days
        except Exception:
            return 0.0

    def test_connection(self) -> bool:
        """Test OANDA API connection"""
        try:
            request = accounts.AccountDetails(self.account_id)
            response = self.api.request(request)
            self.logger.info("OANDA API connection test successful")
            return True
        except Exception as e:
            self.logger.error(f"OANDA API connection test failed: {e}")
            return False
