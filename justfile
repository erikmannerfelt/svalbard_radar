
# Run rsgpr with default settings
run-ridal:
    ipython svalbardradar/process_radar.py

# Build all cached items
build-cache:
    ipython -c 'from svalbardradar.format_radargrams import *; print(len(parse_all_radargrams(progress=True)))'

# Rebuild all cached items
rebuild-cache:
    ipython -c 'from svalbardradar.format_radargrams import *; print(len(parse_all_radargrams(progress=True, redo_cache=True)))'

# Run the webserver
web:
    python webserver.py
    
# Run the webserver in debug mode
web-debug: 
    python -c 'from webserver import *; main(debug=True)'

rebuild-user-interpretations:
    ipython -c 'from svalbardradar.interpretations import *; merge_all_interpretations(overwrite_cache=True)'
    ipython -c 'from svalbardradar.comparisons import *; sample_models(overwrite_cache=True)'

make-figures:
    ipython svalbardradar/figures.py

make-user-report:
    ipython -c 'from svalbardradar.figures import *; plot_user_spread()'

build-all-statistics:
    rm -f tables/statistics.json
    ipython -c 'from svalbardradar.analysis import *; contribution_stats()'
    ipython -c 'from svalbardradar.analysis import *; data_stats()'
    ipython -c 'from svalbardradar.analysis import *; cts_transition_steepness()'
    ipython -c 'from svalbardradar.analysis import *; glacier_table()'
    ipython -c 'from svalbardradar.figures import *; plot_crossover_difference(show=False)'
    ipython -c 'from svalbardradar.figures import *; plot_glathida_comparison(show=False, correct_topo=True)'
    ipython -c 'from svalbardradar.figures import *; plot_model_comparison(show=False, correct_topo=True)'
    ipython -c 'from svalbardradar.figures import *; plot_model_temperate_cold_performance(show=False)'

make-data-publications:
    ipython -c 'from svalbardradar.analysis import *; make_data_publication()'
    ipython misc/glathida_submission.py
    ipython misc/glenglat_submission.py
