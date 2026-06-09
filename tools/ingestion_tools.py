"""
Ingestion tools for adding transactions manually via the agent.
"""

from datetime import datetime, timezone
from .db import get_transactions, get_embedding, format_inr, HOUSEHOLD_ID

VALID_MEMBERS = {"MK", "AK", "AC", "AR"}
VALID_CATEGORIES = [
    "Nursing Staff", "Hospital Equipment Rental", "Medicines",
    "Medical Consumables", "Medical Insurance", "Doctor Consultation",
    "Diagnostic Tests", "Hospitalisation", "Toiletries", "Groceries",
    "Foodstuffs", "Electricity", "Gas", "Water", "Cable / Internet",
    "Municipal Property Tax", "Household Insurance", "Car Insurance",
    "Accounting Legal Fees", "Bank Charges"
]


def add_manual_transaction(
    paid_by: str,
    transaction_date: str,
    amount: float,
    vendor: str,
    expense_category: str,
    split_between: str,
    remarks: str = "",
    payment_mode: str = "UPI",
    is_parent_care: bool = True,
    split_ratio: str = None
) -> dict:
    """
    Add a new expense transaction manually.
    Use this when the user wants to record a new expense.
    Always confirm details with the user before calling this tool.

    Args:
        paid_by: Who paid (MK, AK, AC, or AR)
        transaction_date: Date in YYYY-MM-DD format
        amount: Amount in INR
        vendor: Name of vendor/payee
        expense_category: Category of expense
        split_between: Comma-separated member names e.g. "MK,AK" or "MK,AK,AC"
        remarks: Description of the expense
        payment_mode: How payment was made (UPI, Cash, Cheque etc.)
        is_parent_care: True if this is for father's care
        split_ratio: Optional comma-separated ratios e.g. "1,1" or "2,1"

    Returns:
        Confirmation of transaction saved
    """
    try:
        # Validate paid_by
        paid_by = paid_by.upper().strip()
        if paid_by not in VALID_MEMBERS:
            return {
                "status": "error",
                "message": f"paid_by must be one of {sorted(VALID_MEMBERS)}, got '{paid_by}'"
            }

        # Parse split_between
        members = [m.strip().upper() for m in split_between.split(",") if m.strip()]
        invalid = [m for m in members if m not in VALID_MEMBERS]
        if invalid:
            return {
                "status": "error",
                "message": f"Invalid member(s) in split_between: {invalid}"
            }

        # Parse split_ratio
        ratios = []
        if split_ratio:
            try:
                ratios = [int(r.strip()) for r in split_ratio.split(",")]
                if len(ratios) != len(members):
                    return {
                        "status": "error",
                        "message": f"split_ratio has {len(ratios)} values but split_between has {len(members)} members"
                    }
            except ValueError:
                return {"status": "error", "message": "split_ratio must be integers e.g. '1,1'"}
        else:
            ratios = [1] * len(members)

        # Calculate per person share
        total_ratio = sum(ratios)
        per_person_share = round(amount / len(members)) if not split_ratio else round(
            amount * ratios[members.index(paid_by)] / total_ratio
            if paid_by in members else amount / len(members)
        )

        # Build search text for embedding
        search_text = f"{vendor} {expense_category} {remarks} {'dad father parent care' if is_parent_care else 'household utility'}"

        # Generate embedding
        embedding = get_embedding(search_text)

        # Build document
        doc = {
            "household_id": HOUSEHOLD_ID,
            "paid_by": paid_by,
            "transaction_date": transaction_date,
            "amount": int(amount),
            "currency": "INR",
            "payment_mode": payment_mode,
            "expense_category": expense_category,
            "is_parent_care": is_parent_care,
            "vendor": vendor.upper(),
            "remarks": remarks,
            "split_between": members,
            "split_ratio": ratios,
            "per_person_share": per_person_share,
            "source_type": "agent_manual",
            "verified": True,
            "search_text": search_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if embedding:
            doc["search_text_embedding"] = embedding

        # Insert to MongoDB
        collection = get_transactions()
        result = collection.insert_one(doc)

        return {
            "status": "success",
            "message": "Transaction saved successfully",
            "transaction_id": str(result.inserted_id),
            "summary": {
                "paid_by": paid_by,
                "date": transaction_date,
                "amount": format_inr(amount),
                "vendor": vendor.upper(),
                "category": expense_category,
                "split_between": members,
                "per_person_share": format_inr(per_person_share),
                "embedding_generated": embedding is not None
            }
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
