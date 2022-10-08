from dataclasses import dataclass
from typing import Any, List
from enum import Enum

import numpy as np


@dataclass
class PathComponent:
    component: Any
    extract_element_out_of_array: bool = False

    def referencing_field_in_field_array(self, type_) -> bool:
        """
        Indicated whether the component references a field in a field array
        """
        return (issubclass(type_, np.ndarray) and
                (isinstance(self.component, str) or
                 (isinstance(self.component, list) and isinstance(self.component[0], str))))

    def is_nd_reference(self):
        return isinstance(self.component, (bool, tuple, list, np.ndarray, SpecialComponent))

    def is_compound(self):
        return isinstance(self.component, tuple) and len(self.component) > 1

    def get_multi_step_path(self) -> 'Path':
        if not self.is_compound():
            return [self]
        return list(PathComponent(cmp) for cmp in self.component)

    def __eq__(self, other):
        from pyquibbler.utilities.iterators import recursively_compare_objects
        return isinstance(other, PathComponent) \
            and self.extract_element_out_of_array == other.extract_element_out_of_array \
            and recursively_compare_objects(self.component, other.component)

    def __repr__(self):
        s = repr(self.component)
        if self.extract_element_out_of_array:
            s = s + ' E'
        return '{' + s + '}'


class SpecialComponent(Enum):
    WHOLE = 'whole'  # whole object
    ALL = 'all'  # keep shape, change all elements
    SHAPE = 'shape'  # shape only


Path = List[PathComponent]

Paths = List[Path]
