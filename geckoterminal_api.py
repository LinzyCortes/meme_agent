"""
Wrapper untuk GeckoTerminal Public API (gratis, tanpa API key).
Dipakai buat scan pool/token baru & trending di berbagai chain (Solana, Base, Ethereum, dll).
Docs: https://www.geckoterminal.com/dex-api

Rate limit publik ~30 request/menit - script ini sudah kasih jeda antar request.
"""

import time
import requests

BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}

# GeckoTerminal API publik ~30 request/menit (bareng SEMUA pengguna gratis, bukan cuma lo).
# Biar gak pernah nabrak limit itu, kita JAGA JARAK MINIMAL antar request secara proaktif,
# daripada nunggu kena 429 baru retry (yang sering tetep gagal kalau macet).
_last_call_time = 0.0
MIN_INTERVAL_SECONDS = 2.5  # ~24 request/menit, kasih margin aman di bawah batas 30/menit

# Mapping nama chain "user-friendly" -> network id GeckoTerminal
NETWORK_MAP = {
    "solana": "solana",
    "ethereum": "eth",
    "base": "base",
    "bsc": "bsc",
    "arbitrum": "arbitrum",
    "polygon": "polygon_pos",
}


def _wait_for_rate_limit():
    global _last_call_time
    elapsed = time.monotonic() - _last_call_time
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_call_time = time.monotonic()


def _get(url, params=None, retries=4):
    for attempt in range(retries):
        _wait_for_rate_limit()
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
            if resp.status_code == 429:
                wait = 5 * (attempt + 1)  # backoff makin lama tiap percobaan (5s, 10s, 15s, 20s)
                print(f"    [WARN] GeckoTerminal rate limit (429), tunggu {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == retries - 1:
                print(f"[WARN] GeckoTerminal request gagal: {e}")
                return None
            time.sleep(2)
    return None


def get_new_pools(chain: str, page: int = 1):
    """Ambil pool/token yang baru dibuat di suatu chain."""
    network = NETWORK_MAP.get(chain, chain)
    url = f"{BASE_URL}/networks/{network}/new_pools"
    data = _get(url, params={"page": page, "include": "base_token,quote_token"})
    return data.get("data", []) if data else []


def get_trending_pools(chain: str, page: int = 1):
    """Ambil pool yang lagi trending (volume/aktivitas naik) di suatu chain."""
    network = NETWORK_MAP.get(chain, chain)
    url = f"{BASE_URL}/networks/{network}/trending_pools"
    data = _get(url, params={"page": page, "include": "base_token,quote_token"})
    return data.get("data", []) if data else []


def get_pool_detail(chain: str, pool_address: str):
    """Detail lengkap satu pool (harga, mcap, liquidity, volume, dll)."""
    network = NETWORK_MAP.get(chain, chain)
    url = f"{BASE_URL}/networks/{network}/pools/{pool_address}"
    data = _get(url, params={"include": "base_token,quote_token"})
    return data.get("data") if data else None


def get_pools_multi(chain: str, pool_addresses: list):
    """
    Ambil detail BANYAK pool SEKALIGUS dalam 1 request (bukan satu-satu) - jauh
    lebih hemat rate limit. Dipakai buat performance_tracker.py biar bisa ngecek
    puluhan token yang lagi dipantau tanpa boros request. Maksimal 30 address per
    request (batas tier gratis GeckoTerminal).
    """
    if not pool_addresses:
        return []
    network = NETWORK_MAP.get(chain, chain)
    addresses_str = ",".join(pool_addresses[:30])
    url = f"{BASE_URL}/networks/{network}/pools/multi/{addresses_str}"
    data = _get(url, params={"include": "base_token,quote_token"})
    return data.get("data", []) if data else []


def get_ohlcv(chain: str, pool_address: str, timeframe: str = "hour", aggregate: int = 1, limit: int = 50):
    """
    Ambil data candle (open/high/low/close/volume) 1 pool - dasar buat ngitung
    indikator teknikal (RSI, moving average) di technical_analysis.py.
    timeframe: 'day', 'hour', atau 'minute'.
    """
    network = NETWORK_MAP.get(chain, chain)
    url = f"{BASE_URL}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
    data = _get(url, params={"aggregate": aggregate, "limit": limit})
    if not data:
        return []
    try:
        return data["data"]["attributes"]["ohlcv_list"]
    except (KeyError, TypeError):
        return []


def parse_pool(pool: dict) -> dict:
    """Ubah raw JSON pool dari GeckoTerminal jadi dict ringkas & gampang dipakai."""
    attrs = pool.get("attributes", {})

    # Ekstrak token contract address LANGSUNG dari data yang udah ada di response
    # list (new_pools/trending_pools) - GAK PERLU request tambahan (get_pool_detail)
    # buat ini. ID relationship formatnya "<network>_<address>", jadi tinggal di-split.
    # Ini fix besar buat ngirit kuota rate limit GeckoTerminal.
    token_address = None
    try:
        base_token_id = pool["relationships"]["base_token"]["data"]["id"]
        if "_" in base_token_id:
            token_address = base_token_id.split("_", 1)[1]
    except Exception:
        pass

    return {
        "pool_address": attrs.get("address"),
        "name": attrs.get("name"),
        "base_token_symbol": (attrs.get("name") or "?/?").split("/")[0].strip(),
        "token_address": token_address,
        "price_usd": _to_float(attrs.get("base_token_price_usd")),
        "quote_token_price_usd": _to_float(attrs.get("quote_token_price_usd")),  # harga native currency (mis. SOL) saat itu
        "market_cap_usd": _to_float(attrs.get("market_cap_usd") or attrs.get("fdv_usd")),
        "fdv_usd": _to_float(attrs.get("fdv_usd")),
        "liquidity_usd": _to_float(attrs.get("reserve_in_usd")),
        "volume_24h_usd": _to_float(attrs.get("volume_usd", {}).get("h24")),
        "price_change_1h_pct": _to_float(attrs.get("price_change_percentage", {}).get("h1")),
        "price_change_24h_pct": _to_float(attrs.get("price_change_percentage", {}).get("h24")),
        "txns_24h": _sum_txns(attrs.get("transactions", {}).get("h24", {})),
        "pool_created_at": attrs.get("pool_created_at"),
        "dex_url": None,  # diisi belakangan lewat build_pool_url() setelah "chain" diketahui
    }


def build_pool_url(chain: str, pool_address: str) -> str:
    """Bikin URL chart GeckoTerminal yang valid, format: geckoterminal.com/<network>/pools/<address>"""
    network = NETWORK_MAP.get(chain, chain)
    return f"https://www.geckoterminal.com/{network}/pools/{pool_address}"


def _sum_txns(h24: dict) -> int:
    if not h24:
        return 0
    return int(h24.get("buys", 0) or 0) + int(h24.get("sells", 0) or 0)


def _to_float(val):
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0
