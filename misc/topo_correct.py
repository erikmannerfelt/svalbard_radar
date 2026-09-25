import numpy as np
import matplotlib.pyplot as plt
import scipy.interpolate
import scipy.ndimage
import xarray as xr
from pathlib import Path
import shutil

import svalbardradar.tools.misc

def resample(values: np.ndarray, new_shape: int) -> np.ndarray:
    # Correct off-by-one endpoint
    model = scipy.interpolate.interp1d(
        np.arange(values.shape[0]), values, fill_value="extrapolate"
    )
    return model(np.linspace(0, values.shape[0] - 1, new_shape))


def topocorr(radar_key: str, stepsize_m: float = 2.5, cut_min_height_masl: float | None = None, cut_max_depth: float | None = None) -> xr.Dataset:
    base_dir = Path(__file__).absolute().parents[1]

    glacier, date_str, filestem = radar_key.split("-")
    filepath = base_dir / f"processed_radar/{glacier}/{date_str}/{filestem}.nc"
    with xr.open_dataset(filepath) as data:
        data = svalbardradar.tools.misc.siglog_radargram(data.load())

        if cut_max_depth:
            # data = data.where(data["depth"] < cut_max_depth, drop=True)
            data = data.isel(y=data["depth"].values <= cut_max_depth)
        # data["data"] -= data["data"].isel(y=slice(600, None)).median("y")
        # Safer coordinate assignment
        if 'x' in data.dims:
            data = data.assign_coords(x=('x', np.arange(data.sizes['x'])))

        # Distance along track (meters)
        dE = np.r_[0, data['easting'].values[1:]  - data['easting'].values[:-1]]
        dN = np.r_[0, data['northing'].values[1:] - data['northing'].values[:-1]]
        dist = np.cumsum(np.hypot(dE, dN))  # shape (n_cols,)
        data['distance'] = xr.DataArray(dist, dims=('x',))
        # dist = data["distance"].values

        # Broadcast arrays / basic metrics
        # depths   = data['depth'].broadcast_like(data['data']).values       # (y,x)
        y_res    = float(data['depth'].diff('y').mean())
        elev_col = data['elevation'].values                                # (x,)
        # nrows, ncols = data['data'].shape

        # Uniform distance grid (this stretches gaps correctly)
        # dx_med  = float(data['distance'].diff('x').median())
        dx_med = stepsize_m
        d_min   = float(data['distance'].min())
        d_max   = float(data['distance'].max())
        x_shape = int(np.ceil((d_max - d_min) / dx_med)) * 2
        new_dist = np.linspace(d_min, d_max, x_shape)

        # Interpolators: distance -> original column index / surface elevation / row offset
        f_col = scipy.interpolate.interp1d(
            dist, np.arange(data["data"].shape[1]), kind='linear', bounds_error=False, fill_value='extrapolate'
        )
        f_surf = scipy.interpolate.interp1d(
            dist, elev_col, kind='linear', bounds_error=False, fill_value='extrapolate'
        )
        elev_rows = (elev_col - elev_col.max()) / y_res  # offset in row units
        f_elev = scipy.interpolate.interp1d(
            dist, elev_rows, kind='linear', bounds_error=False, fill_value='extrapolate'
        )

        # Evaluate on uniform distance
        new_cols   = f_col(new_dist)      # fractional original column indices
        new_elevs  = f_elev(new_dist)     # per-column vertical offsets (rows)
        surf_elevs = f_surf(new_dist)     # surface elevation (m a.s.l.) at each column

        # Global height range from original data (absolute elevation for each (y,x))
        heights = (data['elevation'].broadcast_like(data['data']) - data['depth']).values
        max_h = float(heights.max())
        min_h = float(heights.min())

        # --- Lower-bound cut: optional ---
        min_h_out = max(min_h, cut_min_height_masl) if cut_min_height_masl is not None else min_h

        # Build sampling grids for map_coordinates
        # Rows are aligned such that row index r corresponds to absolute height: H = max_h - r*y_res
        y_shape = int(np.ceil((max_h - min_h_out) / y_res))
        base_rows = np.repeat(np.arange(y_shape, dtype=float).reshape(-1,1), x_shape, axis=1)
        rows = base_rows + np.repeat(new_elevs.reshape(1,-1), y_shape, axis=0)
        cols = np.repeat(new_cols.reshape(1,-1), y_shape, axis=0)

        new_e = scipy.interpolate.interp1d(data["distance"].values, data["easting"].values)(new_dist)
        new_n = scipy.interpolate.interp1d(data["distance"].values, data["northing"].values)(new_dist)

        # Map the data; use constant fill with NaN for out-of-bounds
        mapped = scipy.ndimage.map_coordinates(
            data['data'].values, [rows, cols], order=1, mode='constant'#, cval=np.nan

        )[::-1]

        m = xr.DataArray(mapped, coords=[("elevation", np.linspace(min_h_out, max_h, mapped.shape[0])), ("distance", np.linspace(d_min, d_max, mapped.shape[1]))]).to_dataset(name="data")
        m["easting"] = "distance", new_e
        m["northing"] = "distance", new_n

        return m


def main(stepsize_m: float = 2.):

    base_dir = Path(__file__).absolute().parents[1]
    fps = [
        base_dir / "processed_radar/ragna_mariebreen/20240412/DAT_0404_A1_1.nc",
        base_dir / "processed_radar/mettebreen/20230305/DAT_0229_A1_1.nc",
    ]

    out_paths = {"-".join(fp.parts[-3:]).replace(".nc", ""): (base_dir / f"temp/{'-'.join(fp.parts[-3:]).replace('.nc', '')}_topocorr.nc") for fp in fps}

    if all(fp.is_file() for fp in out_paths.values()):
        return out_paths

    for i, (radar_key, out_path) in enumerate(out_paths.items()):
        if out_path.is_file():
            continue
        filepath = fps[i]

        cut_min_height_masl = 0.
        if "mettebreen" in radar_key:
            cut_min_height_masl = 150.
        elif "ragna_marie" in radar_key:
            cut_min_height_masl = 50.

        m = topocorr(radar_key, cut_min_height_masl=cut_min_height_masl)

        # # ---- user setting: cut elevation (m a.s.l.) ----
        # cut_min_height_masl = 50.  # e.g., set to 50.0 to skip anything below 50 m a.s.l.


            # temp_path = out_path.with_suffix(".tmp")
            # m.to_netcdf(out_path, encoding={"data": {"zlib": True, "complevel": 8}})
            # shutil.move(temp_path, out_path)
            # print(m)
            # continue


            # m.to_netcdf("temp/")
            # return


        # Plot
        # vlim = np.percentile(np.abs(data['data']), 97)
        plt.imshow(
            m.data, aspect="auto", vmin=-3, vmax=3, cmap="RdBu",
            extent=(m.distance.min()/1e3, m.distance.max()/1e3, m.elevation.min(), m.elevation.max()),
            origin='lower'
        )
        plt.xlabel("Distance (km)")
        plt.ylabel("Elevation (m a.s.l.)")
        plt.show()
    return out_paths


if __name__ == "__main__":
    main()