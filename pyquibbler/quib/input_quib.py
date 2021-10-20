from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Set, TYPE_CHECKING, List

from .assignment import AssignmentTemplate
from .assignment.assignment import PathComponent
from .quib import Quib
from .utils import is_there_a_quib_in_object
from ..env import DEBUG, PRETTY_REPR
from ..exceptions import DebugException


@dataclass
class CannotNestQuibInIQuibException(DebugException):
    iquib: InputQuib

    def __str__(self):
        return 'Cannot create an input quib that contains another quib'


class InputQuib(Quib):
    _DEFAULT_ALLOW_OVERRIDING = True

    def __init__(self, value: Any, assignment_template: Optional[AssignmentTemplate] = None):
        """
        Creates an InputQuib instance containing the given value.
        """
        super().__init__(assignment_template=assignment_template)
        self._value = value
        if DEBUG:
            if is_there_a_quib_in_object(value, force_recursive=True):
                raise CannotNestQuibInIQuibException(self)

    def _get_inner_value_valid_at_path(self, path: List[PathComponent]) -> Any:
        """
        No need to do any calculation, this is an input quib.
        """
        return self._value

    def _get_path_for_children_invalidation(self, invalidator_quib: 'Quib',
                                            path: List['PathComponent']) -> Optional[List[PathComponent]]:
        """
        If an input quib is invalidated at a certain path, we want to invalidate our children at that path- as we are
        not performing any change on it (as opposed to a transpositional quib)
        """
        return path

    def __repr__(self):
        if PRETTY_REPR:
            return self.pretty_repr()
        return f'<{self.__class__.__name__} ({self.get_value()})>'

    def pretty_repr(self):
        return f'iquib({self.get_value()})'

    @property
    def parents(self) -> Set[Quib]:
        return set()


iquib = InputQuib
