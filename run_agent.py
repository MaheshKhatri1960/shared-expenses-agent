"""
Run the Shared Expenses ADK Agent.

TWO ways to run:

Option A — ADK Web UI (RECOMMENDED for demo):
    adk web .
    Then open http://localhost:8000 in your browser

Option B — ADK CLI:
    adk run .

Option C — Python programmatic (for testing):
    python run_agent.py

Before running any option, set your MongoDB password below.
"""

import os
import sys
import asyncio

# ─── Set Environment Variables ────────────────────────────────────────────────
# Replace YOUR_PASSWORD with your actual Atlas password

MONGO_PASSWORD = "*subkuchnayahai9#"  # ← Replace this

os.environ["MONGO_URI"] = (
    f"mongodb+srv://mahesh:{MONGO_PASSWORD}"
    f"@cluster0.0qjbym8.mongodb.net/"
    f"?appName=Cluster0"
)
os.environ["GCP_PROJECT"]  = "shared-expenses-498507"
os.environ["GCP_LOCATION"] = "us-central1"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"

# ─── Connection Verification ──────────────────────────────────────────────────

def verify_mongodb():
    """Quick connection test."""
    try:
        from pymongo import MongoClient
        from pymongo.server_api import ServerApi
        client = MongoClient(os.environ["MONGO_URI"], server_api=ServerApi("1"))
        count = client["household_expenses"]["transactions"].count_documents({})
        print(f"  ✅ MongoDB Atlas — {count} transactions found")
        client.close()
        return True
    except Exception as e:
        print(f"  ❌ MongoDB connection failed: {e}")
        return False

def verify_vertex():
    """Quick Vertex AI test."""
    try:
        import vertexai
        vertexai.init(
            project=os.environ["GCP_PROJECT"],
            location=os.environ["GCP_LOCATION"]
        )
        print(f"  ✅ Vertex AI — project: {os.environ['GCP_PROJECT']}")
        return True
    except Exception as e:
        print(f"  ⚠️  Vertex AI warning: {e}")
        return False

# ─── Programmatic Runner (Option C) ──────────────────────────────────────────

async def run_programmatic():
    """Run agent programmatically with async runner."""
    from google.adk import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from agent import root_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        state={},
        app_name="shared_expenses_agent",
        user_id="mahesh"
    )

    runner = Runner(
        agent=root_agent,
        app_name="shared_expenses_agent",
        session_service=session_service
    )

    print("\nType your question (or 'quit' to exit):\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        content = types.Content(
            role="user",
            parts=[types.Part(text=user_input)]
        )

        try:
            async for event in runner.run_async(
                user_id="mahesh",
                session_id=session.id,
                new_message=content
            ):
                if event.is_final_response():
                    response = event.content.parts[0].text
                    print(f"\nAgent: {response}\n")
        except Exception as e:
            print(f"\n⚠️  Error: {e}\n")

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Shared Household Expenses — ADK Agent")
    print("="*60)

    if MONGO_PASSWORD == "YOUR_PASSWORD_HERE":
        print("\n❌ Please set MONGO_PASSWORD in run_agent.py")
        print("   Open the file and replace YOUR_PASSWORD_HERE")
        sys.exit(1)

    print("\n🔌 Verifying connections...")
    mongo_ok = verify_mongodb()
    verify_vertex()

    if not mongo_ok:
        print("\n❌ Cannot start — MongoDB connection failed")
        print("   Check your MONGO_PASSWORD")
        sys.exit(1)

    print("\n" + "─"*60)
    print("  HOW TO RUN (choose one):")
    print("")
    print("  OPTION A — Web UI with chat interface (BEST for demo):")
    print("    adk web .")
    print("    Then open http://localhost:8000")
    print("")
    print("  OPTION B — Command line:")
    print("    adk run .")
    print("")
    print("  OPTION C — Running programmatic mode now...")
    print("─"*60)
    print("")
    print("  Try asking:")
    print("  • How much did we spend on nursing staff?")
    print("  • Show me all Papa's medical expenses")
    print("  • Calculate settlement for all time")
    print("  • Who paid the most?")
    print("  • Category breakdown of all expenses")
    print("─"*60 + "\n")

    asyncio.run(run_programmatic())
