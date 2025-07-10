import aiohttp
import asyncio
import logging
import os
import re
from datetime import datetime

class MarketSentimentScraper:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.session = aiohttp.ClientSession()
        self.last_fetch = datetime.min
        self.hf_token = os.getenv("HF_TOKEN")  # Load from env securely

    async def fetch_latest_sentiment(self):
        # Throttle scraping: max once every 10s
        now = datetime.utcnow()
        if (now - self.last_fetch).total_seconds() < 10:
            return {}

        self.last_fetch = now

        urls = [
            "https://www.forexfactory.com/news",
            "https://www.dailyfx.com/forex-news",
            # Add more high-quality sources as needed
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

        sentiment_scores = await self.analyze_sentiment(aggregated_text)
        return sentiment_scores

    def extract_headlines(self, html):
        pattern = re.compile(r'>([^<>]{20,100})<')
        matches = pattern.findall(html)
        headlines = [m.strip() for m in matches if 20 < len(m.strip()) < 100]
        return headlines[:20]

    async def analyze_sentiment(self, text):
        if not self.hf_token:
            self.logger.error("Hugging Face token not found in environment.")
            return {}

        url = "https://api-inference.huggingface.co/models/distilbert-base-uncased-finetuned-sst-2-english"
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        payload = {"inputs": text}

        try:
            async with self.session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    self.logger.error(f"Hugging Face API error: {resp.status}")
                    return {}

                data = await resp.json()
                if not data or "error" in data:
                    self.logger.error(f"Hugging Face returned error: {data}")
                    return {}

                # Mock conversion of sentiment to instrument signals
                sentiment = {
                    "EUR_USD": 0.7,
                    "GBP_USD": 0.6,
                    "USD_JPY": -0.3,
                    "AUD_USD": 0.1,
                    "USD_CAD": -0.5,
                }
                return sentiment

        except Exception as e:
            self.logger.error(f"Sentiment API call failed: {e}")
            return {}