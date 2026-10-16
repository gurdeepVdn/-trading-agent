# day1_strategy.py

import requests
import pandas as pd
import time
from datetime import datetime, timezone, timedelta
import json

# === SETTINGS ===
API_KEY = "d100f66ad2944f5db00a5c12d6ca7657"
WEBHOOK_URL = "https://pushbird.app/pb_2nh3rauuzowiecr4dx010a76"

# === SIRF FOREX PAIRS (18 pairs) ===
ALL_PAIRS = [
    # Majors
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD",
    # EUR Crosses
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/CAD",
    # GBP Crosses
    "GBP/JPY", "GBP/CHF", "GBP/AUD",
    # AUD Crosses
    "AUD/JPY", "AUD/CHF",
    # NZD Crosses
    "NZD/JPY",
]

# === BATCHES (5 pairs per batch) ===
BATCHES = [
    ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD"],
    ["USD/CAD", "NZD/USD", "EUR/GBP", "EUR/JPY", "EUR/CHF"],
    ["EUR/AUD", "EUR/CAD", "GBP/JPY", "GBP/CHF", "GBP/AUD"],
    ["AUD/JPY", "AUD/CHF", "NZD/JPY", "EUR/USD", "GBP/USD"],
]

# === SESSION CHECK (Bahrain) ===
def is_session_time():
    bh_tz = timezone(timedelta(hours=3))
    now = datetime.now(bh_tz)
    hour = now.hour
    # London: 9 AM - 12 PM, NY: 2 PM - 5 PM
    return 9 <= hour < 12 or 14 <= hour < 17

# === BATCH ROTATION ===
BATCH_FILE = "day1_batch.json"

def get_batch():
    try:
        with open(BATCH_FILE) as f:
            return json.load(f).get('idx', 0)
    except:
        return 0

def save_batch(idx):
    with open(BATCH_FILE, 'w') as f:
        json.dump({'idx': (idx + 1) % len(BATCHES)}, f)

# === ALERT ===
def send_alert(title, message):
    try:
        requests.post(WEBHOOK_URL, json={"title": title, "message": message})
        print(f"ALERT: {title}")
    except Exception as e:
        print(f"Alert fail: {e}")

# === DATA FETCH ===
def fetch_data(ticker, interval, outputsize=200):
    url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval={interval}&outputsize={outputsize}&apikey={API_KEY}"
    try:
        r = requests.get(url, timeout=15)
        d = r.json()
        if 'values' not in d:
            return None
        df = pd.DataFrame(d['values'])
        df = df.iloc[::-1].reset_index(drop=True)
        for c in ['open', 'high', 'low', 'close']:
            df[c] = df[c].astype(float)
        df['date'] = pd.to_datetime(df['datetime'])
        return df
    except:
        return None

# === SWING DETECTION ===
def detect_swings(df):
    sh, sl = [], []
    for i in range(3, len(df)-3):
        if df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1]:
            sh.append({'idx': i, 'price': df['high'].iloc[i]})
        if df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1]:
            sl.append({'idx': i, 'price': df['low'].iloc[i]})
    return sh, sl

# === LIQUIDITY SWEEP ===
def detect_sweep(df, sh, sl):
    if not sh or not sl:
        return None
    last = df.iloc[-1]
    if last['high'] > sh[-1]['price'] and last['close'] < sh[-1]['price']:
        return "Buy Side", sh[-1]['price']
    if last['low'] < sl[-1]['price'] and last['close'] > sl[-1]['price']:
        return "Sell Side", sl[-1]['price']
    return None

# === 5M MSS ===
def detect_mss(df, sh, sl):
    if not sh or not sl:
        return None
    current = df['close'].iloc[-1]
    if current > sh[-1]['price']:
        return "Bullish MSS", sh[-1]['price']
    if current < sl[-1]['price']:
        return "Bearish MSS", sl[-1]['price']
    return None

# === MAIN ===
print("=" * 70)
print("DAY 1 STRATEGY — Forex Only (Liquidity Sweep + 5M MSS)")
print("=" * 70)

if not is_session_time():
    print("Outside session — skip")
    exit()

batch_idx = get_batch()
PAIRS = BATCHES[batch_idx]
print(f"Batch {batch_idx + 1}: {PAIRS}\n")

for pair in PAIRS:
    print(f"Checking {pair}...")
    
    m5 = fetch_data(pair, "5min", 200)
    time.sleep(8)
    
    if m5 is None:
        print(f"  {pair}: Data fail\n")
        continue
    
    sh, sl = detect_swings(m5)
    sweep = detect_sweep(m5, sh, sl)
    mss = detect_mss(m5, sh, sl)
    current = m5['close'].iloc[-1]
    
    if sweep and mss:
        sweep_side, sweep_level = sweep
        mss_type, mss_level = mss
        
        # BUY Setup: Sell-side sweep + Bullish MSS
        if sweep_side == "Sell Side" and mss_type == "Bullish MSS":
            entry = current
            sl_price = sweep_level
            tp_price = entry + 2 * (entry - sl_price)
            send_alert(
                f"DAY 1 BUY - {pair}",
                f"Sweep: Sell Side @ {sweep_level:.5f}\nMSS: Bullish @ {mss_level:.5f}\nEntry: {entry:.5f}\nSL: {sl_price:.5f}\nTP: {tp_price:.5f}\nRR: 1:2"
            )
        
        # SELL Setup: Buy-side sweep + Bearish MSS
        elif sweep_side == "Buy Side" and mss_type == "Bearish MSS":
            entry = current
            sl_price = sweep_level
            tp_price = entry - 2 * (sl_price - entry)
            send_alert(
                f"DAY 1 SELL - {pair}",
                f"Sweep: Buy Side @ {sweep_level:.5f}\nMSS: Bearish @ {mss_level:.5f}\nEntry: {entry:.5f}\nSL: {sl_price:.5f}\nTP: {tp_price:.5f}\nRR: 1:2"
            )
        else:
            print(f"  Sweep: {sweep_side} | MSS: {mss_type} — no match")
    else:
        print(f"  Sweep: {sweep if sweep else 'None'} | MSS: {mss if mss else 'None'}")
    
    print()

save_batch(batch_idx)
print("=" * 70)
print("Batch complete. Next run: next batch.")
print("=" * 70)
