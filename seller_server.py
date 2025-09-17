# seller_server.py
import os
import socket
import json
import traceback
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv   

# Try to import Gemini SDK; we'll fall back to rule-based if unavailable or key not provided
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except Exception:
    genai = None
    GEMINI_AVAILABLE = False

# -----------------------------
# Config
# -----------------------------
# Load .env file if present
load_dotenv()

HOST = "127.0.0.1"
PORT = 65432

MARKET_PRICE = 180000
MIN_PRICE = int(MARKET_PRICE * 0.8)  # seller won't go below this in logic
PRODUCT_NAME = "Alphonso Mangoes"
QUALITY_GRADE = "A"
QUANTITY = 100

# Read API key from .env or system environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
USE_GEMINI = bool(GEMINI_API_KEY and GEMINI_AVAILABLE)

if GEMINI_API_KEY and GEMINI_AVAILABLE:
    genai.configure(api_key=GEMINI_API_KEY)
    MODEL = genai.GenerativeModel("gemini-1.5-flash")
    print("[SELLER] ✅ Gemini seller enabled (model: gemini-1.5-flash)")
else:
    MODEL = None
    if not GEMINI_API_KEY:
        print("[SELLER] ⚠️ GEMINI_API_KEY not found in .env/environment; running in rule-based fallback mode.")
    if not GEMINI_AVAILABLE:
        print("[SELLER] ⚠️ google.generativeai package not available; running in rule-based fallback mode.")

# -----------------------------
# Helpers
# -----------------------------
def extract_first_json_block(text: str) -> Optional[str]:
    """
    Extract the first balanced JSON object from text.
    This handles text wrapped in markdown fences like ```json { ... } ``` as well as plain JSON.
    Returns the JSON string or None if not found.
    """
    if not text:
        return None
    # find first '{'
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def safe_json_loads_from_model_output(raw: str) -> Optional[dict]:
    """
    Try to extract JSON from the LLM output and parse it.
    Returns dict on success, None on failure.
    """
    try:
        json_block = extract_first_json_block(raw)
        if not json_block:
            return None
        return json.loads(json_block)
    except Exception:
        return None


# -----------------------------
# Product dataclass
# -----------------------------
@dataclass
class Product:
    name: str
    base_market_price: int
    quality_grade: str
    quantity: int


