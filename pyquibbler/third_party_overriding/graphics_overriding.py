import functools
from dataclasses import dataclass

from typing import Dict, Any

import matplotlib
from matplotlib.axes import Axes

from pyquibbler.third_party_overriding.definitions import OverrideDefinition


@dataclass
class GraphicsOverrideDefinition(OverrideDefinition):

    @property
    def _default_creation_flags(self) -> Dict[str, Any]:
        return dict(
            is_known_graphics_func=True,
            evaluate_now=True
        )


AxesOverrideDefinition = functools.partial(GraphicsOverrideDefinition, module_or_cls=Axes)


GRAPHICS_DEFINITIONS = [
    AxesOverrideDefinition(
        func_name="plot"
    )
]
