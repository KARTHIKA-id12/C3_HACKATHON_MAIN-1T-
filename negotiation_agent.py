"""
===========================================
AI NEGOTIATION AGENT
===========================================

This module defines the buyer agent, its persona, negotiation tactics,
and fallback logic for handling offers. It is fully compatible with
buyer_client.py using Ollama or rule-based fallback.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any


# ============================================
# DATA STRUCTURES
# ============================================

@dataclass
class Product:
    """Product being negotiated"""
    name: str
    category: str
    quantity: int
    quality_grade: str  # 'A', 'B', or 'Export'
    origin: str
    base_market_price: int
    attributes: Dict[str, Any]


@dataclass
class NegotiationContext:
    """Current negotiation state"""
    product: Product
    your_budget: int
    current_round: int
    seller_offers: List[int]
    your_offers: List[int]
    messages: List[Dict[str, str]]


class DealStatus(Enum):
    ONGOING = "ongoing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTER = "counter"
    TIMEOUT = "timeout"


# ============================================
# BUYER AGENT
# ============================================

class YourBuyerAgent:
    """
    MARKET ANALYST BUYER AGENT
    Data-driven and conversational negotiator that adapts dynamically.
    """

    def __init__(self, name: str):
        self.name = name

        # Define buyer persona
        self.persona = {
            "role": "smart price-conscious buyer",
            "style": "polite but firm negotiator",
            "goal": "secure the best possible price without offending the seller"
        }

        # Define negotiation tactics
        self.tactics = [
            "start with low counter offers",
            "gradually increase offer if seller does not budge",
            "mention market price to justify counters",
            "use persuasion (e.g., bulk order, repeat customer)",
            "walk away if price is too high"
        ]

    # -----------------------------
    # Methods for Ollama prompts
    # -----------------------------
    def get_persona_description(self) -> str:
        """Return a natural language description of the buyer persona."""
        return (
            f"You are acting as a {self.persona['role']}. "
            f"Your negotiation style is {self.persona['style']}. "
            f"Your goal is to {self.persona['goal']}."
        )

    def get_negotiation_tactics(self) -> str:
        """Return a natural language list of tactics for LLM to follow."""
        return "Negotiation tactics:\n- " + "\n- ".join(self.tactics)

    def get_personality_prompt(self) -> str:
        """Return a concise persona description for Ollama prompts."""
        return (
            "I am a Market Analyst buyer. I always provide clear, professional reasoning, "
            "cite market benchmarks, and respect budget discipline. I speak in full sentences, "
            "offer constructive counter-offers, and adapt tone as negotiations progress."
        )

    # -----------------------------
    # Fallback logic for rule-based negotiation
    # -----------------------------
    def respond_to_seller_offer(
        self, context: NegotiationContext, seller_price: int, seller_message: str
    ):
        """
        Rule-based fallback negotiation logic if Ollama is not used.
        """
        print(f"[AGENT] Fallback: Seller offered ₹{seller_price:,}, budget ₹{context.your_budget:,}")
        
        # Accept if price within budget
        if seller_price <= context.your_budget:
            return DealStatus.ACCEPTED, seller_price, "That works for me. Deal accepted."
        
        # Reject if price too high
        elif seller_price > context.your_budget * 1.5:
            return DealStatus.REJECTED, 0, "Too expensive, I cannot proceed."

        # Otherwise, make a strategic counter
        else:
            last_offer = context.your_offers[-1] if context.your_offers else int(context.product.base_market_price * 0.65)
            counter_price = max(int(last_offer * 1.07), int(context.your_budget * 0.8))
            return DealStatus.COUNTER, counter_price, f"I can offer ₹{counter_price:,}."


# ============================================
# Optional: Test Framework
# ============================================

if __name__ == "__main__":
    # Quick test
    product = Product(
        name="Alphonso Mangoes",
        category="Mangoes",
        quantity=100,
        quality_grade="A",
        origin="Ratnagiri",
        base_market_price=180000,
        attributes={"ripeness": "optimal"}
    )

    agent = YourBuyerAgent("TestBuyer")
    print(agent.get_persona_description())
    print(agent.get_negotiation_tactics())
    print(agent.get_personality_prompt())

    context = NegotiationContext(
        product,
        your_budget=200000,
        current_round=1,
        seller_offers=[250000],
        your_offers=[],
        messages=[]
    )
    status, price, msg = agent.respond_to_seller_offer(context, 250000, "Premium quality A grade mangoes!")
    print(f"Status: {status}, Offer: ₹{price}, Message: {msg}")

