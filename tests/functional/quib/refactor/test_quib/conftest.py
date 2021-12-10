from unittest import mock

import pytest

from pyquibbler.quib.refactor.factory import create_quib
from pyquibbler.quib.refactor.quib import Quib
from pyquibbler.overriding.overriding import override_third_party_funcs


@pytest.fixture(autouse=True)
def override_all():
    override_third_party_funcs()


@pytest.fixture
def create_quib_with_return_value():
    def _create(ret_val, allow_overriding=False):
        return create_quib(mock.Mock(return_value=ret_val), allow_overriding=allow_overriding)
    return _create


@pytest.fixture()
def quib():
    return Quib(
        func=mock.Mock(return_value=[1, 2, 3]),
        args=tuple(),
        kwargs={},
        allow_overriding=False,
        assignment_template=None,
        cache_behavior=None,
        is_known_graphics_func=False,
        name=None,
        line_no=None,
        file_name=None,
        is_random_func=False
    )


@pytest.fixture()
def graphics_quib(quib):
    return create_quib(
        func=mock.Mock(),
        args=(quib,),
        kwargs={},
        is_known_graphics_func=True
    )


@pytest.fixture
def axes():
    from matplotlib import pyplot as plt
    plt.close("all")
    plt.gcf().set_size_inches(8, 6)
    return plt.gca()


@pytest.fixture()
def mock_axes():
    axes = mock.Mock()
    axes.figure.canvas.supports_blit = False
    axes.artists = []
    return axes
