# ===========================================
# main.py - Negotiation Orchestrator
# ===========================================
import threading
import time
from buyer_client import BuyerClient
from seller_server import SellerServer, Product

# -----------------------------
# CONFIG
# -----------------------------
MIN_EXCHANGES = 3
MAX_EXCHANGES = 10

PRODUCT_NAME = "Alphonso Mangoes"
MARKET_PRICE = 180000
QUALITY_GRADE = "A"
QUANTITY = 100


# -----------------------------
# RUNNING LOGIC
# -----------------------------
def run_seller():
    product = Product(
        name=PRODUCT_NAME,
        base_market_price=MARKET_PRICE,
        quality_grade=QUALITY_GRADE,
        quantity=QUANTITY,
    )
    server = SellerServer(product)
    server.run()


def run_buyer():
    buyer = BuyerClient()
    buyer.connect()
    buyer.negotiate()


if __name__ == "__main__":
    print("=== AI Negotiation System Starting ===")

    # Track negotiation rounds globally
    rounds_counter = {"count": 0, "done": False}

    def wrapped_buyer():
        buyer = BuyerClient()
        buyer.connect()
        while not rounds_counter["done"]:
            cont = buyer.negotiate()  # we’ll tweak buyer to return False if finished
            rounds_counter["count"] += 1

            # Ensure loop safety
            if rounds_counter["count"] >= MAX_EXCHANGES:
                print("\n[MAIN] ⛔ Max exchanges reached. Ending negotiation...")
                rounds_counter["done"] = True
                break

            # Artificially enforce minimum exchanges before accept
            if rounds_counter["count"] < MIN_EXCHANGES:
                # force continuation if accept too early
                if cont is False:  # deal closed too soon
                    print("[MAIN] ⚠️ Deal tried to close too early, continuing at least until 3 rounds...")
                    continue

            if cont is False:
                # negotiation ended naturally
                rounds_counter["done"] = True
                break

    # Launch seller in background thread
    seller_thread = threading.Thread(target=run_seller, daemon=True)
    seller_thread.start()

    time.sleep(1)  # let server boot

    # Launch buyer
    buyer_thread = threading.Thread(target=wrapped_buyer, daemon=True)
    buyer_thread.start()

    # Wait for buyer thread
    buyer_thread.join()

    print("\n=== Negotiation session ended ===")

