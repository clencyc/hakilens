try:
    from hakilens_scraper.api import app
    print('API imported successfully')
except Exception as e:
    print('API import error:', str(e))
    import traceback
    traceback.print_exc()
