import numpy as np

def nmad(values):
    return 1.426 * np.nanmedian(np.abs(values - np.nanmedian(values)))
