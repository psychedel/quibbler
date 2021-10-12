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
        return not issubclass(component.indexed_cls, np.ndarray) or component.references_field_in_field_array()

    def _represents_translatable_numpy_indexing(self, component):
        return issubclass(component.indexed_cls, np.ndarray) and not component.references_field_in_field_array()

    def _translate_and_invalidate(self, invalidator_quib, path):
        boolean_mask = self._get_boolean_mask_representing_new_indices_of_quib(invalidator_quib, path[0])
        if np.any(boolean_mask):
            new_path = [PathComponent(indexed_cls=self.get_type(), component=boolean_mask), *path[1:]]
            super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                       path=new_path)

    def _check_indices_equality_and_invalidate(self, path):
        working_component = path[0]
        if self.args[1] == working_component.component:
            super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                       path=path[1:])

    def _pass_and_invalidate(self, path):
        super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
                                                                   path=path)

    def _invalidate_with_children(self, invalidator_quib, path: List[PathComponent]):
        """

        :param invalidator_quib:
        :param path:
        :return:
        """

        """
        There are three things we can potentially do: 
        1. If we're getitem, equalize where our invalidator quib (which is the quib we're getitem'ing) was invalidated
        and our indices. If they're the same, drop it from the path and invalidate our children
        2. If we're getitem, take where our invalidator quib was invalidated and pass it on to our children
        3. Translate the indices if possible
        """
        if len(path) == 0:
            return super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self, path=[])

        working_component = path[0]
        if self.func == getitem:
            getitem_path_component = PathComponent(component=self._args[1], indexed_cls=invalidator_quib.get_type())
            if self._represents_translatable_numpy_indexing(getitem_path_component) and self._represents_translatable_numpy_indexing(working_component):
                # We're both numpy indicing; we can translate!
                # [This means invalidator was numpy, this getitem's result is numpy array, no fields]
                return self._translate_and_invalidate(invalidator_quib, path)
            elif not issubclass(invalidator_quib.get_type(), np.ndarray):
                # Our invalidator was NOT a numpy array- we check pure equality and invalidate by that
                # [this means invalidator was not numpy, this getitem's is anything, potentially fields/indices]
                return self._check_indices_equality_and_invalidate(path)
            elif self._represents_translatable_numpy_indexing(getitem_path_component):
                # Our invalidator did NOT represent numpy indicing, but WAS a numpy array
                # [this means invalidator was numpy, this getitem's is numpy, get item is translatable indices, invalidator is a field]
                self._pass_and_invalidate(path)
            elif not issubclass(self.get_type(), np.ndarray):
                return self._check_indices_equality_and_invalidate(path)
            elif self._represents_translatable_numpy_indexing(working_component):
                # Our invalidator DID represent numpy indicing, and WAS a numpy array, we are
                # [this means invalidator was numpy, this getitem's is numpy, get item is NOT translatable indices, the invalidator's are]
                self._pass_and_invalidate(path)
        else:
            # Any other situation ->
            assert issubclass(self.get_type(), np.ndarray)
            if not self._represents_translatable_numpy_indexing(working_component):
                return self._pass_and_invalidate(path)
            return self._translate_and_invalidate(invalidator_quib, path)

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





"""
{
    a: np.array()
}

"""
# def _invalidate_with_children(self, invalidator_quib, path: List[PathComponent]):
#     component = path[0]
#
#     if self.func == getitem:
#         # If we're a getitem, there are two options:
#         # 1. We're both non numpy indexing (meaning we can't create bool masks), so
#         #   a. If we're equal, invalidate
#         #   b. If we're not, don't
#         # 2. We're not BOTH non numpy- continue
#         getitem_path_component = PathComponent(component=self._args[1], indexed_cls=self.get_type())
#
#         if self._represent_non_numpy_indexing(component) and self._represent_non_numpy_indexing(getitem_path_component):
#             if self.args[1] == component.component or self.args[1] is Ellipsis or component.component is Ellipsis:
#                 super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
#                                                                            path=[PathComponent(component=...,
#                                                                                                indexed_cls=self.get_type()),
#                                                                                  *path[1:]])
#                 return
#             else:
#                 # Do nothing, this is on purpose
#                 return
#         else:
#             if self._represent_non_numpy_indexing(component):
#                 # The getitem does represent numpy indices- which means we are entirely invalidated, and the key should
#                 # continue on
#                 super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
#                                                                            path=path)
#                 return
#             else:
#                 # Continue on, this is on purpose:
#                 pass
#
#     # The component is non numpy indexing- we won't be able to create a bool mask
#     if self._represent_non_numpy_indexing(component):
#         super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
#                                                                    path=path)
#         return
#
#     # if self.func == getitem and (component.references_field_in_field_array()
#     #                              or not issubclass(component.indexed_cls, np.ndarray)):
#     #     # We can't run normal our operation to get a boolean mask representing new indices, since our key is a
#     #     # string- this may mean we're a dict, in which case we can't run the boolean mask op,
#     #     # or we're in a field array, in which case we can't create a boolean mask to work with our key unless we
#     #     # have the dtype (which we dont')
#     #     if self.args[1] == component.component:
#     #         super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
#     #                                                                    path=[PathComponent(component=...,
#     #                                                                                        indexed_cls=self.get_type()), *path[1:]])
#     #     return
#
#     boolean_mask = self._get_boolean_mask_representing_new_indices_of_quib(invalidator_quib, path[0])
#     if np.any(boolean_mask):
#         new_path = [PathComponent(indexed_cls=self.get_type(), component=boolean_mask), *path[1:]]
#         super(TranspositionalQuib, self)._invalidate_with_children(invalidator_quib=self,
#                                                                    path=new_path)
