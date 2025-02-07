from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Union

from pyquibbler.assignment import AssignmentToQuib
from pyquibbler.project.undo_group import undo_group_mode
from pyquibbler.quib.graphics import aggregate_redraw_mode
from pyquibbler.utilities.basic_types import Flag


@dataclass
class QuibChangeWithOverrideRemovals:
    change: AssignmentToQuib
    override_removals: List[AssignmentToQuib]

    @property
    def quib(self):
        return self.change.quib


@dataclass
class OverrideGroup:
    """
    A group of overrides to be applied together, and the relevant override removals.
    When overriding a quib as a result of an upstream assignment,
    we remove overrides in all the indices that lead to the chosen override,
    so the override will actually cause the desired effect on the upstream quib.
    """
    quib_changes: List[AssignmentToQuib] = field(default_factory=list)

    def apply(self, temporarily: bool = False) -> Flag:
        with undo_group_mode(temporarily) as ugm, aggregate_redraw_mode(temporarily):
            for quib_change in self.quib_changes:
                quib_change.apply()
        return ugm

    def __bool__(self):
        return len(self.quib_changes) > 0

    def extend(self, extension: Union[OverrideGroup, List[AssignmentToQuib]]):
        """
        Add quib changes from a list or another override group.
        """
        if isinstance(extension, OverrideGroup):
            self.quib_changes.extend(extension.quib_changes)
        elif isinstance(extension, list):
            self.quib_changes.extend(extension)
        else:
            raise TypeError(type(extension))

    def __add__(self, other: OverrideGroup):
        if not isinstance(other, OverrideGroup):
            raise TypeError(type(other))
        return OverrideGroup(self.quib_changes + other.quib_changes)
