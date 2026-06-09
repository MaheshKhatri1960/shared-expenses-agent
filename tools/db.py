"""
MongoDB connection helper for shared expenses agent.
Reads credentials from environment variables.
"""

import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# ─── Constants ────────────────────────────────────────────────────────────────
DB_NAME         = "household_expenses"
COLLECTION_NAME = "transactions"
VECTOR_INDEX    = "transaction_vector_index"
HOUSEHOLD_ID    = "family_001"

# NOTE: MONGO_URI, GCP_PROJECT, GCP_LOCATION are read inside functions
# so that environment variables set in run_agent.py take effect correctly.

_client = None

def get_db():
    """Get MongoDB database connection (singleton)."""
    global _client
    # Read MONGO_URI here — not at module load time
    mongo_uri = os.environ.get("MONGO_URI", "")
    if _client is None:
        if not mongo_uri:
            raise ValueError(
                "MONGO_URI environment variable not set. "
                "Set it in run_agent.py before running."
            )
        _client = MongoClient(mongo_uri, server_api=ServerApi("1"))
    return _client[DB_NAME]

def get_transactions():
    """Get transactions collection."""
    return get_db()[COLLECTION_NAME]

def format_inr(amount):
    """Format amount as Indian Rupees."""
    if amount is None:
        return "₹0"
    try:
        amount = float(amount)
        if amount >= 100000:
            return f"₹{amount/100000:.1f}L"
        elif amount >= 1000:
            return f"₹{amount:,.0f}"
        else:
            return f"₹{amount:.0f}"
    except (TypeError, ValueError):
        return f"₹{amount}"

def get_embedding(text):
    """Generate embedding for semantic search using Vertex AI."""
    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput
        # Read GCP config here — not at module load time
        gcp_project  = os.environ.get("GCP_PROJECT",  "shared-expenses-498507")
        gcp_location = os.environ.get("GCP_LOCATION", "us-central1")
        vertexai.init(project=gcp_project, location=gcp_location)
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        inputs = [TextEmbeddingInput(text=text, task_type="RETRIEVAL_QUERY")]
        results = model.get_embeddings(inputs)
        return results[0].values
    except Exception:
        return None
