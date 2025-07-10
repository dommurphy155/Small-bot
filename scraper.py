import aiohttp
import asyncio
import logging
import random
import time

HUGGINGFACE_MODELS = [
    "ProsusAI/finbert", "yiyanghkust/finbert-tone",
    "finiteautomata/beto-sentiment-analysis", "cardiffnlp/twitter-roberta-base-sentiment",
    "siebert/sentiment-roberta-large-english", "distilbert-base-uncased-finetuned-sst-2-english",
    "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis", "bhadresh-savani/bert-base-go-emotion",
    "michellejieli/emotion_text_classifier", "SamLowe/roberta-base-go_emotions"
]

NEWS_URLS = [
    "https://www.reuters.com", "https://www.bloomberg.com", "https://www.cnbc.com", "https://www.investing.com",
    "https://www.marketwatch.com", "https://www.wsj.com", "https://www.fxstreet.com", "https://www.coindesk.com",
    "https://www.yahoo.com/finance", "https://www.ft.com", "https://www.theguardian.com/business",
    "https://www.economist.com", "https://www.moneycontrol.com", "https://www.zerohedge.com", "https://www.dailyfx.com",
    "https://www.tradingview.com", "https://www.forexlive.com", "https://www.kitco.com", "https://seekingalpha.com",
    "https://markets.businessinsider.com"
]

class MarketSentimentScraper:
    def __init__(self, logger: logging.Logger, hf_api_key: str):
        self.logger = logger
        self.hf_token = hf_api_key
        self.session = None
        self.current_model_index = 0

    async def fetch(self):
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()

            headlines = await self.scrape_headlines()

            sentiment_summary = await self.analyze_sentiment(headlines)
            return sentiment_summary

        except Exception as e:
            self.logger.error(f"❌ Sentiment scraping failed: {e}")
            return {}

    async def scrape_headlines(self):
        headlines = []
        for url in NEWS_URLS:
            try:
                async with self.session.get(url, timeout=10) as resp:
                    text = await resp.text()
                    titles = self.extract_titles(text)
                    headlines.extend(titles[:2])  # max 2 per site
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to scrape {url}: {e}")
        return headlines[:30]  # limit total

    def extract_titles(self, html):
        import re
        return re.findall(r"<title>(.*?)</title>", html, re.IGNORECASE)

    async def analyze_sentiment(self, headlines):
        results = {"positive": 0, "neutral": 0, "negative": 0}
        headers = {"Authorization": f"Bearer {self.hf_token}"}

        for text in headlines:
            model_used = False
            for attempt in range(10):  # Try 10 different models
                model = HUGGINGFACE_MODELS[self.current_model_index % len(HUGGINGFACE_MODELS)]
                self.current_model_index += 1
                url = f"https://api-inference.huggingface.co/models/{model}"

                try:
                    async with self.session.post(url, headers=headers, json={"inputs": text}, timeout=20) as resp:
                        if resp.status == 200:
                            output = await resp.json()
                            label = self.extract_label(output)
                            if label:
                                results[label] += 1
                                model_used = True
                                break
                        elif resp.status == 503:
                            continue  # Try another
                        else:
                            raise Exception(f"{model} failed with status {resp.status}")
                except Exception as e:
                    self.logger.warning(f"Model {model} error: {e}")
                    continue

            if not model_used:
                self.logger.error("All 10 AI models failed for a headline. Halting bot.")
                raise Exception("No valid AI model responded.")

        total = sum(results.values()) or 1
        sentiment = {
            "positive": results["positive"] / total,
            "neutral": results["neutral"] / total,
            "negative": results["negative"] / total,
        }
        return sentiment

    def extract_label(self, output):
        if isinstance(output, list):
            if isinstance(output[0], list):
                label = output[0][0]['label'].lower()
            else:
                label = output[0]['label'].lower()
        else:
            return None

        if "neg" in label:
            return "negative"
        elif "pos" in label:
            return "positive"
        elif "neutral" in label or "neu" in label:
            return "neutral"
        return None