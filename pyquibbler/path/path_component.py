from dataclasses import dataclass
from typing import Type, Any, List

import numpy as np


@dataclass
class PathComponent:
    indexed_cls: Type
    component: Any

    def references_field_in_field_array(self) -> bool:
        """
        Whether or not the component references a field in a field array
        It's important to note that this method is necessary as we need to dynamically decide whether a __setitem__
        assignment is a field assignment or not. This is in contrast to setattr for example where we could have had a
        special PathComponent for it, as the interface for setting an attribute is different.
        """
        return (issubclass(self.indexed_cls, np.ndarray) and
                (isinstance(self.component, str) or
                 (isinstance(self.component, list) and isinstance(self.component[0], str))))


Path = List[PathComponent]

Paths = List[Path]
