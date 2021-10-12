import functools
from operator import getitem
from typing import TYPE_CHECKING, List

import numpy as np

from pyquibbler.quib.assignment import Assignment
from .default_function_quib import DefaultFunctionQuib
from pyquibbler.quib.assignment.reverse_assignment import TranspositionalReverser
from pyquibbler.quib.assignment.reverse_assignment.utils import create_empty_array_with_values_at_indices
from pyquibbler.quib.utils import iter_objects_of_type_in_object_shallowly, recursively_run_func_on_object, \
    call_func_with_quib_values
from ..assignment.assignment import PathComponent

if TYPE_CHECKING:
    from .. import Quib


class TranspositionalQuib(DefaultFunctionQuib):
    """
    A quib that represents any transposition function- a function that moves elements (but commits no operation on
    them)
    """

    # A mapping between functions and indices of args that can change
    SUPPORTED_FUNCTIONS_TO_POTENTIALLY_CHANGED_QUIB_INDICES = {
        np.rot90: {0},
        np.concatenate: {0},
        np.repeat: {0},
        np.full: {1},
        getitem: {0},
        np.reshape: {0}
    }

    def _get_boolean_mask_representing_new_indices_of_quib(self, quib: 'Quib', path_component: PathComponent) -> np.ndarray:
        """
        Get a boolean mask representing all new indices of the quib after having passed through the function.
        The boolean mask will be in the shape of the final result of the function
        """
        def _replace_arg_with_corresponding_mask_or_arg(q):
            if q in self.get_quibs_which_can_change():
                if q is quib:
                    return create_empty_array_with_values_at_indices(
                        quib.get_shape().get_value(),
                        indices=path_component.component,
                        value=True,
                        empty_value=False
                    )
                else:
                    return np.full(q.get_shape().get_value(), False)
            return q

        new_arguments = recursively_run_func_on_object(
            func=_replace_arg_with_corresponding_mask_or_arg,
            obj=self._args
        )
        return call_func_with_quib_values(self._func, new_arguments, self._kwargs)

    def _represent_non_numpy_indexing(self, component):
        return not component.references_field_in_field_array() and issubclass(component.indexed_cls, np.ndarray)

    def _invalidate_with_children(self, invalidator_quib, path: List[PathComponent]):
        component = path[0]

        if self.func == getitem:
            # If we're a getitem, there are two options:
            # 1. We're both non numpy indexing (meaning we can't create bool masks), so
            #   a. If we're equal, invalidate
            #   b. If we're not, don't
            # 2. We're not BOTH non numpy- continue
            getitem_path_component = PathComponent(component=self._args[1], indexed_cls=self.get_type())
            if self._represent_non_numpy_indexing(component) and self._represent_non_numpy_indexing(getitem_path_component):
                if self.args[1] == component.component:
                    super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                               path=[PathComponent(component=...,
                                                                                                   indexed_cls=self.get_type()),
                                                                                     *path[1:]])
                    return
                else:
                    # Do nothing, this is on purpose
                    return
            else:
                if self._represent_non_numpy_indexing(component):
                    # The getitem does represent numpy indices- which means we are entirely invalidated, and the key should
                    # continue on
                    super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                               path=path)
                else:
                    # The component invalidating does represent numpy indices, we don't- which means we need to send the path
                    # on
                    super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                               path=path)
                return

        # The component is non numpy indexing- we won't be able to create a bool mask
        if self._represent_non_numpy_indexing(component):
            super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                       path=path)
            return

        # if self.func == getitem and (component.references_field_in_field_array()
        #                              or not issubclass(component.indexed_cls, np.ndarray)):
        #     # We can't run normal our operation to get a boolean mask representing new indices, since our key is a
        #     # string- this may mean we're a dict, in which case we can't run the boolean mask op,
        #     # or we're in a field array, in which case we can't create a boolean mask to work with our key unless we
        #     # have the dtype (which we dont')
        #     if self.args[1] == component.component:
        #         super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
        #                                                                    path=[PathComponent(component=...,
        #                                                                                        indexed_cls=self.get_type()), *path[1:]])
        #     return

        boolean_mask = self._get_boolean_mask_representing_new_indices_of_quib(invalidator_quib, path[0])
        if np.any(boolean_mask):
            new_path = [PathComponent(indexed_cls=self.get_type(), component=boolean_mask), *path[1:]]
            super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                       path=new_path)

    @functools.lru_cache()
    def get_quibs_which_can_change(self):
        """
        Return a list of quibs that can potentially change as a result of the transpositional function- this does NOT
        necessarily mean these quibs will in fact be changed.

        For example, in `np.repeat(q1, q2)`, where q1 is a numpy array quib
        and q2 is a number quib with amount of times to repeat, q2 cannot in any
        situation be changed by a change in `np.repeat`'s result. So only `q1` would be returned.
        """
        from pyquibbler.quib import Quib
        potentially_changed_quib_indices = self.SUPPORTED_FUNCTIONS_TO_POTENTIALLY_CHANGED_QUIB_INDICES[self._func]
        quibs = []
        for i, arg in enumerate(self._args):
            if i in potentially_changed_quib_indices:
                quibs.extend(iter_objects_of_type_in_object_shallowly(Quib, arg))
        return quibs

    def get_reversals_for_assignment(self, assignment: Assignment):
        return TranspositionalReverser.create_and_get_reversed_quibs_with_assignments(
            assignment=assignment,
            function_quib=self
        )
