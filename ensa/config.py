import os
from dotenv import load_dotenv

load_dotenv()

# Project Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Serverless Compatibility: Use OS temp directory if root folder is read-only
import tempfile
if not os.access(BASE_DIR, os.W_OK) or os.getenv("STREAMLIT_SHARING_MODE"):
    DB_PATH = os.path.join(tempfile.gettempdir(), "ensa.db")
    print(f"[Config] Base directory read-only. Using temp database path: {DB_PATH}")
else:
    DB_PATH = os.path.join(BASE_DIR, "ensa.db")

# Ensure Data Directories Exist
os.makedirs(os.path.join(DATA_DIR, "boundaries"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "crop_masks"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "cache"), exist_ok=True)

# Target Region: Zambia (Southern & Eastern Provinces)
# Bounding Box format: [min_lon, min_lat, max_lon, max_lat]
ZAMBIA_BBOX = [22.0, -18.0, 33.5, -8.0]
SOUTHERN_PROVINCE_BBOX = [25.0, -18.0, 29.0, -15.0]

# Season Parameters: White Maize
MAIZE_SEASON_START = "11-01"  # November 1st (Start of cropping season)
MAIZE_SEASON_END = "04-30"    # April 30th (End of season)

# API Configurations
CDS_API_URL = os.getenv("CDS_API_URL", "https://cds.climate.copernicus.eu/api/v2")
CDS_API_KEY = os.getenv("CDS_API_KEY", "")

CDSE_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"

# LLM Configurations
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai or anthropic
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
