import re
from typing import Dict, Any
from app.providers.base import AbstractOrderProvider

MOCK_ORDERS = {
    "CLIN-1001": {
        "order_id": "CLIN-1001",
        "status": "In Transit - Out for Delivery",
        "customer_name": "Rohan Sharma",
        "items": ["Clinderma Acne Clarifying Serum 30ml", "Ayurvedic Gut Balance Capsules"],
        "estimated_delivery": "Tomorrow by 5:00 PM via BlueDart",
        "tracking_url": "https://track.bluedart.com/CLIN1001",
        "found": True
    },
    "CLIN-1002": {
        "order_id": "CLIN-1002",
        "status": "Processing - Dermatologist Verification",
        "customer_name": "Priya Patel",
        "items": ["Pigmentation Defence Cream 50g", "Hydrating Gentle Cleanser"],
        "estimated_delivery": "2-3 business days",
        "tracking_url": "https://clinderma.com/account/orders/CLIN-1002",
        "found": True
    },
    "CLIN-1003": {
        "order_id": "CLIN-1003",
        "status": "Delivered",
        "customer_name": "Ananya Verma",
        "items": ["Customized Acne Kit (Phase 1)", "Sunscreen SPF 50 Gel"],
        "estimated_delivery": "Delivered on Aug 8, 2026",
        "tracking_url": "https://track.delhivery.com/CLIN1003",
        "found": True
    }
}

class MockOrderProvider(AbstractOrderProvider):
    def get_order_status(self, query: str) -> Dict[str, Any]:
        query_upper = query.upper().strip()

        # Extract order ID pattern (e.g. CLIN-1001 or 1001)
        match = re.search(r'CLIN-?\d{4}', query_upper)
        if match:
            clean_id = match.group(0)
            if not clean_id.startswith("CLIN-"):
                clean_id = f"CLIN-{clean_id}"
            if clean_id in MOCK_ORDERS:
                return MOCK_ORDERS[clean_id]

        # Check digits
        digits = re.findall(r'\d{4}', query_upper)
        for d in digits:
            key = f"CLIN-{d}"
            if key in MOCK_ORDERS:
                return MOCK_ORDERS[key]

        # Default fallback sample response if generic number entered
        return {
            "order_id": query,
            "status": "Order Found",
            "customer_name": "Valued Customer",
            "items": ["Clinderma Prescribed Skincare Kit"],
            "estimated_delivery": "2-4 Business Days",
            "tracking_url": "https://clinderma.com/track",
            "found": True
        }

def get_order_provider() -> AbstractOrderProvider:
    return MockOrderProvider()
