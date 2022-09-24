from __future__ import annotations
from typing import Any, Tuple, Dict

from pyquibbler.utilities.numpy_original_functions import np_zeros

import numpy as np


Args = Tuple[Any, ...]
Kwargs = Dict[str, Any]
Shape = Tuple[int, ...]


def create_bool_mask_with_true_at_indices(shape: Shape, indices: Any) -> np.ndarray:
    """
    Create an array of False in a given shape with True at `indices`.
    """
    res = np_zeros(shape, dtype=bool)
    res[indices] = True
    return res


def unbroadcast_bool_mask(bool_mask: np.ndarray, original_shape: Shape) -> np.ndarray:
    """
    Given a bool mask representing changes in an array which is a result of a broadcast, return an "un-broadcast"
    array in the given original shape (the shape before broadcasting) in which each boolean is true
    if any of its broadcast bools was true.
    """
    new_broadcast_ndim = bool_mask.ndim - len(original_shape)
    assert new_broadcast_ndim >= 0
    new_broadcast_axes = tuple(range(0, new_broadcast_ndim))
    reduced_bool_mask = np.any(bool_mask, axis=new_broadcast_axes)
    broadcast_loop_dimensions_to_reduce = tuple(i for i, (result_len, quib_len) in
                                                enumerate(zip(reduced_bool_mask.shape, original_shape))
                                                if result_len != quib_len)
    reduced_bool_mask = np.any(reduced_bool_mask, axis=broadcast_loop_dimensions_to_reduce, keepdims=True)
    return np.broadcast_to(reduced_bool_mask, original_shape)
