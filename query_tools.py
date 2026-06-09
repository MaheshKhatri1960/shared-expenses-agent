"""
Query tools for the shared expenses agent.
Handles semantic search, filtered queries, and summaries.

Updated: expense_owner field replaces is_parent_care
  DAD       = Father's medical and care expenses
  MOM       = Mother's historical medical expenses
  HOUSEHOLD = Shared utility and household expenses
  FAMILY    = General family expenses
"""

from datetime import datetime
from .db import get_transactions, get_embedding, format_inr, VECTOR_INDEX, HOUSEHOLD_ID

VALID_OWNERS = {"DAD", "MOM", "HOUSEHOLD", "FAMILY"}


def search_expenses_semantic(query: str, limit: int = 5) -> dict:
    """
    Search expenses using natural language semantic search.
    Use this for queries like "Papa's medical bills", "nursing staff costs",
    "Mom's expenses", "medicines", "hospital equipment",
    "utility bills", "household expenses" etc.

    Args:
        query: Natural language search query
        limit: Maximum number of results to return (default 5)

    Returns:
        Dictionary with matching transactions and total amount
    """
    try:
        collection = get_transactions()
        embedding = get_embedding(query)

        if embedding:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": VECTOR_INDEX,
                        "path": "search_text_embedding",
                        "queryVector": embedding,
                        "numCandidates": 50,
                        "limit": limit * 2,
                    }
                },
                {
                    "$match": {"household_id": HOUSEHOLD_ID}
                },
                {
                    "$limit": limit
                },
                {
                    "$project": {
                        "search_text_embedding": 0,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
            ]
            results = list(collection.aggregate(pipeline))
        else:
            results = list(collection.find(
                {
                    "household_id": HOUSEHOLD_ID,
                    "$or": [
                        {"search_text": {"$regex": query, "$options": "i"}},
                        {"remarks": {"$regex": query, "$options": "i"}},
                        {"vendor": {"$regex": query, "$options": "i"}},
                        {"expense_category": {"$regex": query, "$options": "i"}}
                    ]
                },
                {"search_text_embedding": 0}
            ).limit(limit))

        if not results:
            return {
                "status": "no_results",
                "message": f"No expenses found matching '{query}'",
                "transactions": [],
                "total_amount": 0
            }

        total = sum(r.get("amount", 0) for r in results)

        formatted = []
        for r in results:
            formatted.append({
                "date": r.get("transaction_date", ""),
                "paid_by": r.get("paid_by", ""),
                "amount": format_inr(r.get("amount", 0)),
                "amount_raw": r.get("amount", 0),
                "vendor": r.get("vendor", ""),
                "category": r.get("expense_category", ""),
                "remarks": r.get("remarks", ""),
                "split_between": r.get("split_between", []),
                "per_person_share": format_inr(r.get("per_person_share", 0)),
                "expense_owner": r.get("expense_owner", ""),
                "source_type": r.get("source_type", ""),
            })

        return {
            "status": "success",
            "query": query,
            "count": len(formatted),
            "total_amount": format_inr(total),
            "total_amount_raw": total,
            "transactions": formatted
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "transactions": []}


def get_expenses_by_filter(
    paid_by: str = None,
    expense_category: str = None,
    expense_owner: str = None,
    month: int = None,
    year: int = None,
    min_amount: float = None,
    max_amount: float = None
) -> dict:
    """
    Get expenses using specific filters.
    Use this for structured queries like:
    - "expenses paid by MK"
    - "expenses in March 2026"
    - "Dad's expenses" (expense_owner=DAD)
    - "Mom's expenses" (expense_owner=MOM)
    - "household expenses" (expense_owner=HOUSEHOLD)
    - "expenses over 10000"

    Args:
        paid_by: Family member who paid (MK, AK, AC, AR)
        expense_category: Category name e.g. "Nursing Staff", "Medicines"
        expense_owner: DAD, MOM, HOUSEHOLD, or FAMILY
        month: Month number (1-12)
        year: Year (e.g. 2026)
        min_amount: Minimum transaction amount
        max_amount: Maximum transaction amount

    Returns:
        Dictionary with matching transactions and summary
    """
    try:
        collection = get_transactions()
        query_filter = {"household_id": HOUSEHOLD_ID}

        if paid_by:
            query_filter["paid_by"] = paid_by.upper()
        if expense_category:
            query_filter["expense_category"] = {
                "$regex": expense_category, "$options": "i"
            }
        if expense_owner:
            owner = expense_owner.upper()
            if owner in VALID_OWNERS:
                query_filter["expense_owner"] = owner
            else:
                return {
                    "status": "error",
                    "message": f"expense_owner must be one of {sorted(VALID_OWNERS)}"
                }

        # Date filtering
        if month or year:
            date_conditions = []
            if year and month:
                start = f"{year}-{month:02d}-01"
                end_month = month + 1 if month < 12 else 1
                end_year = year if month < 12 else year + 1
                end = f"{end_year}-{end_month:02d}-01"
                date_conditions = [
                    {"transaction_date": {"$gte": start}},
                    {"transaction_date": {"$lt": end}}
                ]
            elif year:
                date_conditions = [
                    {"transaction_date": {"$gte": f"{year}-01-01"}},
                    {"transaction_date": {"$lt": f"{year+1}-01-01"}}
                ]
            elif month:
                current_year = datetime.now().year
                start = f"{current_year}-{month:02d}-01"
                end_month = month + 1 if month < 12 else 1
                end_year = current_year if month < 12 else current_year + 1
                end = f"{end_year}-{end_month:02d}-01"
                date_conditions = [
                    {"transaction_date": {"$gte": start}},
                    {"transaction_date": {"$lt": end}}
                ]
            if date_conditions:
                query_filter["$and"] = date_conditions

        # Amount filtering
        if min_amount or max_amount:
            amount_filter = {}
            if min_amount:
                amount_filter["$gte"] = min_amount
            if max_amount:
                amount_filter["$lte"] = max_amount
            query_filter["amount"] = amount_filter

        results = list(collection.find(
            query_filter,
            {"search_text_embedding": 0}
        ).sort("transaction_date", -1))

        if not results:
            return {
                "status": "no_results",
                "message": "No expenses found matching the filters",
                "transactions": [],
                "total_amount": 0
            }

        total = sum(r.get("amount", 0) for r in results)

        formatted = []
        for r in results:
            formatted.append({
                "date": r.get("transaction_date", ""),
                "paid_by": r.get("paid_by", ""),
                "amount": format_inr(r.get("amount", 0)),
                "amount_raw": r.get("amount", 0),
                "vendor": r.get("vendor", ""),
                "category": r.get("expense_category", ""),
                "remarks": r.get("remarks", ""),
                "split_between": r.get("split_between", []),
                "per_person_share": format_inr(r.get("per_person_share", 0)),
                "expense_owner": r.get("expense_owner", ""),
            })

        return {
            "status": "success",
            "count": len(formatted),
            "total_amount": format_inr(total),
            "total_amount_raw": total,
            "transactions": formatted
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "transactions": []}


def get_category_summary(
    month: int = None,
    year: int = None,
    expense_owner: str = None
) -> dict:
    """
    Get expense summary grouped by category.
    Use this for "breakdown by category", "category wise summary",
    "Dad's expenses by category", "Mom's expenses by category",
    "household expenses breakdown"

    Args:
        month: Month number (1-12), None for all time
        year: Year (e.g. 2026), None for all time
        expense_owner: DAD, MOM, HOUSEHOLD, or FAMILY — None for all

    Returns:
        Category-wise summary with totals
    """
    try:
        collection = get_transactions()
        match_filter = {"household_id": HOUSEHOLD_ID}

        if expense_owner:
            owner = expense_owner.upper()
            if owner in VALID_OWNERS:
                match_filter["expense_owner"] = owner

        if year and month:
            end_month = month + 1 if month < 12 else 1
            end_year = year if month < 12 else year + 1
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-{month:02d}-01"}},
                {"transaction_date": {"$lt": f"{end_year}-{end_month:02d}-01"}}
            ]
        elif year:
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-01-01"}},
                {"transaction_date": {"$lt": f"{year+1}-01-01"}}
            ]

        pipeline = [
            {"$match": match_filter},
            {"$group": {
                "_id": "$expense_category",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
            }},
            {"$sort": {"total": -1}}
        ]

        results = list(collection.aggregate(pipeline))
        grand_total = sum(r["total"] for r in results)

        categories = []
        for r in results:
            pct = (r["total"] / grand_total * 100) if grand_total > 0 else 0
            categories.append({
                "category": r["_id"],
                "total": format_inr(r["total"]),
                "total_raw": r["total"],
                "count": r["count"],
                "percentage": f"{pct:.1f}%"
            })

        return {
            "status": "success",
            "grand_total": format_inr(grand_total),
            "grand_total_raw": grand_total,
            "category_count": len(categories),
            "categories": categories
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_member_summary(
    month: int = None,
    year: int = None,
    expense_owner: str = None
) -> dict:
    """
    Get expense summary grouped by family member.
    Use this for "who paid how much", "member wise summary",
    "how much did MK pay for Dad", "AK's contributions"

    Args:
        month: Month number (1-12)
        year: Year (e.g. 2026)
        expense_owner: DAD, MOM, HOUSEHOLD, FAMILY — None for all

    Returns:
        Per-member payment summary
    """
    try:
        collection = get_transactions()
        match_filter = {"household_id": HOUSEHOLD_ID}

        if expense_owner:
            owner = expense_owner.upper()
            if owner in VALID_OWNERS:
                match_filter["expense_owner"] = owner

        if year and month:
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-{month:02d}-01"}},
                {"transaction_date": {"$lt": f"{year}-{month+1:02d}-01"
                    if month < 12 else f"{year+1}-01-01"}}
            ]
        elif year:
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-01-01"}},
                {"transaction_date": {"$lt": f"{year+1}-01-01"}}
            ]

        pipeline = [
            {"$match": match_filter},
            {"$group": {
                "_id": "$paid_by",
                "total_paid": {"$sum": "$amount"},
                "transaction_count": {"$sum": 1},
                "categories": {"$addToSet": "$expense_category"}
            }},
            {"$sort": {"total_paid": -1}}
        ]

        results = list(collection.aggregate(pipeline))
        grand_total = sum(r["total_paid"] for r in results)

        members = []
        for r in results:
            pct = (r["total_paid"] / grand_total * 100) if grand_total > 0 else 0
            members.append({
                "member": r["_id"],
                "total_paid": format_inr(r["total_paid"]),
                "total_paid_raw": r["total_paid"],
                "transaction_count": r["transaction_count"],
                "percentage_of_total": f"{pct:.1f}%",
                "categories": r["categories"]
            })

        return {
            "status": "success",
            "grand_total": format_inr(grand_total),
            "grand_total_raw": grand_total,
            "members": members
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_period_summary(
    period: str = "monthly",
    month: int = None,
    year: int = None
) -> dict:
    """
    Get expense summary for a specific period.
    Use this for "monthly summary", "this month's expenses",
    "quarterly summary", "how much did we spend in May"

    Args:
        period: "weekly", "monthly", "quarterly", or "annual"
        month: Month number for monthly summary
        year: Year for the summary

    Returns:
        Period summary with totals broken down by expense_owner
    """
    try:
        collection = get_transactions()

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
            period_label = f"{datetime(year, month, 1).strftime('%B %Y')}"
        elif period == "quarterly" and month:
            quarter = (month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            end_month = start_month + 3
            end_year = year if end_month <= 12 else year + 1
            end_month = end_month if end_month <= 12 else end_month - 12
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-{start_month:02d}-01"}},
                {"transaction_date": {"$lt": f"{end_year}-{end_month:02d}-01"}}
            ]
            period_label = f"Q{quarter} {year}"
        else:
            match_filter["$and"] = [
                {"transaction_date": {"$gte": f"{year}-01-01"}},
                {"transaction_date": {"$lt": f"{year+1}-01-01"}}
            ]
            period_label = f"Annual {year}"

        # Totals pipeline — breakdown by expense_owner
        pipeline = [
            {"$match": match_filter},
            {"$group": {
                "_id": None,
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
                "dad_total": {
                    "$sum": {
                        "$cond": [{"$eq": ["$expense_owner", "DAD"]}, "$amount", 0]
                    }
                },
                "mom_total": {
                    "$sum": {
                        "$cond": [{"$eq": ["$expense_owner", "MOM"]}, "$amount", 0]
                    }
                },
                "household_total": {
                    "$sum": {
                        "$cond": [{"$eq": ["$expense_owner", "HOUSEHOLD"]}, "$amount", 0]
                    }
                },
                "family_total": {
                    "$sum": {
                        "$cond": [{"$eq": ["$expense_owner", "FAMILY"]}, "$amount", 0]
                    }
                }
            }}
        ]

        result = list(collection.aggregate(pipeline))

        if not result:
            return {
                "status": "no_results",
                "period": period_label,
                "message": f"No expenses found for {period_label}"
            }

        r = result[0]

        # Top 5 categories
        cat_pipeline = [
            {"$match": match_filter},
            {"$group": {
                "_id": "$expense_category",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"total": -1}},
            {"$limit": 5}
        ]
        top_categories = list(collection.aggregate(cat_pipeline))

        return {
            "status": "success",
            "period": period_label,
            "total_expenses": format_inr(r["total"]),
            "total_raw": r["total"],
            "transaction_count": r["count"],
            "breakdown_by_owner": {
                "DAD": format_inr(r["dad_total"]),
                "MOM": format_inr(r["mom_total"]),
                "HOUSEHOLD": format_inr(r["household_total"]),
                "FAMILY": format_inr(r["family_total"])
            },
            "top_5_categories": [
                {
                    "category": c["_id"],
                    "total": format_inr(c["total"]),
                    "count": c["count"]
                }
                for c in top_categories
            ]
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