# -----------------------------
# SellerServer
# -----------------------------
class SellerServer:
    def __init__(self, product: Product, min_price: int = MIN_PRICE):
        self.product = product
        self.min_price = min_price
        self.current_price = int(product.base_market_price * 1.4)  # start above market
        self.round = 0

    def _gemini_generate(self, buyer_offer: int, buyer_message: str) -> dict:
        """
        Use Gemini to produce a seller response. Returns a dict with keys:
        - type: 'counter' | 'accept' | 'reject'
        - price: int
        - message: str
        """
        prompt = f"""
You are a SELLER negotiating for premium {self.product.name}.

Context:
- Market price: ₹{self.product.base_market_price}
- Your minimum acceptable price: ₹{self.min_price}
- Your current listed price: ₹{self.current_price}
- Buyer's last offer: ₹{buyer_offer}
- Round number: {self.round}

Buyer said: "{buyer_message}"

Goal:
- Maximize selling price but do not go below minimum.
- Use persuasive, brief language (quality, freshness, rarity).
- If buyer_offer >= min_price, consider accepting.
- Otherwise, propose a counter (never below min_price).

Respond ONLY with valid JSON containing exactly three keys:
{{ "type": "<counter|accept|reject>", "price": <integer>, "message": "<short message>" }}
"""
        try:
            # use model API
            response = MODEL.generate_content(prompt)
            raw_output = getattr(response, "text", str(response)).strip()
            print(f"\n[SELLER DEBUG] Raw Gemini output:\n{raw_output}\n")

            parsed = safe_json_loads_from_model_output(raw_output)
            if not parsed:
                raise ValueError("No valid JSON found in Gemini output")

            # sanitize parsed output
            typ = parsed.get("type", "").lower()
            price = int(parsed.get("price", 0)) if parsed.get("price") is not None else 0
            message = str(parsed.get("message", "")).strip()

            if typ not in ("counter", "accept", "reject"):
                # Normalize/interpret common patterns
                if typ.startswith("acc"):
                    typ = "accept"
                elif typ.startswith("rej"):
                    typ = "reject"
                else:
                    typ = "counter"

            # enforce min price
            if typ == "counter":
                price = max(price, self.min_price)
            elif typ == "accept":
                # ensure acceptance price is reasonable
                price = max(price or buyer_offer or self.min_price, self.min_price)

            return {"type": typ, "price": price, "message": message, "round": self.round}

        except Exception as e:
            print(f"[SELLER] ⚠️ Gemini error or parsing failed: {e}")
            traceback.print_exc()
            return {
                "type": "reject",
                "price": 0,
                "message": "I'm unable to negotiate at this moment. Please try again later.",
                "round": self.round
            }

    def _rule_based_response(self, buyer_offer: int, buyer_message: str) -> dict:
        """
        Deterministic fallback response when Gemini is unavailable.
        Uses negotiation_round to decide concession amount.
        """
        self.round += 1
        # Accept if buyer_offer is very good
        if buyer_offer >= int(self.min_price * 1.1):
            return {
                "type": "accept",
                "price": buyer_offer,
                "message": f"Excellent — I accept your offer of ₹{buyer_offer:,}. Pleasure doing business.",
                "round": self.round
            }

        # If buyer_offer is zero or missing, propose a modest reduction from current price
        if buyer_offer <= 0:
            counter_price = self.current_price
            message = f"My asking price remains ₹{counter_price:,}. These are premium {self.product.quality_grade} grade {self.product.name}."
            return {
                "type": "counter",
                "price": counter_price,
                "message": message,
                "round": self.round
            }

        # Concession strategy
        if self.round >= 8:
            counter_price = max(self.min_price, int(buyer_offer * 1.05))
            message = f"This is my final offer: ₹{counter_price:,}. Take it or leave it."
        elif self.round >= 6:
            counter_price = max(self.min_price, int(buyer_offer * 1.12))
            message = f"I'm coming down to ₹{counter_price:,} — that's really pushing my limits."
        else:
            counter_price = max(self.min_price, int(buyer_offer * 1.18))
            message = f"I appreciate your interest; I can come down to ₹{counter_price:,}. Quality costs money."

        return {"type": "counter", "price": counter_price, "message": message, "round": self.round}

    def handle_buyer_message(self, buyer_data: dict) -> dict:
        """
        Main handler: interpret buyer_data and return seller reply dict.
        Accept both buyer_data['action'] and buyer_data['type'] for compatibility.
        """
        # Normalize buyer action field
        action = (buyer_data.get("action") or buyer_data.get("type") or "").lower()
        buyer_price = int(buyer_data.get("price", 0) or 0)
        buyer_message = str(buyer_data.get("message", "") or "")

        print(f"[SELLER] Received buyer action='{action}', price=₹{buyer_price:,}, message='{buyer_message}'")

        # If buyer accepted on their side
        if action == "accept":
            return {
                "type": "deal_confirmed",
                "price": buyer_price,
                "message": "Deal confirmed! Pleasure doing business with you.",
                "round": self.round
            }

        # If buyer walked away
        if action == "reject":
            return {
                "type": "reject",
                "price": 0,
                "message": "Understood. If you change your mind, let me know.",
                "round": self.round
            }

        # Normal negotiation (counter or other)
        # Use Gemini when configured, otherwise use rule-based fallback
        if USE_GEMINI and MODEL:
            # increase internal round counter before calling model so prompt sees updated round
            self.round += 1
            reply = self._gemini_generate(buyer_price, buyer_message)
            # update internal current_price if model counters
            if reply.get("type") == "counter" and reply.get("price"):
                self.current_price = max(reply["price"], self.min_price)
            return reply
        else:
            # rule-based uses internal round increment inside function
            return self._rule_based_response(buyer_price, buyer_message)

    def run(self):
        print("=== SELLER AGENT STARTING ===")
        print(f"Product: {self.product.name}")
        print(f"Market Price: ₹{self.product.base_market_price:,}")
        print(f"Seller Min Price: ₹{self.min_price:,}")
        print(f"Waiting for buyer on {HOST}:{PORT}...")
        print("=" * 50)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((HOST, PORT))
            server_socket.listen(1)
            conn, addr = server_socket.accept()
            with conn:
                print(f"[SELLER] Buyer connected from {addr}")

                # Send initial opening offer
                opening_msg = {
                    "type": "offer",
                    "price": self.current_price,
                    "message": f"Welcome! I have premium {self.product.quality_grade} grade {self.product.name}. "
                               f"My asking price is ₹{self.current_price:,}. These are high-quality products worth every rupee.",
                    "round": self.round
                }
                conn.sendall(json.dumps(opening_msg, ensure_ascii=False).encode("utf-8"))
                print(f"[SELLER] Sent opening offer: ₹{self.current_price:,}")

                # negotiation loop
                try:
                    # we will loop until a deal is accepted/rejected or connection breaks
                    while True:
                        raw = conn.recv(8192)
                        if not raw:
                            print("[SELLER] Buyer disconnected (no data).")
                            break

                        # decode and parse JSON safely
                        try:
                            decoded = raw.decode("utf-8").strip()
                            buyer_data = json.loads(decoded)
                        except json.JSONDecodeError:
                            # sometimes client might send trailing newline or multiple messages; try to be tolerant
                            text = raw.decode("utf-8", errors="replace").strip()
                            # attempt to extract JSON block from the received bytes
                            json_block = extract_first_json_block(text)
                            if json_block:
                                try:
                                    buyer_data = json.loads(json_block)
                                except json.JSONDecodeError:
                                    print("[SELLER] Received invalid JSON from buyer; ignoring this message.")
                                    continue
                            else:
                                print("[SELLER] Received non-JSON from buyer; ignoring.")
                                continue

                        # handle buyer message and create reply
                        reply = self.handle_buyer_message(buyer_data)

                        # send reply back to buyer
                        conn.sendall(json.dumps(reply, ensure_ascii=False).encode("utf-8"))
                        print(f"[SELLER] Responded with: {reply.get('type')} @ ₹{reply.get('price', 0):,}")

                        # End if final states
                        if reply.get("type") in ("deal_confirmed", "accept", "reject"):
                            print(f"[SELLER] Negotiation ended with type='{reply.get('type')}', price=₹{reply.get('price', 0):,}")
                            break

                except ConnectionResetError:
                    print("[SELLER] Connection reset by peer.")
                except Exception as e:
                    print(f"[SELLER] Unexpected error: {e}")
                    traceback.print_exc()

        print("\n=== SELLER AGENT ENDED ===")


# Keep this block ONLY for standalone testing
if __name__ == "__main__":
    product = Product(
        name=PRODUCT_NAME,
        base_market_price=MARKET_PRICE,
        quality_grade=QUALITY_GRADE,
        quantity=QUANTITY
    )
    server = SellerServer(product)
    server.run()

