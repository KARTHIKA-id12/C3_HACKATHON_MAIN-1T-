# ===========================================
# buyer_client.py (Buyer Agent using Ollama locally)
# ===========================================
import socket
import json
import requests
import traceback
from negotiation_agent import YourBuyerAgent, NegotiationContext, Product, DealStatus

# ==================================================
# CONFIG
# ==================================================
SELLER_HOST = "127.0.0.1"
SELLER_PORT = 65432

USE_OLLAMA = True
MODEL_NAME = "llama3.2"
MAX_ROUNDS = 10

# ✅ Ollama runs locally
OLLAMA_API_URL = "http://localhost:11434/api/chat"


class BuyerClient:
    def __init__(self, budget: int = 200000):
        self.agent = YourBuyerAgent("LiveBuyer")   # persona & strategy
        self.context = None
        self.sock = None
        self.negotiation_active = True
        self.budget = budget

    def connect(self):
        print("[BUYER] 🔌 Connecting to seller...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((SELLER_HOST, SELLER_PORT))
        print("[BUYER] ✅ Connected to seller.")

    def stop(self, reason="Stopped by controller"):
        """Stop negotiation gracefully."""
        self.negotiation_active = False
        try:
            self.sock.sendall(json.dumps({
                "action": "reject",
                "price": 0,
                "message": reason
            }).encode("utf-8"))
        except:
            pass
        finally:
            self.sock.close()
            print(f"[BUYER] ⏹️ Negotiation stopped: {reason}")

    def _ollama_generate(self, prompt: str) -> str:
        """Send prompt to Ollama local API and collect streaming response."""
        try:
            payload = {
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            }
            resp = requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=60)
            resp.raise_for_status()

            response_text = ""
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    if "message" in chunk and "content" in chunk["message"]:
                        response_text += chunk["message"]["content"]
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    continue

            response_text = response_text.strip()
            print("\n[BUYER DEBUG] Final Ollama output:\n", response_text, "\n")
            return response_text

        except Exception as e:
            print(f"[BUYER] ⚠️ Ollama local API error: {e}")
            return '{"action": "reject", "price": 0, "message": "Ollama unavailable, rejecting."}'

    def negotiate(self) -> bool:
        """
        Run one negotiation cycle.
        Returns:
            True if negotiation should continue,
            False if ended (accept/reject/deal closed).
        """
        try:
            data = self.sock.recv(4096)
            if not data:
                print("[BUYER] 🔚 Seller closed connection.")
                return False

            try:
                seller_data = json.loads(data.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                print("[BUYER] ❌ Failed to parse seller message.")
                return True  # ignore and continue

            print(f"\n[BUYER] 📩 Received from seller: {seller_data}")

            if seller_data.get("type") in ("offer", "counter"):
                self.handle_offer(seller_data)
                if self.context.current_round >= MAX_ROUNDS:
                    print("[BUYER] 🛑 Max rounds reached. Rejecting and stopping.")
                    self.stop("Max rounds reached.")
                    return False

            elif seller_data.get("type") in ("accept", "deal_confirmed"):
                print(f"[BUYER] 🎉 Seller accepted! Deal closed at ₹{seller_data['price']:,}")
                return False

            elif seller_data.get("type") == "reject":
                print("[BUYER] ❌ Seller rejected the deal.")
                return False

            return True  # continue loop

        except ConnectionAbortedError:
            print("[BUYER] ❌ Connection aborted.")
            return False
        except Exception as e:
            print(f"[BUYER] ❌ Unexpected error: {e}")
            traceback.print_exc()
            return False

    def handle_offer(self, seller_data):
        # Initialize context if first round
        if not self.context:
            product = Product(
                name="Alphonso Mangoes",
                category="Mangoes",
                quantity=100,
                quality_grade="A",
                origin="Ratnagiri",
                base_market_price=180000,
                attributes={"ripeness": "optimal", "export_grade": True},
            )
            self.context = NegotiationContext(
                product, your_budget=self.budget,
                current_round=0, seller_offers=[], your_offers=[], messages=[]
            )

        self.context.current_round += 1
        self.context.seller_offers.append(seller_data["price"])
        self.context.messages.append({"role": "seller", "message": seller_data["message"]})

        if USE_OLLAMA:
            # ✅ Persona prompt from YourBuyerAgent
            persona_description = self.agent.get_personality_prompt()

            prompt = f"""
            You are a BUYER negotiating for {self.context.product.name}.

            Persona & Strategy:
            {persona_description}

            Negotiation Context:
            - Round: {self.context.current_round}
            - Seller offer: ₹{seller_data["price"]:,}
            - Seller says: "{seller_data['message']}"
            - Your budget: ₹{self.context.your_budget:,}
            - Previous offers: {self.context.your_offers}

            Rules:
            - Stay within budget (never exceed ₹{self.context.your_budget:,}).
            - Always negotiate realistically, consistent with persona.
            - Respond ONLY with JSON in this format:
            {{
                "action": "accept" | "reject" | "counter",
                "price": <int>,
                "message": "<short persuasive message>"
            }}
            """

            response_text = self._ollama_generate(prompt)
            try:
                buyer_response = json.loads(response_text)
            except json.JSONDecodeError:
                print("[BUYER] ⚠️ Ollama output invalid. Using fallback reject.")
                buyer_response = {
                    "action": "reject",
                    "price": 0,
                    "message": "Invalid model response."
                }
        else:
            # Local fallback
            status, counter_price, message = self.agent.respond_to_seller_offer(
                self.context, seller_data["price"], seller_data["message"]
            )
            buyer_response = {
                "action": "accept" if status == DealStatus.ACCEPTED else (
                    "reject" if status == DealStatus.REJECTED else "counter"),
                "price": counter_price,
                "message": message,
            }

        if buyer_response["action"] == "counter":
            self.context.your_offers.append(buyer_response["price"])

        print(f"[BUYER] 🤖 Sent response: {buyer_response}")
        self.sock.sendall(json.dumps(buyer_response).encode("utf-8"))


if __name__ == "__main__":
    buyer = BuyerClient()
    buyer.connect()
    # Run until negotiation ends
    while buyer.negotiate():
        continue




