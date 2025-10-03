import traceback
import sys

try:
    import hakilens_scraper.config
    print('Import successful')
    print('Module contents:', dir(hakilens_scraper.config))
    if hasattr(hakilens_scraper.config, 'settings'):
        print('Settings object found:', type(hakilens_scraper.config.settings))
    else:
        print('Settings object not found in module')
except Exception as e:
    print('Error:', e)
    traceback.print_exc()
