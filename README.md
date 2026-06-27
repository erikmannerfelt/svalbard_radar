## Code for processing, interpreting, analysing, and visualising ground-penetrating radar (GPR) data from 25 Svalbard glaciers, accompanying Mannerfelt et al. (in review)
**Titled**: Glacier thickness, thermal regime, and subjective uncertainty from ground-penetrating radar of 25 Svalbard glaciers

See our preprint here: [https://doi.org/10.31223/X5P19C](https://doi.org/10.31223/X5P19C).

This repo contains all code for processing, analyzing and visualizing Ground-Penetrating Radar (GPR) data from 25 glaciers in Svalbard. It also includes code for hosting the crowd-sourcing website that was part of the project. It supports the workflows used to generate the data publication products, comparisons, and figures described in the manuscript.

The data publication (see `svalbardradar/analysis.py::make_data_publication()`) is available here: https://doi.org/10.5281/zenodo.17882299. For published data products and field descriptions, see the Zenodo publication. This README focuses on the code and how to reproduce the results.

### Dependencies
Development was entirely done using [Nix](https://nixos.org/) and all dependencies are found in the `flake.nix` (Python, [ridal](https://github.com/erikmannerfelt/ridal), and nodejs for webserver dependencies). All Python dependencies are specified in a `requirements.txt`, though it may not be 100% compatible with the PyPi counterparts because they refer to the [nixpkgs](https://search.nixos.org/packages?channel=unstable) names. 

### Structure
- `svalbardradar/`:  Code module for preprocessing, processing, website data prep., and visualization (more below)
-  `misc/`: Miscellaneous scripts, for example to generate [GlaThiDa](https://gitlab.com/wgms/glathida/-/merge_requests/17)/[Glenglat](https://github.com/mjacqu/glenglat/issues/122) outputs
- `web/` and `webserver.py`: Files and scripts for the webpage

#### The `svalbardradar/` module

Below are the main scripts in the module, sorted in roughly chronological execution order
- `process_radar.py`: locate raw files and process them with [ridal](https://github.com/erikmannerfelt/ridal).
- `format_radargrams.py`: convert processed radargrams into a website-ready format.
- `interpretations.py`: handle and merge user interpretations into consensus point products.
- `analysis.py`: generate statistics and the data publication.
- `comparisons.py`: compare observations to inversion products / archival thickness.
- `figures.py`: make manuscript figures and summary statistics.

#### Notes
- This has only been developed and tested in the Nix environment and may have issues with other versions
- Some scripts currently assume local file paths / unpublished raw data organization. This would need fixing for full reproducibility.

### How to reproduce the results

1. Reproduce the environment. Easiest: `nix develop`, but should be fixable with other tools as mentioned above
2. Process the radar data: 
```bash
just run-ridal
```
3. In case of re-interpretation: start the webserver (needs a `PRIVATEKEY` environment variable for passwords)
```bash
just web
```
4. Make all the figures and tables (some processing overlap between the commands)
```bash
just make-figures
just build-all-statistics
```
5. Make the data publication
```bash
just make-data-publications
```

### Outputs

- `figures/`: Figures for the publication
- `tables/`: Values for the tables in the publication
- `processed_radar/`: Processed radargrams as NetCDF files
- Publication assets for Zenodo / GlaThiDa / glenglat

### Citation
Please cite the paper once published (will be linked here). Until then, please cite the data publication: 
> Mannerfelt et al. (2026): Dataset for: Glacier thickness, thermal regime, and subjective uncertainty from ground-penetrating radar of 25 Svalbard glaciers. Zenodo. https://doi.org/10.5281/zenodo.17882299
