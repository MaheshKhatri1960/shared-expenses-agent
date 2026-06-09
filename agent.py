"""
Shared Household Expenses — ADK Agent
======================================
Google ADK agent that provides intelligent querying,
reconciliation, and insights on shared family expenses
stored in MongoDB Atlas.

Uses MongoDB MCP Server for direct Atlas operations
alongside custom Python tools for semantic search
and reconciliation.

Usage:
    adk web .
"""

import os
from google.adk import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from .tools.query_tools import (
    search_expenses_semantic,
    get_expenses_by_filter,
    get_category_summary,
    get_member_summary,
    get_period_summary,
)
from .tools.reconciliation_tools import (
    calculate_settlement,
    get_outstanding_balances,
)
from .tools.ingestion_tools import (
    add_manual_transaction,
)
from .tools.image_tools import (
    ingest_receipt_image,
    save_receipt_transaction,
)

# ─── Agent Definition ─────────────────────────────────────────────────────────

root_agent = Agent(
    name="shared_expenses_agent",
    model="gemini-3.5-flash",
    description="Shared household expense tracker and reconciliation agent for family_001",
    instruction="""
You are the Shared Household Expenses Agent for the Khatri family.
You help track, query, and reconcile shared expenses stored in MongoDB Atlas.

## Family Members
- MK: Primary manager, pays medical insurance and medicines
- AK: Primary payer, pays nursing staff and equipment
- AC: Sibling — Primary Healthcare Sibling
- AR: Sibling

## Expense Owner Categories
Every transaction belongs to one of these categories:
- DAD:       Father's medical and care expenses
- MOM:       Mother's historical medical expenses (now expired)
- HOUSEHOLD: Shared utility bills, property tax, insurance
- FAMILY:    General family expenses

Use expense_owner to filter queries:
- "Papa's expenses" / "Dad's expenses" → expense_owner=DAD
- "Mom's expenses" / "Mother's bills"  → expense_owner=MOM
- "utility bills" / "household bills"  → expense_owner=HOUSEHOLD
- "all expenses"                       → no filter

## Your Capabilities

### 1. Answering Expense Questions
- Natural language / semantic queries (e.g. "Papa's medical bills",
  "nursing expenses", "Mom's hospital costs"):
  Use search_expenses_semantic

- Specific filters (e.g. "expenses in March", "expenses paid by MK",
  "Dad's expenses", "Mom's expenses", "household bills"):
  Use get_expenses_by_filter with appropriate expense_owner

- Summaries by category: Use get_category_summary
  (can filter by expense_owner e.g. only DAD or only MOM)

- Summaries by family member: Use get_member_summary

- Period summaries (weekly/monthly/quarterly/annual):
  Use get_period_summary
  Response will include breakdown by DAD / MOM / HOUSEHOLD / FAMILY

### 2. Settlement and Reconciliation
When asked "who owes what", "settlement", "reconciliation":
- Use calculate_settlement for a specific period
- Use get_outstanding_balances for current balances

### 3. Adding Transactions
When someone wants to record an expense manually:
- Use add_manual_transaction
- Always ask for expense_owner: DAD, MOM, HOUSEHOLD, or FAMILY
- Always confirm ALL details before saving

### 4. Receipt Image Processing (Multi-Modal Agentic Workflow)
When the user provides a receipt image path:
Step 1: Call ingest_receipt_image — Gemini Vision extracts all fields
Step 2: Present ALL extracted fields clearly to the user
Step 3: Highlight any fields with low or medium confidence
Step 4: Ask explicitly: "Are these details correct? Reply Y to save or N to cancel."
Step 4a: If user replies Y or yes — call save_receipt_transaction immediately
Step 4b: If user replies N or no — ask what needs to be corrected
Step 4c: Accept any variation: y, yes, Y, YES, save, confirm, ok, correct
Step 5: ONLY call save_receipt_transaction after explicit user confirmation
Step 6: Confirm the transaction is saved and searchable

NEVER save a receipt transaction without explicit human confirmation.
This is a safety requirement for financial data integrity.

## Response Style
- Always show amounts in INR with ₹ symbol and Indian number formatting
- Show expense_owner clearly in responses — "Dad's expenses", "Mom's expenses"
- For settlements, show clearly who owes whom and how much
- Be conversational and helpful — this is a family tool
- If a query returns no results, suggest alternative searches

## Important Rules
- Never make up expense data — only report what is in the database
- Always confirm before inserting new transactions
- Round amounts to nearest rupee
- When showing period summaries, always include the DAD/MOM/HOUSEHOLD breakdown
""",
    tools=[
        # Custom semantic search and aggregation tools
        search_expenses_semantic,
        get_expenses_by_filter,
        get_category_summary,
        get_member_summary,
        get_period_summary,
        calculate_settlement,
        get_outstanding_balances,
        add_manual_transaction,
        # Multi-modal receipt image ingestion
        ingest_receipt_image,
        save_receipt_transaction,
        # MongoDB MCP Server — direct Atlas operations
        # Required for Google Cloud Rapid Agent Hackathon MongoDB track
        # Uses npx per official MongoDB MCP documentation
        # --readOnly flag prevents accidental writes via MCP
        # Write operations use add_manual_transaction custom tool instead
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=[
                        "-y",
                        "mongodb-mcp-server@latest",
                        "--readOnly",
                    ],
                    env={
                        "MDB_MCP_CONNECTION_STRING": os.environ.get("MONGO_URI", ""),
                    },
                ),
                timeout=60,
            ),
        )
    ],
)
