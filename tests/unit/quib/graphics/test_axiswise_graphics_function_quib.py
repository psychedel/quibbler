import numpy as np
from pytest import mark

from pyquibbler import iquib


def check_invalidation(func, indices_to_invalidate):
    """
    Run func on an ndarray iquib, change the iquib in the given indices,
    and verify that the invalidated indices were also the ones that changed values.
    Make sure that func works in a way that guarantees that when a value in the input changes,
    all affected values in the result also change.
    """
    arr = np.array([[[1, 2, 3], [4, 5, 6]]])
    data = iquib(arr)
    result = func(data)
    children = {idx: result[idx] for idx in np.ndindex(result.get_shape().get_value())}

    values = {idx: child.get_value() for idx, child in children.items()}
    data[indices_to_invalidate] = 999

    invalidated_result_indices = {idx for idx, child in children.items() if not child.is_cache_valid}
    new_values = {idx: child.get_value() for idx, child in children.items()}
    changed_result_indices = {idx for idx in new_values if not np.array_equal(values[idx], new_values[idx])}
    assert invalidated_result_indices == changed_result_indices


@mark.parametrize('indices_to_invalidate', [-1, 0, (0, 0), (0, 1, 2), ...])
@mark.parametrize('axis', [-1, (-1, 1), 0, 1, 2, (0, 2), (0, 1), None])
@mark.parametrize('keepdims', [True, False, None])
@mark.parametrize('where', [True, False, [[[True], [False]]], None])
def test_axiswise_invalidation_with_sum(indices_to_invalidate, axis, keepdims, where):
    kwargs = dict(axis=axis)
    if keepdims is not None:
        kwargs['keepdims'] = keepdims
    if where is not None:
        kwargs['where'] = where
    check_invalidation(lambda data: np.sum(data, **kwargs), indices_to_invalidate)


@mark.parametrize('indices_to_invalidate', [-1, 0, (0, 0), (0, 1, 2), ...])
@mark.parametrize('axis', [0, 1, 2, -1, -2])
@mark.parametrize('func_out_dims', [0, 1, 2])
def test_axiswise_invalidation_with_apply_along_axis(indices_to_invalidate, axis, func_out_dims):
    func1d = lambda slice: np.sum(slice).reshape((1,) * func_out_dims)
    check_invalidation(lambda data: np.apply_along_axis(func1d, axis, data), indices_to_invalidate)


@mark.parametrize('indices_to_invalidate', [-1, 0, (0, 0), (0, 1, 2), ...])
def test_axiswise_invalidation_with_vectorize(indices_to_invalidate):
    check_invalidation(lambda data: np.vectorize(lambda x: x)(data), indices_to_invalidate)
