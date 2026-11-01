"""Tribunal of Ages: an AI court that judges petty modern grievances.

It cites laws from history, myth and fiction.
"""

from dotenv import load_dotenv

# Load .env into os.environ once, so our settings and third-party SDKs see the same values.
# Variables that already exist win, so Docker, CI and Spaces secrets are never overridden.
load_dotenv()
