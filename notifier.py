"""
Modul pengirim notifikasi ke Telegram.
Kalau TELEGRAM_BOT_TOKEN belum diisi, notifikasi cuma di-print ke terminal (fallback).
"""

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def _post_message(text: str, parse_mode: str = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return requests.post(url, json=payload, timeout=15)


def send_telegram(message: str):
    """
    Kirim pesan ke Telegram. Fallback ke print() kalau belum dikonfigurasi.

    Data yang dianalisis (nama token, social media link, dll) datang dari internet
    dan gak bisa diprediksi isinya - kadang ngandung karakter spesial Markdown
    (_, *, `) yang bikin Telegram nolak seluruh pesan kalau formatnya gak seimbang.
    Makanya di sini kita coba kirim dengan format dulu (bold/italic), tapi kalau
    GAGAL karena masalah parsing, otomatis kirim ulang sebagai teks polos - biar
    pesannya TETAP SAMPAI walau tanpa formatting, daripada ilang sama sekali.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[NOTIF - Telegram belum dikonfigurasi, tampil di terminal aja]")
        print(message)
        print("-" * 60)
        return

    try:
        resp = _post_message(message, parse_mode="Markdown")
        if resp.status_code == 400 and "can't parse entities" in resp.text.lower():
            print("[WARN] Markdown gagal di-parse Telegram, kirim ulang sebagai teks polos...")
            plain_text = message.replace("*", "").replace("_", "").replace("`", "")
            resp = _post_message(plain_text, parse_mode=None)

        if resp.status_code != 200:
            print(f"[WARN] Gagal kirim Telegram ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"[WARN] Error kirim Telegram: {e}")
