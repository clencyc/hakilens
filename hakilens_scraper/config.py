import os

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

settings = Settings()
