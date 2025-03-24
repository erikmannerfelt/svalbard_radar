
# Run rsgpr with default settings
run-rsgpr:
    ipython process_radar.py

# Build all cached items
build-cache:
    ipython -c 'from format_radargrams import *; parse_all_radargrams(progress=True)'

# Rebuild all cached items
rebuild-cache:
    ipython -c 'from format_radargrams import *; parse_all_radargrams(progress=True, redo_cache=True)'

# Run the webserver
web:
    python webserver.py
    
# Run the webserver in debug mode
web-debug: 
    python -c 'from webserver import *; main(debug=True)'
