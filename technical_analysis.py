"""
Modul analisis teknikal sederhana - RSI dan moving average, dihitung dari
data candle (OHLCV) GeckoTerminal. Ini PELENGKAP analisis fundamental yang
udah ada di deep_analysis.py (kontrak, holder, dll) - bukan pengganti.

CATATAN PENTING: indikator teknikal di token yang BARU BANGET listing (data
candle masih sedikit) kurang reliable - butuh minimal ~15-20 candle biar
RSI/MA bermakna secara statistik. Kalau data candle-nya kurang, modul ini
jujur bilang "data belum cukup" daripada maksa ngasih angka yang menyesatkan.
"""


def calculate_rsi(closes: list, period: int = 14):
    """RSI standar 14-period. closes harus urutan ASCENDING (lama ke baru)."""
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def calculate_sma(closes: list, period: int):
    """Simple Moving Average. closes harus urutan ASCENDING (lama ke baru)."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def interpret_rsi(rsi) -> str:
    if rsi is None:
        return "RSI: data candle belum cukup buat dihitung"
    if rsi >= 70:
        return f"RSI {rsi} - OVERBOUGHT (udah naik cepet, rawan koreksi jangka pendek)"
    if rsi <= 30:
        return f"RSI {rsi} - OVERSOLD (udah turun cepet, bisa rebound tapi juga bisa lanjut turun)"
    return f"RSI {rsi} - netral"


def analyze_technical(ohlcv_list: list) -> dict:
    """
    ohlcv_list format dari GeckoTerminal: [[timestamp, open, high, low, close, volume], ...]
    Urutan dari API biasanya TERBARU DULU (descending), jadi di sini kita
    urutin ulang ascending (lama->baru) biar perhitungan RSI/MA bener arahnya.
    """
    if not ohlcv_list or len(ohlcv_list) < 15:
        return {
            "available": False,
            "summary": "Data candle belum cukup (token masih terlalu baru) buat analisis teknikal yang reliable.",
        }

    sorted_candles = sorted(ohlcv_list, key=lambda c: c[0])
    closes = [c[4] for c in sorted_candles]

    rsi = calculate_rsi(closes)
    sma5 = calculate_sma(closes, 5)
    sma20 = calculate_sma(closes, min(20, len(closes)))

    trend = "Momentum: data belum cukup"
    if sma5 and sma20:
        if sma5 > sma20 * 1.01:
            trend = "Momentum jangka pendek BULLISH (MA5 di atas MA20)"
        elif sma5 < sma20 * 0.99:
            trend = "Momentum jangka pendek BEARISH (MA5 di bawah MA20)"
        else:
            trend = "Momentum jangka pendek netral/sideways"

    return {
        "available": True,
        "rsi": rsi,
        "rsi_interpretation": interpret_rsi(rsi),
        "trend": trend,
        "summary": f"{interpret_rsi(rsi)}. {trend}.",
    }
