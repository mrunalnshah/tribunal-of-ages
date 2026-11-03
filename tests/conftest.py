import os

# Tests must pass on every machine, whatever your .env or your terminal says. So the package
# skips your .env, and every setting goes back to its default: a test that needs another value
# passes it to Settings(...) itself.
os.environ["TRIBUNAL_DOTENV"] = "0"

from tribunal.config import Settings  # noqa: E402  (after the switch above, on purpose)

for name in Settings.model_fields:
    os.environ.pop(name.upper(), None)
os.environ["LANGFUSE_PUBLIC_KEY"] = ""  # and the tracing SDK, which reads its own keys
