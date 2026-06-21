import os
import sys
from dotenv import load_dotenv

# Load environment variables from multiple possible .env locations:
# 1. User home profile .pact directory
pact_dir = os.path.join(os.path.expanduser("~"), ".pact")
user_env_path = os.path.join(pact_dir, ".env")
if os.path.exists(user_env_path):
    load_dotenv(user_env_path)

# 2. Executable directory (or script directory in dev)
if getattr(sys, 'frozen', False):
    exe_dir = os.path.dirname(sys.executable)
else:
    exe_dir = os.path.dirname(os.path.abspath(__file__))

exe_env_path = os.path.join(exe_dir, ".env")
if os.path.exists(exe_env_path):
    load_dotenv(exe_env_path)

# 3. Current working directory fallback
load_dotenv()

# API Configuration
SERPAPI_KEY = os.getenv('SERPAPI_KEY', '')

# Application Settings
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser('~'), 'Documents')
MAX_RETRIES = 3
TIMEOUT = 30  # seconds
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_CONCURRENT_DOWNLOADS = 3
MAX_SEARCH_RESULTS = 50  # Maximum number of search results to return 