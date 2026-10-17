import os

# Tests must not depend on a developer's personal .env file
os.environ.setdefault("MOCK_ADP_API_KEY", "test-key")

# Tests never send traces out, whatever .env says (load_dotenv won't override this)
os.environ["LANGSMITH_TRACING"] = "false"
