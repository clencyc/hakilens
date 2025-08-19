from hakilens_scraper.api import app

# Production configuration
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


