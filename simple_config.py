import os

# Simple settings class
class Settings:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///data/hakilens.db")

settings = Settings()
print("Settings created successfully")
