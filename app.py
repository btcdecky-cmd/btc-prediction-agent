"""
BTC short-term prediction agent (FastAPI).
Fetches live price and applies simple range-bound momentum logic.
Not financial advice.
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import httpx
from datetime import datetime
from pathlib import Path

app = FastAPI(title="BTC Prediction Agent")

# Serve static files if present
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

async def _get_json(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()

async def _coingecko_price() -> float:
    data = await _get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        {"ids": "bitcoin", "vs_currencies": "usd"},
    )
    return float(data["bitcoin"]["usd"])

async def _coinbase_price() -> float:
    data = await _get_json(
        "https://api.coinbase.com/v2/prices/BTC-USD/spot",
        {},
    )
    return float(data["data"]["amount"])

# Keyless public spot sources; the first one that answers wins.
PRICE_SOURCES = (("coingecko", _coingecko_price), ("coinbase", _coinbase_price))

async def get_btc_price() -> dict:
    """Current BTC spot price in USD from the first reachable source."""
    for name, fetch in PRICE_SOURCES:
        try:
            price = await fetch()
            if price > 0:
                return {
                    "price": price,
                    "source": name,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="Could not fetch BTC price")

def analyze(price: float) -> dict:
    """Simple range analysis based on recent observed zone ~80.3k-80.7k."""
    low, high = 80300, 80700
    if price > high + 100:
        pred5, pred10 = "Up", "Up"
        notes = "Above recent range, upside breakout lean."
    elif price < low - 100:
        pred5, pred10 = "Down", "Down"
        notes = "Below recent range, downside pressure."
    else:
        # Inside tight range — mild continuation or chop
        pred5 = "Down" if price > 80500 else "Up"
        pred10 = "Choppy"
        notes = "Tight range-bound ($80.3k-$80.7k). Immediate move often continues last leg or chops."
    return {
        "price": round(price, 2),
        "prediction_5min": pred5,
        "prediction_10min": pred10,
        "notes": notes + " Not financial advice.",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

@app.get("/", response_class=HTMLResponse)
async def root():
    index = static_dir / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return """<h1>BTC Prediction Agent</h1><p>API ready. See <a href='/predict'>/predict</a></p>"""

@app.get("/price")
async def price():
    quote = await get_btc_price()
    return {
        "btc_usd": quote["price"],
        "source": quote["source"],
        "timestamp": quote["timestamp"],
    }

@app.get("/predict")
async def predict(timeframe: str = "5min"):
    quote = await get_btc_price()
    analysis = analyze(quote["price"])
    analysis["timeframe"] = timeframe
    return analysis

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
