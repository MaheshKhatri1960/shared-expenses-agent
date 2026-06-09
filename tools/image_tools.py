"""
Receipt Image Ingestion Tools
==============================
Uses Gemini Vision to extract transaction details from
receipt images and PDFs, then saves to MongoDB Atlas
with Vertex AI embeddings for semantic search.

This demonstrates true multi-modal agentic capability:
1. Accept image file path or base64 encoded image
2. Call Gemini Vision to extract transaction fields
3. Present extracted fields to user for confirmation (HITL)
4. Generate Vertex AI embedding for semantic search
5. Save confirmed transaction to MongoDB Atlas
"""

import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from .db import get_transactions, get_embedding, format_inr, HOUSEHOLD_ID

VALID_MEMBERS = {"MK", "AK", "AC", "AR"}
VALID_OWNERS  = {"DAD", "MOM", "HOUSEHOLD", "FAMILY"}

EXPENSE_CATEGORIES = [
    "Nursing Staff", "Hospital Equipment Rental", "Medicines",
    "Medical Consumables", "Medical Insurance", "Doctor Consultation",
    "Diagnostic Tests", "Hospitalisation", "Toiletries", "Groceries",
    "Foodstuffs", "Electricity", "Gas", "Water", "Cable / Internet",
    "Municipal Property Tax", "Household Insurance", "Car Insurance",
    "Accounting Legal Fees", "Bank Charges"
]


def analyze_receipt_image(image_path: str) -> dict:
    """
    Use Gemini Vision to extract transaction fields from a receipt image.

    Args:
        image_path: Full path to the receipt image or PDF file
                   Supports: .jpg, .jpeg, .png, .pdf, .webp

    Returns:
        Dictionary with extracted fields and confidence level
    """
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel, Part

        # Validate file exists
        path = Path(image_path)
        if not path.exists():
            return {
                "status": "error",
                "message": f"File not found: {image_path}"
            }

        # Determine media type — PDF not supported via Part.from_data
        if path.suffix.lower() == ".pdf":
            return {
                "status": "error",
                "message": (
                    "PDF files are not supported for direct image analysis. "
                    "Please take a photo or screenshot of the receipt and "
                    "provide it as JPG or PNG."
                )
            }

        media_types = {
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".webp": "image/webp"
        }
        media_type = media_types.get(path.suffix.lower(), "image/jpeg")

        # Read file as bytes — used directly by Part.from_data
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Initialise Vertex AI
        gcp_project  = os.environ.get("GCP_PROJECT",  "shared-expenses-498507")
        gcp_location = os.environ.get("GCP_LOCATION", "global")
        vertexai.init(project=gcp_project, location=gcp_location)
        model = GenerativeModel("gemini-3.5-flash")

        # Build extraction prompt
        categories_str = ", ".join(EXPENSE_CATEGORIES)
        prompt = f"""
Analyze this receipt or bill image and extract transaction information.
Return ONLY a valid JSON object with these exact keys — no other text:

{{
    "transaction_date": "DD-MMM-YYYY format if visible, else null",
    "amount": integer total amount in INR (numbers only, no symbols), or null,
    "vendor": "vendor/shop/company name in UPPERCASE, else null",
    "expense_category": "best match from: {categories_str}",
    "vendor_bill_number": "invoice/bill number if visible, else null",
    "vendor_bill_date": "DD-MMM-YYYY format if visible, else null",
    "remarks": "brief description max 60 chars of what was purchased",
    "confidence": "high if all key fields clearly visible, medium if some fields unclear, low if image is poor quality"
}}

Rules:
- amount must be the TOTAL amount as an integer — no decimals, no commas
- If amount is unclear, return null
- vendor must be in UPPERCASE
- Return ONLY the JSON object, no markdown, no explanation
"""

        # Call Gemini Vision
        image_part = Part.from_data(
            data=image_data,
            mime_type=media_type
        )
        response = model.generate_content([prompt, image_part])

        # Parse JSON response
        text = response.text.strip()
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        extracted = json.loads(text)

        return {
            "status": "success",
            "extracted": extracted,
            "source_filename": path.name
        }

    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "message": f"Could not parse Gemini response as JSON: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Image analysis failed: {str(e)}"
        }


