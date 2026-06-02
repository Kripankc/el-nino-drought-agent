import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Use /tmp when the root directory is read-only (Streamlit Cloud)
if not os.access(BASE_DIR, os.W_OK) or os.getenv("STREAMLIT_SHARING_MODE"):
    DB_PATH = os.path.join(tempfile.gettempdir(), "ensa.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "ensa.db")

os.makedirs(os.path.join(DATA_DIR, "cache"), exist_ok=True)

# Optional LLM credentials — only needed for the AI-enhanced narrative feature.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
