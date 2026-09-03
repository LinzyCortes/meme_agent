"""
AGENT 1: WALLET TRACKER
Memantau daftar wallet di config.WATCHED_WALLETS. Kalau ada wallet yang
buy/sell token (terutama token baru/kecil), kirim notifikasi Telegram.

Cara pakai:
    python wallet_tracker.py
"""

from datetime import datetime, timezone

import solana_rpc_api as sol
import evm_wallet_api
import state
import smart_money_finder
import dashboard_data
from config import WATCHED_WALLETS, WALLET_TRACKER_MIN_SOL_SPENT_FOR_BUY
from notifier import send_telegram


def get_all_wallets_to_watch() -> list:
    """
    Gabungin wallet manual (config.WATCHED_WALLETS) + wallet hasil auto-discovery
    dari smart_money_finder.py (discovered_wallets.json), biar wallet_tracker
    otomatis mantau keduanya tanpa lo perlu isi manual satu-satu.
    """
    combined = list(WATCHED_WALLETS)  # copy biar gak modif list asli
    manual_addresses = {w["address"] for w in WATCHED_WALLETS}

    discovered = smart_money_finder.load_discovered()
    for address, info in discovered.items():
        if address in manual_addresses:
            continue  # udah ada di list manual, skip biar gak dobel
        combined.append({
            "label": f"Smart Money (auto, {info['appearances']}x)",
            "chain": info["chain"],
            "address": address,
        })

    return combined


def check_solana_wallet(wallet: dict):
    """
    Pakai RPC standar (getSignaturesForAddress + getTransaction), BUKAN Helius
    Enhanced API, biar hemat credit / bisa full gratis pakai RPC publik.
    """
    label = wallet["label"]
    address = wallet["address"]

    signatures = sol.get_signatures_for_address(address, limit=15)

    for sig_info in signatures:
        tx_id = sig_info.get("signature")
        if not tx_id or not state.is_new_tx(tx_id):
            continue
        if sig_info.get("err"):
            state.mark_tx_seen(tx_id)  # transaksi gagal, skip tapi tetap tandai biar gak dicek ulang
            continue

        tx = sol.get_transaction(tx_id)
        token_changes = sol.extract_token_changes(tx, address)
        sol_change = sol.extract_sol_change(tx, address)

        if not token_changes:
            state.mark_tx_seen(tx_id)
            continue  # bukan transaksi token (transfer SOL biasa dll), skip biar notif gak spam

        # Filter noise: BUY/IN cuma dianggap valid kalau wallet BENERAN keluar modal
        # (bukan airdrop/reflection/distribusi otomatis yang cuma nambah saldo gratis).
        # Pakai extract_total_sol_spent (gabungan SOL native + WSOL) - BUKAN cuma SOL
        # native - karena kebanyakan swap DEX lewat WSOL, bukan SOL native langsung.
        # SELL/OUT selalu dianggap valid (jual selalu aksi sengaja).
        sol_spent = sol.extract_total_sol_spent(tx, address)
        real_changes = [
            c for c in token_changes
            if c["direction"] == "SELL/OUT" or sol_spent >= WALLET_TRACKER_MIN_SOL_SPENT_FOR_BUY
        ]

        if not real_changes:
            state.mark_tx_seen(tx_id)
            continue  # kemungkinan besar cuma airdrop/reflection/dust, bukan aktivitas beli/jual asli

        lines = []
        for change in real_changes:
            lines.append(
                f"{change['direction']} {abs(change['delta']):.6f} of `{change['mint'][:8]}...`"
            )
        sol_line = f"\nPerubahan SOL: {sol_change:+.4f} SOL" if abs(sol_change) > 0.001 else ""

        message = (
            f"🔔 *Wallet Activity* — {label} (Solana)\n"
            f"Address: `{address}`\n"
            + "\n".join(lines)
            + sol_line
            + f"\nTx: https://solscan.io/tx/{tx_id}"
        )
        send_telegram(message)
        dashboard_data.add_wallet_activity(
            label=label, chain="solana", address=address,
            summary=" | ".join(lines) + sol_line,
            tx_url=f"https://solscan.io/tx/{tx_id}",
        )
        state.mark_tx_seen(tx_id)


def check_evm_wallet(wallet: dict):
    label = wallet["label"]
    address = wallet["address"]
    chain = wallet["chain"]
    transfers = evm_wallet_api.get_wallet_token_transfers(chain, address, limit=15)

    for raw in transfers:
        parsed = evm_wallet_api.parse_transfer(raw, address)
        tx_id = parsed["hash"]
        if not tx_id or not state.is_new_tx(tx_id):
            continue

        ts = datetime.fromtimestamp(int(parsed["timestamp"]), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        explorer = "https://basescan.org" if chain == "base" else "https://etherscan.io"

        message = (
            f"🔔 *Wallet Activity* — {label} ({chain.title()})\n"
            f"Address: `{address}`\n"
            f"Action: {parsed['direction']} {parsed['amount']:.4f} {parsed['token_symbol']}\n"
            f"Waktu: {ts}\n"
            f"Tx: {explorer}/tx/{tx_id}"
        )
        send_telegram(message)
        dashboard_data.add_wallet_activity(
            label=label, chain=chain, address=address,
            summary=f"{parsed['direction']} {parsed['amount']:.4f} {parsed['token_symbol']}",
            tx_url=f"{explorer}/tx/{tx_id}",
        )
        state.mark_tx_seen(tx_id)


def run_once():
    wallets = get_all_wallets_to_watch()
    if not wallets:
        print("[INFO] Belum ada wallet yang dipantau. Isi WATCHED_WALLETS di config.py, "
              "atau jalankan smart_money_finder.py dulu buat auto-discover.")
        return

    print(f"[INFO] Cek {len(wallets)} wallet ({len(WATCHED_WALLETS)} manual + "
          f"{len(wallets) - len(WATCHED_WALLETS)} hasil auto-discovery)...")
    for wallet in wallets:
        try:
            if wallet["chain"] == "solana":
                check_solana_wallet(wallet)
            else:
                check_evm_wallet(wallet)
        except Exception as e:
            print(f"[ERROR] Gagal cek wallet {wallet.get('label')}: {e}")
    print("[INFO] Selesai cek semua wallet.")


if __name__ == "__main__":
    run_once()