def ingest_receipt_image(
    image_path: str,
    paid_by: str,
    expense_owner: str = "DAD",
    split_between: str = "MK,AK",
    split_ratio: str = "1,1"
) -> dict:
    """
    Extract transaction details from a receipt image using Gemini Vision.
    Shows extracted fields to user for confirmation before saving.

    This is a multi-step agentic workflow:
    Step 1: Read the image file
    Step 2: Call Gemini Vision to extract transaction fields
    Step 3: Return extracted fields for human review and confirmation
    Step 4: Human confirms or corrects fields
    Step 5: Call save_receipt_transaction to save to MongoDB

    IMPORTANT: Always show extracted fields to the user and ask for
    confirmation before saving. Never save without explicit user approval.

    Args:
        image_path: Full path to receipt image or PDF
                   e.g. C:/Users/Mahesh/receipts/pharmacy_bill.jpg
        paid_by: Who paid — MK, AK, AC, or AR
        expense_owner: DAD, MOM, HOUSEHOLD, or FAMILY
        split_between: Comma-separated members e.g. MK,AK
        split_ratio: Split ratio e.g. 1,1 for equal split

    Returns:
        Extracted transaction fields for user confirmation
    """
    # Validate paid_by
    paid_by = paid_by.upper().strip()
    if paid_by not in VALID_MEMBERS:
        return {
            "status": "error",
            "message": f"paid_by must be one of {sorted(VALID_MEMBERS)}"
        }

    # Validate expense_owner
    expense_owner = expense_owner.upper().strip()
    if expense_owner not in VALID_OWNERS:
        return {
            "status": "error",
            "message": f"expense_owner must be one of {sorted(VALID_OWNERS)}"
        }

    # Parse members
    members = [m.strip().upper() for m in split_between.split(",") if m.strip()]
    invalid = [m for m in members if m not in VALID_MEMBERS]
    if invalid:
        return {
            "status": "error",
            "message": f"Unknown members in split_between: {invalid}"
        }

    # Step 1 & 2: Analyse the image
    result = analyze_receipt_image(image_path)

    if result["status"] == "error":
        return result

    extracted = result["extracted"]
    source_filename = result["source_filename"]

    # Calculate per person share — safely handle string amounts from Gemini
    amount = extracted.get("amount")
    try:
        amount_num = float(str(amount).replace(",", "")) if amount is not None else None
        per_person_share = round(amount_num / len(members)) if amount_num and members else None
    except (ValueError, TypeError):
        amount_num = None
        per_person_share = None
    amount = amount_num  # Use validated numeric amount

    # Build confirmation response
    confidence = extracted.get("confidence", "unknown")
    confidence_note = ""
    if confidence == "low":
        confidence_note = "⚠️ Low confidence — please verify all fields carefully"
    elif confidence == "medium":
        confidence_note = "⚠️ Medium confidence — please check highlighted fields"

    return {
        "status": "awaiting_confirmation",
        "message": "Receipt analysed successfully. Please review and confirm:",
        "confidence": confidence,
        "confidence_note": confidence_note,
        "extracted_fields": {
            "paid_by": paid_by,
            "expense_owner": expense_owner,
            "transaction_date": extracted.get("transaction_date"),
            "amount": format_inr(amount) if amount else "⚠️ Not detected — please provide",
            "amount_raw": amount,
            "vendor": extracted.get("vendor"),
            "expense_category": extracted.get("expense_category"),
            "vendor_bill_number": extracted.get("vendor_bill_number"),
            "vendor_bill_date": extracted.get("vendor_bill_date"),
            "remarks": extracted.get("remarks"),
            "split_between": members,
            "split_ratio": split_ratio,
            "per_person_share": format_inr(per_person_share) if per_person_share else None,
            "source_type": "receipt_image",
            "source_filename": source_filename
        },
        "next_step": (
           "Are these details correct? "
           "Reply Y to save or N to cancel. "
           "This transaction will NOT be saved until you confirm."
        )
    }


