import copy
import dataclasses
from functools import wraps

from typing import Any, Union, Tuple, Optional

import numpy as np

from pyquibbler.function_definitions import KeywordArgument, SourceLocation
from pyquibbler.path import Path, deep_set, split_path_at_end_of_object, deep_get
from pyquibbler.function_definitions.func_call import FuncCall, FuncArgsKwargs
from pyquibbler.utilities.general_utils import is_scalar_np, get_shared_shape, is_same_shapes
from pyquibbler.utilities.get_original_func import get_original_func

from .array_index_codes import IndexCode, is_focal_element, IndexCodeArray
from .exceptions import PyQuibblerRaggedArrayException
from .source_func_call import SourceFuncCall
from .types import Source


ALLOW_RAGGED_ARRAYS = True


def convert_an_arg_to_array_of_source_index_codes(arg: Any,
                                                  focal_source: Optional[Source] = None,
                                                  path_to_source: Optional[Path] = None,
                                                  path_in_source: Optional[Path] = None,
                                                  ) \
        -> Tuple[IndexCodeArray, Optional[Path], Optional[Path], Optional[Path]]:
    """
    Convert a given arg to an IndexCodeArray, which is an array of np.int64 with values wither matching
    the linear indexing of focal_source, or specifying other elements according to IndexCode.

    Parameters
    ----------
        `arg`: an object to convert to an index-code array, can be a scalar, an array,
        or array-like (nested list, tulple, arrays). This is typically the data argument of a numpy function.
        `arg` can be, or contain Sources.

        focal_source: the source whose indexes we want to encode.
            If `None`, the array will be encoded fully as IndexCode.OTHERS_ELEMENT.

        path_to_source: the path to the focal source. `None` for no focal source.

        path_in_source: a path in the focal source specifying chosen array elements, to be encoded as
            linear indices.  Source elements not in the path_in_source, are encoded as IndexCode.NON_CHOSEN_ELEMENT
            If `None`, all elements are encoded as indices.

        convert_to_bool_mask: a bool indicating whether to convert the array to boolean mask designating True for
            chosen source array elements, False otherwise.

    Returns
    -------
     1. arg_index_array:
            The index-code array representing `arg`

     2. remaining_path_to_source
        Remaining path to the source. If source is part of the array, the remaining path is []. If the source is
        a minor source, not part of the array but rather included within an element of the array, then the
        remaining_path_to_source is the path from the array element to the source.

     3 and 4. path_in_source_array, path_in_source_element
        The input parameter path_in_source, is broken into path_in_source_array, path_in_source_element,
        representing the part of the path that is within the source array, and the part, if any, that is
        within an element of the source array.
    """

    path_in_source_array: Optional[Path] = None
    path_in_source_element: Optional[Path] = None

    def _convert_obj_to_index_array(obj: Any, _remaining_path_to_source: Path = None) -> \
            Tuple[Union[IndexCode, IndexCodeArray], Optional[Path]]:
        """
        convert obj to index array. returns the index array and the remaining path to the source.
        """
        nonlocal path_in_source_array, path_in_source_element

        is_focal_source = obj is focal_source
        if isinstance(obj, Source):
            obj = obj.value

        if is_focal_source:
            if is_scalar_np(obj):
                path_in_source_array, path_in_source_element = [], path_in_source
                return IndexCode.FOCAL_SOURCE_SCALAR, _remaining_path_to_source

            full_index_array = np.arange(np.size(obj)).reshape(np.shape(obj))
            if path_in_source is None:
                return full_index_array, _remaining_path_to_source
            else:
                path_in_source_array, path_in_source_element, _ = split_path_at_end_of_object(full_index_array,
                                                                                              path_in_source)
                chosen_index_array = np.full(np.shape(obj), IndexCode.NON_CHOSEN_ELEMENT)
                deep_set(chosen_index_array, path_in_source_array, deep_get(full_index_array, path_in_source_array),
                         should_copy_objects_referenced=False)
                return chosen_index_array, _remaining_path_to_source

        if is_scalar_np(obj):
            if _remaining_path_to_source is None:
                return IndexCode.SCALAR_NOT_CONTAINING_FOCAL_SOURCE, _remaining_path_to_source
            path_in_source_array = []
            path_in_source_element = path_in_source
            return IndexCode.SCALAR_CONTAINING_FOCAL_SOURCE, _remaining_path_to_source

        if isinstance(obj, np.ndarray):
            return np.full(np.shape(obj), IndexCode.OTHERS_ELEMENT), _remaining_path_to_source

        if len(obj) == 0:
            return np.array(obj), _remaining_path_to_source

        source_index = None if _remaining_path_to_source is None else _remaining_path_to_source[0].component
        converted_sub_args = [None if source_index == sub_arg_index else
                              _convert_obj_to_index_array(sub_arg)[0] for sub_arg_index, sub_arg in enumerate(obj)]
        if _remaining_path_to_source is not None:
            converted_sub_args[source_index], _remaining_path_to_source = \
                _convert_obj_to_index_array(obj[source_index], _remaining_path_to_source[1:])

        if not is_same_shapes(converted_sub_args):
            # If the arrays are not same shape, their size will be squashed by numpy, yielding an object array
            # containing the squashed arrays.  We simulate that by an array with elements coded as
            # IndexCode.LIST_CONTAINING_CHOSEN_ELEMENTS, or IndexCode.LIST_NOT_CONTAINING_CHOSEN_ELEMENTS
            if not ALLOW_RAGGED_ARRAYS:
                raise PyQuibblerRaggedArrayException()

            shared_shape = get_shared_shape(converted_sub_args)

            for sub_arg_index, converted_sub_arg in enumerate(converted_sub_args):
                if converted_sub_arg.shape != shared_shape:
                    if np.any(is_focal_element(converted_sub_arg)):
                        collapsed_sub_arg = np.full(shared_shape, IndexCode.LIST_CONTAINING_CHOSEN_ELEMENTS)
                        if path_in_source is not None:
                            path_in_source_array, path_in_source_element, _ = \
                                split_path_at_end_of_object(collapsed_sub_arg, path_in_source)
                    else:
                        collapsed_sub_arg = np.full(shared_shape, IndexCode.LIST_NOT_CONTAINING_CHOSEN_ELEMENTS)
                    converted_sub_args[sub_arg_index] = collapsed_sub_arg

        return np.array(converted_sub_args), _remaining_path_to_source

    arg_index_array, remaining_path_to_source = _convert_obj_to_index_array(arg, path_to_source)

    return arg_index_array, remaining_path_to_source, path_in_source_array, path_in_source_element


