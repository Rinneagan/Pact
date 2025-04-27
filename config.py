import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Configuration
SERPAPI_KEY = os.getenv('SERPAPI_KEY', 'fdb20e84adcafd76bfed7714bf3dbff659c6deaa19193d4bc0c5697ceadd83cf')

# Application Settings
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser('~'), 'Downloads')
MAX_RETRIES = 3
TIMEOUT = 30  # seconds 