from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Union, Any

from pyquibbler.assignment import Assignment
from pyquibbler.function_definitions import FuncCall
from pyquibbler.path.data_accessing import deep_set
from pyquibbler.path_translation.source_func_call import SourceFuncCall

from .exceptions import FailedToInvertException


class Inverter(ABC):

    def __init__(self, func_call: Union[FuncCall, SourceFuncCall],
                 assignment: Assignment,
                 previous_result: Any):
        self._func_call = func_call
        self._assignment = assignment
        self._previous_result = previous_result

    def _raise_faile_to_invert_exception(self):
        raise FailedToInvertException(self._func_call)

    @abstractmethod
    def get_inversals(self):
        pass

    def _get_result_with_assignment_set(self):
        return deep_set(self._previous_result, self._assignment.path, self._assignment.value,
                        should_copy_objects_referenced=True)