def convert_args_before_run(func):

    @wraps(func)
    def wrapper(self, *arg, **kwargs):
        if self._func_args_kwargs is None:
            self.convert_data_arguments_to_source_index_codes()

        return func(self, *arg, **kwargs)

    return wrapper


@dataclasses.dataclass
class ArrayPathTranslator:
    """
    Convert the data arguments of a function call (func)call) to index code arrays (IndexCodeArray), representing
    the linear indexing of focal_source, or specifying other elements according to IndexCode.

    See more explanations in convert_an_arg_to_array_of_source_index_codes (above)
    """

    func_call: FuncCall
    focal_source: Source = None
    focal_source_location: SourceLocation = None
    path_in_source: Path = None
    convert_to_bool_mask: bool = False

    # Output:
    _remaining_path_to_source: Path = None
    _path_in_source_array: Path = None
    _path_in_source_element: Path = None
    _func_args_kwargs: FuncArgsKwargs = None

    def _convert_an_arg_to_array_of_source_index_codes(self, arg: Any, path_to_source: Optional[Path] = None,
                                                       ) -> IndexCodeArray:
        arg_index_array, remaining_path_to_source, path_in_source_array, path_in_source_element = \
            convert_an_arg_to_array_of_source_index_codes(arg, self.focal_source, path_to_source, self.path_in_source)
        if path_to_source is not None:
            self._path_in_source_array = path_in_source_array
            self._path_in_source_element = path_in_source_element
            self._remaining_path_to_source = remaining_path_to_source

        if self.convert_to_bool_mask:
            arg_index_array = is_focal_element(arg_index_array)
        return arg_index_array

    def is_func_of_multi_arg_data_argument(self):
        # TODO: this needs to be part of the function definition.
        return self.func_call.func is get_original_func(np.concatenate)

    def _convert_an_arg_or_multi_arg_to_array_of_source_index_codes(self, args: Union[Tuple[Any, ...], Any],
                                                                    path_to_source: Path = None) \
            -> Union[Tuple[IndexCodeArray, ...], IndexCodeArray]:
        """
        Convert given arg(s) to an array of int64 with values matching the linear indexing of focal_source,
        or specifying other elements according to IndexCode.
        `args` can be a single data argument, or a list/tuple containing data arguments (for example, for np.concatenate)
        """
        if self.is_func_of_multi_arg_data_argument():
            new_arg = []
            for index, arg in enumerate(args):
                if path_to_source[0].component == index:
                    converted_arg = self._convert_an_arg_to_array_of_source_index_codes(arg, path_to_source[1:])
                else:
                    converted_arg = self._convert_an_arg_to_array_of_source_index_codes(arg)
                new_arg.append(converted_arg)
            return tuple(new_arg)
        return self._convert_an_arg_to_array_of_source_index_codes(args, path_to_source)

    def convert_data_arguments_to_source_index_codes(self):
        """
        Convert data arguments in args/kwargs to arrays of index codes for the indicated focal source.
        """
        args = list(self.func_call.args)
        kwargs = copy.copy(self.func_call.kwargs)
        for data_argument in self.func_call.func_definition.get_data_source_arguments(self.func_call.func_args_kwargs):
            if isinstance(data_argument, KeywordArgument):
                args_or_kwargs = kwargs
                element_in_args_or_kwargs = data_argument.keyword
            else:
                args_or_kwargs = args
                element_in_args_or_kwargs = data_argument.index
            if self.focal_source_location.argument == data_argument:
                index_array = self._convert_an_arg_or_multi_arg_to_array_of_source_index_codes(
                        args_or_kwargs[element_in_args_or_kwargs],
                        path_to_source=self.focal_source_location.path)
            else:
                index_array = self._convert_an_arg_or_multi_arg_to_array_of_source_index_codes(
                        args_or_kwargs[element_in_args_or_kwargs])
    
            args_or_kwargs[element_in_args_or_kwargs] = index_array

        self._func_args_kwargs = FuncArgsKwargs(self.func_call.func, tuple(args), kwargs)

    @convert_args_before_run
    def get_func_args_kwargs(self):
        return self._func_args_kwargs

    @convert_args_before_run
    def get_path_from_array_element_to_source(self):
        return self._remaining_path_to_source

    @convert_args_before_run
    def get_path_in_source_array(self):
        return self._path_in_source_array

    @convert_args_before_run
    def get_path_in_source_element(self):
        return self._path_in_source_element

    @convert_args_before_run
    def get_source_path_split_at_end_of_array(self):
        return self._path_in_source_array, self._path_in_source_element

    @convert_args_before_run
    def get_masked_data_arguments(self):
        """
        a list of the data arguments as masked arrays
        """
        return [
            self._func_args_kwargs.get_arg_value_by_argument(argument) for
            argument in self.func_call.func_definition.get_data_source_arguments(self.func_call.func_args_kwargs)
        ]

    @convert_args_before_run
    def get_masked_data_argument_of_source(self):
        """
        the index-converted data argument of the focal source
        """
        return self._func_args_kwargs.get_arg_value_by_argument(self.focal_source_location.argument)


def run_func_call_with_new_args_kwargs(func_call: FuncCall, func_args_kwargs: FuncArgsKwargs) -> np.ndarray:
    """
    Runs the function with the given args, kwargs
    """
    return SourceFuncCall.from_(func_args_kwargs.func, func_args_kwargs.args, func_args_kwargs.kwargs,
                                func_definition=func_call.func_definition,
                                data_source_locations=[],
                                parameter_source_locations=func_call.parameter_source_locations).run()
