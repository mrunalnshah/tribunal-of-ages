"""Tribunal of Ages: an AI court that judges petty modern grievances.

It cites laws from history, myth and fiction.
"""

import os

from dotenv import load_dotenv

# Load .env into os.environ once, so our settings and third-party SDKs see the same values.
# Variables that already exist win, so Docker, CI and Spaces secrets are never overridden.
# Tests set TRIBUNAL_DOTENV=0, so nothing in your .env can change their results.
if os.environ.get("TRIBUNAL_DOTENV") != "0":
    load_dotenv()
