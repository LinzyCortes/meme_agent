"""
ENTRY POINT - jalankan semua agent sekaligus.

Mode:
    python main.py once     -> jalan sekali lalu keluar (cocok utk GitHub Actions/cron)
    python main.py loop     -> jalan terus-menerus dengan jeda SCAN_INTERVAL_MINUTES

Catatan: smart_money_finder (auto-discover wallet) sengaja TIDAK dijalankan tiap
kali script ini jalan, karena dia lumayan berat request-nya (nelusurin pembeli awal
banyak token). Jalankan terpisah secara berkala (mis. 1x sehari) dengan:
    python smart_money_finder.py
Atau pakai --with-smart-money buat include di run ini juga.
"""

import sys
import time

import wallet_tracker
import token_screener
import smart_money_finder
import performance_tracker
from config import SCAN_INTERVAL_MINUTES


def run_all_once(with_smart_money: bool = False):
    if with_smart_money:
        print("=" * 60)
        print("Menjalankan Smart Money Finder (Agent 4)...")
        smart_money_finder.run_once()

    print("=" * 60)
    print("Menjalankan Wallet Tracker (Agent 1)...")
    wallet_tracker.run_once()

    print("=" * 60)
    print("Menjalankan Token Screener + Deep Analysis (Agent 2 & 3)...")
    token_screener.run_once(trigger_deep_analysis=True)

    print("=" * 60)
    print("Menjalankan Performance Tracker (Agent 5)...")
    performance_tracker.update_all()
    print("=" * 60)


def run_loop(with_smart_money: bool = False):
    while True:
        run_all_once(with_smart_money=with_smart_money)
        print(f"[INFO] Tidur {SCAN_INTERVAL_MINUTES} menit sebelum scan berikutnya...\n")
        time.sleep(SCAN_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    include_smart_money = "--with-smart-money" in sys.argv

    if mode == "loop":
        run_loop(with_smart_money=include_smart_money)
    else:
        run_all_once(with_smart_money=include_smart_money)