def save_receipt_transaction(
    paid_by: str,
    transaction_date: str,
    amount: float,
    vendor: str,
    expense_category: str,
    expense_owner: str,
    split_between: str,
    remarks: str = "",
    vendor_bill_number: str = None,
    vendor_bill_date: str = None,
    split_ratio: str = "1,1",
    source_filename: str = ""
) -> dict:
    """
    Save a receipt transaction to MongoDB after human confirmation.
    Only call this tool after the user has explicitly confirmed the
    extracted fields from ingest_receipt_image.

    This completes the multi-step agentic workflow:
    - Generates Vertex AI embedding for semantic search
    - Saves transaction to MongoDB Atlas
    - Confirms the transaction is now searchable

    Args:
        paid_by: Who paid (MK, AK, AC, AR)
        transaction_date: Date in DD-MMM-YYYY or YYYY-MM-DD format
        amount: Amount in INR as a number
        vendor: Vendor name in UPPERCASE
        expense_category: Expense category
        expense_owner: DAD, MOM, HOUSEHOLD, or FAMILY
        split_between: Comma-separated member names e.g. MK,AK
        remarks: Description of the expense
        vendor_bill_number: Bill/invoice number if available
        vendor_bill_date: Bill date if available
        split_ratio: Split ratio e.g. 1,1
        source_filename: Original receipt filename

    Returns:
        Confirmation with transaction ID and embedding status
    """
    try:
        # Validate inputs
        paid_by = paid_by.upper().strip()
        if paid_by not in VALID_MEMBERS:
            return {"status": "error", "message": f"Invalid paid_by: {paid_by}"}

        expense_owner = expense_owner.upper().strip()
        if expense_owner not in VALID_OWNERS:
            return {"status": "error", "message": f"Invalid expense_owner: {expense_owner}"}

        # Parse members and ratios
        members = [m.strip().upper() for m in split_between.split(",") if m.strip()]
        try:
            ratios = [int(r.strip()) for r in split_ratio.split(",") if r.strip()]
            if len(ratios) != len(members):
                ratios = [1] * len(members)
        except ValueError:
            ratios = [1] * len(members)

        # Calculate per person share
        per_person_share = round(float(amount) / len(members)) if members else int(amount)

        # Build search text for embedding
        owner_text = {
            "DAD":       "dad father parent care",
            "MOM":       "mom mother parent care",
            "HOUSEHOLD": "household utility bills",
            "FAMILY":    "family general expenses"
        }.get(expense_owner, "")

        search_text = f"{vendor} {expense_category} {remarks} {owner_text}"

        # Generate embedding
        embedding = get_embedding(search_text)

        # Build MongoDB document
        doc = {
            "household_id":     HOUSEHOLD_ID,
            "paid_by":          paid_by,
            "transaction_date": transaction_date,
            "amount":           int(float(amount)),
            "currency":         "INR",
            "expense_category": expense_category,
            "expense_owner":    expense_owner,
            "vendor":           vendor.upper(),
            "remarks":          remarks,
            "split_between":    members,
            "split_ratio":      ratios,
            "per_person_share": per_person_share,
            "source_type":      "receipt_image",
            "source_filename":  source_filename,
            "verified":         True,
            "search_text":      search_text,
            "created_at":       datetime.now(timezone.utc).isoformat(),
        }

        # Add optional fields
        if vendor_bill_number:
            doc["vendor_bill_number"] = vendor_bill_number
        if vendor_bill_date:
            doc["vendor_bill_date"] = vendor_bill_date
        if embedding:
            doc["search_text_embedding"] = embedding

        # Save to MongoDB
        collection = get_transactions()
        result = collection.insert_one(doc)

        return {
            "status": "success",
            "message": "✅ Transaction saved to MongoDB Atlas successfully",
            "transaction_id": str(result.inserted_id),
            "embedding_generated": embedding is not None,
            "summary": {
                "paid_by":          paid_by,
                "date":             transaction_date,
                "amount":           format_inr(int(float(amount))),
                "vendor":           vendor.upper(),
                "category":         expense_category,
                "expense_owner":    expense_owner,
                "split_between":    members,
                "per_person_share": format_inr(per_person_share),
                "source_filename":  source_filename,
                "now_searchable":   embedding is not None
            },
            "next_steps": (
                "Transaction is now saved and searchable via Vector Search. "
                "You can query it with natural language like "
                f"'Show me {expense_category} expenses' or "
                f"'Find {vendor} receipts'."
            )
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to save transaction: {str(e)}"
        }
