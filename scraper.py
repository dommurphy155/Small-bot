import aiohttp
import asyncio
import logging
import re
from datetime import datetime, timedelta

HF_TOKEN = "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"  # replace with your token or use env

class MarketSentimentScraper:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.session = aiohttp.ClientSession()
        self.last_fetch = datetime.min

    async def fetch_latest_sentiment(self):
        # Throttle scraping: max once every 10s
        now = datetime.utcnow()
        if (now - self.last_fetch).total_seconds() < 10:
            return {}

        self.last_fetch = now

        # Scrape headlines from legit forex news sites (simple example)
        urls = [
            "https://www.forexfactory.com/news",
            "https://www.dailyfx.com/forex-news",
            # Add more reputable sources
        ]

        aggregated_text = ""
        for url in urls:
            try:
                async with self.session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        headlines = self.extract_headlines(html)
                        aggregated_text += " ".join(headlines) + " "
            except Exception as e:
                self.logger.error(f"Failed to scrape {url}: {e}")

        if not aggregated_text.strip():
            self.logger.warning("No headlines scraped.")
            return {}

        # Run sentiment analysis on combined headlines using Hugging Face API
        sentiment_scores = await self.analyze_sentiment(aggregated_text)
        return sentiment_scores

    def extract_headlines(self, html):
        # Simple regex-based extraction of headlines, tune per site layout
        # Example: <a class="news-link" href="...">Headline Text</a>
        pattern = re.compile(r'>([^<>]{20,100})<')
        matches = pattern.findall(html)
        headlines = [m.strip() for m in matches if len(m.strip()) > 20 and len(m.strip()) < 100]
        return headlines[:20]  # limit to top 20 headlines

    async def analyze_sentiment(self, text):
        url = "https://api-inference.huggingface.co/models/distilbert-base-uncased-finetuned-sst-2-english"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": text}
        async with self.session.post(url, json=payload, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                self.logger.error(f"Hugging Face API error: {resp.status}")
                return {}

            data = await resp.json()
            if not data or "error" in data:
                self.logger.error(f"Hugging Face returned error: {data}")
                return {}

            # Example parse, transform sentiment to currency signals (mock example)
            sentiment = {"EUR_USD": 0.7, "GBP_USD": 0.6, "USD_JPY": -0.3, "AUD_USD": 0.1, "USD_CAD": -0.5}
            return sentiment