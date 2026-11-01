import os

# Tests must never send traces, whatever your .env says. (load_dotenv won't override this.)
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
