import os

# Tests must not depend on a developer's personal .env file
os.environ.setdefault("MOCK_ADP_API_KEY", "test-key")
