import numpy as np


def nmad(values):
    return 1.4826 * np.nanmedian(np.abs(values - np.nanmedian(values)))
