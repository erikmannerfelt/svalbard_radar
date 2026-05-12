# Draft dataset publication from Mannerfelt et al., (submitted)
Titled: **Glacier thickness, thermal regime, and subjective uncertainty from ground-penetrating radar of 25 Svalbard glaciers**

### **NOTE**: This is a preliminary version that only contains radargrams from Filantropbreen and Fimbulisen for getting peer feedback on the data format.. All data will be available upon final publication of the paper.


## Dataset description

This repository contains ground-penetraing radar (GPR) data from 25 glaciers in Svalbard, associated with the publication Mannerfelt et al., (submitted).
It includes crowd-sourced consensus estimates of glacier thickness and thermal regime (defined by the cold-temperate transition surface; CTS).

An archival version of the crowd sourcing website is available at https://erikmannerfelt.github.io/svalbard_radar_web.
The source code is soon available at https://github.com/erikmannerfelt/svalbard_radar.

## Dataset organization
Its contents are:

* `thickness_cts_points.arrow`: Thickness and thermal regime (CTS) data for all profiles from crowd-sourced interpretation consensus estimates.
* `thickness_cts_points_csv.zip`: The same thickness and thermal regime data as above, but separated per profile in CSV files.
* `radargrams-*.zip`: A zipfile for each glacier, containing data for each radargram:
    - Raw (.rd3,.cor,.rad) data in a zipfile
    - Processed (.nc) data
    - The profile track (.geojson)
    - A thumbnail (picture) as it appeared on the website (.jpg)
    - A report showing the user interpretations and consensus for this radargram (.pdf) 
* `dems.zip`: Digital Elevation Models (DEMs) used for elevation coordinate correction
* `interpretation_lines.zip`: Interpretations (.json) submitted by users on the website.
* `interpretation_report.pdf`: A report showing the user interpretations and consensus for every radargram

Each profile's id (`radar_key`) is unique and is formed in the pattern `<glacier>-<date>-<filename>`.
The `<glacier>` part is a simplified version of the glacier's name (see `shapes/glacier_locations.geojson` in the code repository for locations and true names).
The `<date>` part is the acquisition date in the format YYYYMMDD.
The `<filename>` part is the stem of the first .rad filename (e.g. "DAT_0001_A1"), plus the amount of files that were merged by `ridal`,  (e.g. "_3" for three merged files).

### **NOTE**: The following radargrams will be made available here latest 1 July 2027. They are currently reserved for Enzenhofer et al. (in prep) (link to be added here):
- `mettebreen-20230305-DAT_0229_A1_1`
- `mettebreen-20230305-DAT_0235_A1_8`
- `ragna_mariebreen-20230305-DAT_0067_A1_1`
- `ragna_mariebreen-20230305-DAT_0068_A1_3`
- `edvardbreen-20230305-DAT_0230_A1_1`
- `edvardbreen-20230305-DAT_0234_A1_1`
- `edvardbreen-20230305-DAT_0232_A1_1`
- `rabotbreen-20250402-DAT_0068_A1_1`
- `rabotbreen-20250402-DAT_0071_A1_1`

## Thickness and thermal regime data description
The consensus data (`thickness_cts_points.arrow`) consist of tabular point data with the following fields:

* `radar_key`: The key shown on the website and in the radargram directory of the data publication
* `distance`: The distance  along the profile (m)
* `x`: The trace number of the point (in pixels)
* `thickness`: Glacier thickness consensus median (m)
* `easting`: The easting coordinate (EPSG:32633) (m)
* `northing`: The northing coordinate (EPSG:32633) (m)
* `elevation`: The elevation above sea level sampled from a DEM (m a.s.l.)
* `elevation_date`: The date of the elevation value (from a DEM).
* `part_idx`: Estimated part index (incremented in case case of data gaps)
* `antenna`: The antenna centre frequency that was used (MHz)
* `date_str`: The acqusition date in the format YYYYMMDD
* `time`: The exact acquisition timestamp of the trace according to the GNSS (in UTC, not GPS time).
* `temperate`: The median consensus height of the CTS above the bed (0 means no temperate ice, =`thickness` means 100% temperate) (m)
* `{temperate,thickness}_lower`: The lower (25%) total uncertainty bound of the variable (m)
* `{temperate,thickness}_upper`: The upper (75%) total uncertainty bound of the variable (m)
* `{temperate,thickness}_user_{std,nmad,lower,upper}`: The standard deviation/NMAD/lower (25%) bound/upper (75%) bound of the user consensus (m)
* `{temperate,thickness}_user_count`: The amount of users contributing to the consensus (m)
* `{temperate,thickness}_gpr_uncertainty`: The calculated GPR-related uncertainty component (m)
* `{temperate,thickness}_gnss_uncertainty`: The calculated GNSS-related uncertainty component (m)
* `{temperate,thickness}_{std,nmad}`: The standard deviation and NMAD including the GPR, GNSS and consensus uncertainty (see the `_user_` variables for only consensus variability) (m)
* `temperate_frac`: The fraction of the ice column that is covered by temperate ice (0-1; unitless)
* `temperate_frac_std`: The standard deviation of the temperate ice fraction (m)
* `bed_type`: Classified glacier bed type in the pattern `{uncertain,certain}_{cold,temperate}`. Certain means the user consensus range (25-75%) agrees and uncertain means that one of the two bounds disagree.
* `bed_elevation`: The elevation above sea level of the median glacier bed (m)
* `temperate_elevation`: The elevation above sea level of the median CTS (m a.s.l.)


The vertical CRS of elevation is identical to that used by the [Norwegian Polar Institute S0 DEM](https://doi.org/10.21334/NPOLAR.2014.DCE53A47) due to it being the co-registration reference.

The uncertainty estimate of the CTS is set to only be the consensus spread wherever there is a "certain cold" flag (i.e. where the 75% consensus percentile says 0% temperate). In all other areas, the uncertainty is a combination of of GPR, GNSS, and consensus uncertainties. This is done to reduce ambiguity in the interpretation of the uncertainty, as "certain cold" areas would otherwise misleadingly appear like they could be temperate due to the added instrument-related uncertainty.

## Interpretation line format description
Each user's interpretation (i.e. each time they pressed the "SUBMIT" button) is saved as a `.json`.
In the publication, only the most recent JSON was used.
The contents of the JSON files are:

- `radar_key`: The radar key (id) belonging to the interpretation
- `user`: The user's nickname
- `date_modified`: The submission date
- `difficulty`: The self-reported difficulty rating of the interpretation
- `comment`: An optional comment by the user
- `height`: The height of the radargram in pixels (for validation)
- `width`: The width of the radargram in pixels (for validation)
- `features`: A GeoJSON-conformative structure of the interpreted lines

Each line in the GeoJSON structure is defined by its coordinates (x and y from the upper left corner in pixels), and its `kind`. There are also `color` and `name` fields which are related to the `kind` field (see below). The kind defines the type of interpretation and can be:

- `bed_cold`, blue: "Glacier bed (no temperate ice)"
- `bed_unspecified`, purple: "Glacier bed"
- `temperate`, red: "Temperate ice"
- `bed_missing`, green: "Glacier bed not visible"

**NOTE**: The `name` field may not align with the final equivalent on the website due to changes throughout the project. In early submissions (pre-May), the `kind` field sometimes does not exist and is then only defined by its old name. See `svalbardradar/interpretations.py` in the source code for an example of how to handle these edge-cases.
