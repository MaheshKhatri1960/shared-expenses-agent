"""
Reconciliation tools for settlement calculation.
"""

from datetime import datetime
from .db import get_transactions, get_db, format_inr, HOUSEHOLD_ID


def calculate_settlement(
    month: int = None,
    year: int = None,
    period: str = "monthly"
) -> dict:
    """
    Calculate who owes whom based on shared expenses.
    Use this for "who owes what", "calculate settlement",
    "reconciliation for this month", "who should pay whom"

    Args:
        month: Month number (1-12)
        year: Year (e.g. 2026)
        period: "monthly", "quarterly", or "all_time"

    Returns:
        Settlement calculation with net balances and instructions
    """
    try:
        collection = get_transactions()

        # Default to current period
        if not year:
            year = datetime.now().year
        if not month and period == "monthly":
            month = datetime.now().month

        match_filter = {"household_id": HOUSEHOLD_ID}

        if period == "monthly" and month:
            end_month = month + 1 if month < 12 else 1
            end_year = year if month < 12 else year + 1
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-{month:02d}-01"}},
                {"transaction_date": {"$lt": f"{end_year}-{end_month:02d}-01"}}
            ]
            period_label = datetime(year, month, 1).strftime("%B %Y")
        elif period == "all_time":
            period_label = "All Time"
        else:
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-01-01"}},
                {"transaction_date": {"$lt": f"{year+1}-01-01"}}
            ]
            period_label = f"Annual {year}"

        # Get all transactions for the period
        transactions = list(collection.find(match_filter, {"search_text_embedding": 0}))

        if not transactions:
            return {
                "status": "no_results",
                "period": period_label,
                "message": f"No transactions found for {period_label}"
            }

        # Calculate amounts paid by each member
        paid_by_member = {}
        owed_by_member = {}

        for txn in transactions:
            paid_by = txn.get("paid_by")
            amount = txn.get("amount", 0)
            split_between = txn.get("split_between", [])
            split_ratio = txn.get("split_ratio", [])

            # Record what this member paid
            if paid_by:
                paid_by_member[paid_by] = paid_by_member.get(paid_by, 0) + amount

            # Calculate each member's share
            if split_between:
                num_members = len(split_between)
                if split_ratio and len(split_ratio) == num_members:
                    total_ratio = sum(split_ratio)
                    for member, ratio in zip(split_between, split_ratio):
                        share = amount * ratio / total_ratio
                        owed_by_member[member] = owed_by_member.get(member, 0) + share
                else:
                    # Equal split
                    share = amount / num_members
                    for member in split_between:
                        owed_by_member[member] = owed_by_member.get(member, 0) + share

        # Calculate net balances
        all_members = set(list(paid_by_member.keys()) + list(owed_by_member.keys()))
        net_balances = {}
        for member in all_members:
            paid = paid_by_member.get(member, 0)
            owed = owed_by_member.get(member, 0)
            net_balances[member] = paid - owed  # Positive = others owe this person

        # Generate settlement instructions
        # Simple algorithm: those with negative balance pay those with positive
        creditors = {m: v for m, v in net_balances.items() if v > 0.5}
        debtors = {m: abs(v) for m, v in net_balances.items() if v < -0.5}

        settlement_instructions = []
        creditor_list = sorted(creditors.items(), key=lambda x: -x[1])
        debtor_list = sorted(debtors.items(), key=lambda x: -x[1])

        # Match debtors to creditors
        c_list = [[m, v] for m, v in creditor_list]
        d_list = [[m, v] for m, v in debtor_list]

        ci, di = 0, 0
        while ci < len(c_list) and di < len(d_list):
            creditor, credit = c_list[ci]
            debtor, debt = d_list[di]
            payment = min(credit, debt)
            if payment > 1:
                settlement_instructions.append(
                    f"{debtor} pays {creditor}: {format_inr(round(payment))}"
                )
            c_list[ci][1] -= payment
            d_list[di][1] -= payment
            if c_list[ci][1] < 1:
                ci += 1
            if d_list[di][1] < 1:
                di += 1

        # Save settlement to MongoDB
        settlement_doc = {
            "household_id": HOUSEHOLD_ID,
            "period": period_label,
            "calculated_at": datetime.now().isoformat(),
            "total_expenses": sum(t.get("amount", 0) for t in transactions),
            "member_contributions": {m: round(v) for m, v in paid_by_member.items()},
            "fair_shares": {m: round(v) for m, v in owed_by_member.items()},
            "net_balances": {m: round(v) for m, v in net_balances.items()},
            "settlement_instructions": settlement_instructions
        }

        settlements_collection = get_db()["settlements"]
        settlements_collection.insert_one(settlement_doc)

        # Format member details
        member_details = []
        for member in sorted(all_members):
            paid = paid_by_member.get(member, 0)
            owed = owed_by_member.get(member, 0)
            net = net_balances.get(member, 0)
            status = "receives" if net > 0.5 else "owes" if net < -0.5 else "settled"
            member_details.append({
                "member": member,
                "total_paid": format_inr(round(paid)),
                "fair_share": format_inr(round(owed)),
                "net_balance": format_inr(abs(round(net))),
                "status": status
            })

        return {
            "status": "success",
            "period": period_label,
            "total_expenses": format_inr(sum(t.get("amount", 0) for t in transactions)),
            "transaction_count": len(transactions),
            "member_details": member_details,
            "settlement_instructions": settlement_instructions,
            "settlement_saved": True
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_outstanding_balances() -> dict:
    """
    Get current outstanding balances across all time.
    Use this for "what are the current balances",
    "who still owes money", "overall settlement status"

    Returns:
        Current net balances for all family members
    """
    return calculate_settlement(period="all_time")
