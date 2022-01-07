import numpy as np
import pytest

from pyquibbler import CacheBehavior
from pyquibbler.refactor.path import PathComponent
from tests.functional.refactor.quib.test_quib.get_value.test_apply_along_axis import parametrize_keepdims, \
    parametrize_where, parametrize_data
from tests.functional.refactor.quib.test_quib.get_value.utils import collecting_quib, check_get_value_valid_at_path


def test_reduction_function_gets_whole_value_of_non_data_source_parents():
    # This is also a regression to handling 0 data source quibs
    non_data = collecting_quib(0)
    fquib = np.sum([1, 2, 3], axis=non_data)
    fquib.set_cache_behavior(CacheBehavior.OFF)
    with non_data.collect_valid_paths() as valid_paths:
        fquib.get_value()

    assert valid_paths == [[]]


def test_reduction_function_gets_whole_value_of_data_source_parents_when_whole_value_changed():
    data = collecting_quib([1, 2, 3])
    fquib = np.sum(data)
    fquib.set_cache_behavior(CacheBehavior.OFF)
    with data.collect_valid_paths() as valid_paths:
        fquib.get_value()

    assert valid_paths == [[]]


@parametrize_data
@pytest.mark.parametrize(['axis', 'indices_to_get_value_at'], [
    (-1, 0),
    ((-1, 1), 1),
    (0, 0),
    (1, (1, 0)),
    (2, (0, 0)),
    ((0, 2), -1),
    ((0, 1), 0),
    (None, ...),
])
@parametrize_keepdims
@parametrize_where
def test_reduction_axiswise_get_value_valid_at_path(axis, data, keepdims, where, indices_to_get_value_at):
    kwargs = dict(axis=axis)
    if keepdims is not None:
        kwargs['keepdims'] = keepdims
    if where is not None:
        kwargs['where'] = where
    path_to_get_value_at = [PathComponent(np.ndarray, indices_to_get_value_at)]
    check_get_value_valid_at_path(lambda quib: np.sum(quib, **kwargs), data, path_to_get_value_at)
