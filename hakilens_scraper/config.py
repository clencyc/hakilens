import os
from pathlib import Path

class Settings:
    def __init__(self):
        # API keys
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        
        # Database
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///data/hakilens.db")
        
        # HTTP client settings
        self.user_agent = os.getenv("USER_AGENT", "HakilensScraper/1.0")
        self.requests_per_minute = int(os.getenv("REQUESTS_PER_MINUTE", "15"))
        self.request_timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY")
        
        # Storage directories
        self.storage_dir = Path(os.getenv("STORAGE_DIR", "./data"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # File subdirectories
        self.files_dir = self.storage_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        
        self.html_dir = self.files_dir / "html"
        self.html_dir.mkdir(parents=True, exist_ok=True)
        
        self.pdf_dir = self.files_dir / "pdf"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        
        self.image_dir = self.files_dir / "images"
        self.image_dir.mkdir(parents=True, exist_ok=True)
        
        self.xml_dir = self.files_dir / "xml"
        self.xml_dir.mkdir(parents=True, exist_ok=True)

settings = Settings()
