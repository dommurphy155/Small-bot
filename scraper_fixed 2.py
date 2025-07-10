import aiohttp
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import json


class MarketSentimentScraper:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.session = None
        self.last_fetch = datetime.min
        self.hf_token = os.getenv("HF_TOKEN")
        self.cached_sentiment = {}
        self.cache_duration = 300  # 5 minutes cache

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            )
        return self.session

    async def fetch_latest_sentiment(self):
        """Fetch and analyze market sentiment from various sources"""
        # Throttle scraping: max once every 60 seconds
        now = datetime.utcnow()
        if (now - self.last_fetch).total_seconds() < 60:
            return self.cached_sentiment

        self.last_fetch = now

        try:
            session = await self._get_session()
            
            # Define news sources with their specific selectors
            sources = [
                {
                    'url': 'https://www.forexfactory.com/news',
                    'selector': '.calendar__cell--event'
                },
                {
                    'url': 'https://www.dailyfx.com/forex-news',
                    'selector': '.dfx-articleTitle'
                },
                {
                    'url': 'https://www.investing.com/news/forex-news',
                    'selector': '.articleItem'
                }
            ]

            all_headlines = []
            
            for source in sources:
                try:
                    headlines = await self._scrape_source(session, source)
                    all_headlines.extend(headlines)
                    await asyncio.sleep(1)  # Be respectful to servers
                except Exception as e:
                    self.logger.warning(f"Failed to scrape {source['url']}: {e}")

            if not all_headlines:
                self.logger.warning("No headlines scraped from any source")
                return self._get_default_sentiment()

            # Analyze sentiment
            sentiment_scores = await self._analyze_sentiment(" ".join(all_headlines))
            
            # Cache the results
            self.cached_sentiment = sentiment_scores
            
            self.logger.info(f"Successfully analyzed sentiment from {len(all_headlines)} headlines")
            return sentiment_scores

        except Exception as e:
            self.logger.error(f"Error in fetch_latest_sentiment: {e}")
            return self._get_default_sentiment()

    async def _scrape_source(self, session, source):
        """Scrape headlines from a specific source"""
        try:
            async with session.get(source['url']) as response:
                if response.status != 200:
                    self.logger.warning(f"HTTP {response.status} for {source['url']}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'lxml')
                
                # Extract headlines using basic text extraction
                headlines = []
                
                # Try multiple common headline selectors
                selectors = [
                    'h1', 'h2', 'h3', 'h4',
                    '.headline', '.title', '.news-title',
                    '[class*="headline"]', '[class*="title"]'
                ]
                
                for selector in selectors:
                    elements = soup.select(selector)
                    for element in elements:
                        text = element.get_text(strip=True)
                        if self._is_valid_headline(text):
                            headlines.append(text)
                    
                    if headlines:  # Stop if we found headlines
                        break
                
                return headlines[:10]  # Limit to 10 headlines per source
                
        except Exception as e:
            self.logger.error(f"Error scraping {source['url']}: {e}")
            return []

    def _is_valid_headline(self, text):
        """Check if text is a valid headline"""
        if not text or len(text) < 10 or len(text) > 200:
            return False
        
        # Filter out common non-headline text
        invalid_patterns = [
            r'^\s*$',
            r'^[0-9]+$',
            r'^(click|read|more|see|view|watch)',
            r'(cookie|privacy|terms|conditions)',
            r'^(home|about|contact|subscribe)'
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False
        
        return True

    async def _analyze_sentiment(self, text):
        """Analyze sentiment using Hugging Face API or fallback to keyword analysis"""
        if not text.strip():
            return self._get_default_sentiment()

        # Try Hugging Face API first
        if self.hf_token:
            try:
                sentiment = await self._analyze_with_hf(text)
                if sentiment:
                    return sentiment
            except Exception as e:
                self.logger.warning(f"Hugging Face API failed: {e}")

        # Fallback to keyword-based sentiment analysis
        return self._analyze_with_keywords(text)

    async def _analyze_with_hf(self, text):
        """Analyze sentiment using Hugging Face API"""
        url = "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest"
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        
        # Truncate text to avoid API limits
        text = text[:500]
        payload = {"inputs": text}

        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 503:
                    self.logger.info("Hugging Face model loading, using fallback")
                    return None
                
                if response.status != 200:
                    self.logger.error(f"Hugging Face API error: {response.status}")
                    return None

                data = await response.json()
                
                if isinstance(data, list) and len(data) > 0:
                    scores = data[0]
                    return self._convert_hf_sentiment_to_forex(scores)
                else:
                    self.logger.warning("Unexpected Hugging Face response format")
                    return None

        except Exception as e:
            self.logger.error(f"Hugging Face API call failed: {e}")
            return None

    def _convert_hf_sentiment_to_forex(self, scores):
        """Convert Hugging Face sentiment scores to forex signals"""
        # Extract sentiment scores
        sentiment_map = {}
        for score in scores:
            sentiment_map[score['label']] = score['score']
        
        # Calculate overall sentiment (-1 to +1)
        positive = sentiment_map.get('LABEL_2', 0)  # Positive
        negative = sentiment_map.get('LABEL_0', 0)  # Negative
        neutral = sentiment_map.get('LABEL_1', 0)   # Neutral
        
        overall_sentiment = positive - negative
        
        # Convert to forex pair signals
        base_strength = overall_sentiment * 0.5  # Scale down
        
        return {
            "EUR_USD": base_strength + 0.1,
            "GBP_USD": base_strength + 0.05,
            "USD_JPY": -base_strength + 0.1,
            "AUD_USD": base_strength * 0.8,
            "USD_CAD": -base_strength * 0.6,
            "EUR_GBP": base_strength * 0.3,
            "GBP_JPY": base_strength * 0.7,
            "overall_sentiment": overall_sentiment
        }

    def _analyze_with_keywords(self, text):
        """Fallback keyword-based sentiment analysis"""
        text_lower = text.lower()
        
        # Define keyword categories
        bullish_keywords = [
            'bullish', 'rise', 'surge', 'gain', 'strong', 'positive',
            'growth', 'increase', 'higher', 'rally', 'boost', 'optimistic'
        ]
        
        bearish_keywords = [
            'bearish', 'fall', 'drop', 'decline', 'weak', 'negative',
            'recession', 'decrease', 'lower', 'crash', 'concern', 'pessimistic'
        ]
        
        # Count keyword occurrences
        bullish_count = sum(1 for keyword in bullish_keywords if keyword in text_lower)
        bearish_count = sum(1 for keyword in bearish_keywords if keyword in text_lower)
        
        # Calculate sentiment score
        total_words = len(text.split())
        if total_words == 0:
            return self._get_default_sentiment()
        
        bullish_ratio = bullish_count / total_words
        bearish_ratio = bearish_count / total_words
        
        sentiment_score = (bullish_ratio - bearish_ratio) * 10  # Scale up
        sentiment_score = max(-1, min(1, sentiment_score))  # Clamp to [-1, 1]
        
        self.logger.info(f"Keyword sentiment: {sentiment_score:.2f} (bullish: {bullish_count}, bearish: {bearish_count})")
        
        # Convert to forex signals
        return {
            "EUR_USD": sentiment_score * 0.3,
            "GBP_USD": sentiment_score * 0.25,
            "USD_JPY": -sentiment_score * 0.4,
            "AUD_USD": sentiment_score * 0.2,
            "USD_CAD": -sentiment_score * 0.3,
            "EUR_GBP": sentiment_score * 0.15,
            "GBP_JPY": sentiment_score * 0.35,
            "overall_sentiment": sentiment_score
        }

    def _get_default_sentiment(self):
        """Return neutral sentiment as fallback"""
        return {
            "EUR_USD": 0.0,
            "GBP_USD": 0.0,
            "USD_JPY": 0.0,
            "AUD_USD": 0.0,
            "USD_CAD": 0.0,
            "EUR_GBP": 0.0,
            "GBP_JPY": 0.0,
            "overall_sentiment": 0.0
        }

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()

    def __del__(self):
        """Cleanup on destruction"""
        if hasattr(self, 'session') and self.session and not self.session.closed:
            try:
                asyncio.create_task(self.session.close())
            except:
                pass