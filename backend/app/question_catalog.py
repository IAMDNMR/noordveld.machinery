"""The question catalogs shown under the question boxes of Parts Intelligence and Agentic E-Commerce.

Every question names a part, machine, supplier, dealer, warehouse, assembly, order or claim that exists in the demo graph. Each one
is run against the live API by `scripts/question_catalog_check.py`; a question that fails there is corrected or removed, never listed
unverified. The order and claim in the shopping catalog belong to the demo End User Lars Becker (USR-EU-002).
"""
from __future__ import annotations

PART_RECORD = "Questions about one named part's record (its machines, its stock) are answered after sign-in; Parts Intelligence answers them for everyone."
SIGN_IN = "Sign in as an End User. The example order and claim belong to the demo End User Lars Becker."

INTELLIGENCE_CATALOG: list[dict] = [
  {
    "category": "Find parts",
    "questions": ["Find NVM-1050-HY", "Find air filters for the NV-3200", "Find hydraulic hoses"],
  },
  {
    "category": "Machines & fitment",
    "questions": [
      "Which parts fit the NV-4500?",
      "Which machines use NVM-1050-HY?",
      "Does NVM-1050-HY fit the KFT-200?",
      "What machines are available?",
      "Tell me about the NV-3200",
      "What parts are used across multiple machines?",
    ],
  },
  {
    "category": "Relationships & assemblies",
    "questions": [
      "Which parts are related to NVM-1010-AT?",
      "What category is NVM-1050-HY in?",
      "Show the relationships for NVM-1050-HY.",
      "What assemblies contain NVM-1010-AT?",
      "Which parts are in Final drive gearbox assembly?",
      "How is NVM-1050-HY connected to the KFT-200?",
    ],
  },
  {
    "category": "Suppliers & dealers",
    "questions": [
      "Which suppliers are connected to NVM-1050-HY?",
      "Which parts does Veldstra Hydraulics (demo) supply?",
      "Which dealers stock NVM-1010-AT?",
      "What does Noordland Machines (demo) stock?",
      "Which dealers are in Rotterdam?",
    ],
  },
  {
    "category": "Stock & locations",
    "questions": [
      "Where is NVM-1050-HY available?",
      "Which warehouses hold NVM-1050-HY?",
      "What is the stock of NVM-1050-HY?",
      "What is in stock at Regional Distribution Centre Zwolle (demo)?",
      "Which parts are low on stock?",
    ],
  },
  {
    "category": "Compliance, service & orders",
    "questions": [
      "Which compliance requirements apply to NVM-1010-AT?",
      "Which service plans require NVM-1050-FL?",
      "Which orders contain NVM-1010-HY?",
      "What is the status of order ORD-0013?",
    ],
  },
  {
    "category": "Data quality & provenance",
    "questions": ["What is the provenance of NVM-1050-HY?", "Where is the catalogue data incomplete?", "What information is missing for NVM-1050-HY?"],
  },
]

SHOPPING_CATALOG: list[dict] = [
  {
    "category": "Find a part",
    "questions": [
      "I need a hydraulic pump.",
      "Find a hydraulic pump for my KFT-200.",
      "I need an air filter for my NV-3200, preferably in stock.",
      "Find a cooling fan for the NV-4500.",
    ],
  },
  {
    "category": "Fitment & compatibility",
        "note": PART_RECORD,
    "questions": ["Which parts fit my NV-3200?", "Which machines use NVM-1050-HY?", "Is this hydraulic pump compatible with the KFT-200?"],
  },
  {
    "category": "Budget & price",
    "questions": [
      "Find the cheapest cooling fan for the NV-4500.",
      "Find the cheapest air filter for my NV-3200",
      "Find a bucket under €2200 for my NV-3200.",
      "Find a bucket under €100 for my NV-3200",
    ],
  },
  {
    "category": "Availability & quantity",
        "note": PART_RECORD,
    "questions": [
      "Do you have NVM-1050-HY in stock?",
      "I need 3 air filters for my NV-3200",
      "I need 5 brake pad sets for my NV-3200",
      "Find the best available bucket for my NV-3200",
    ],
  },
  {
    "category": "Delivery",
    "questions": [
      "How fast can I get an air filter for my NV-3200 delivered to Aalborg?",
      "What is the cheapest delivery option for an air filter for my NV-3200 to Aalborg?",
      "My NV-3200 is down. I need a bucket under €2200, delivered to Aalborg as fast as possible.",
      "I need a footstep bracket for the NV-2100, delivered to Aalborg.",
      "Can a hydraulic pump for my KFT-200 be delivered to Lagos?",
    ],
  },
  {
    "category": "Orders & shipments",
    "note": SIGN_IN,
    "questions": ["Where is my shipment?", "Which parts are in my shipment?", "Show me my order.", "Has order HCME-ORD-000001 shipped?"],
  },
  {
    "category": "Warranty",
    "note": SIGN_IN,
    "questions": ["Is this failed part covered by warranty?", "Is my warranty still active?", "Is claim CLM-G001 covered?"],
  },
  {
    "category": "Combined questions",
    "note": "Parts are answered for everyone; the order and warranty parts need sign-in.",
    "questions": [
      "Find a hydraulic pump for my KFT-200 delivered to Aalborg, and has order HCME-ORD-000001 shipped?",
      "I need a hydraulic pump for my KFT-200, and is claim CLM-G001 covered?",
      "I need a replacement hydraulic pump urgently. Is the failed one covered by warranty and how quickly can I get a replacement?",
    ],
  },
]
