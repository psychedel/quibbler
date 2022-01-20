import functools
from typing import List, Union

from pyquibbler.function_definitions.func_definition import create_func_definition
from pyquibbler.function_overriding.function_override import FuncOverride

RawArgument = Union[str, int]


def override_with_cls(override_cls, module_or_cls,
                      func_name: str, data_source_arguments: List[RawArgument] = None,
                      forwards_path_translators: List = None, backwards_path_translators: List = None,
                      inverters: List = None,
                      quib_function_call_cls=None, is_file_loading_func=False,
                      replace_previous_quibs_on_artists: bool = False,
                      is_known_graphics_func: bool = False):
    return override_cls(
        func_name=func_name,
        module_or_cls=module_or_cls,
        function_definition=create_func_definition(
            data_source_arguments=data_source_arguments,
            forwards_path_translators=forwards_path_translators,
            backwards_path_translators=backwards_path_translators,
            inverters=inverters,
            is_file_loading_func=is_file_loading_func,
            quib_function_call_cls=quib_function_call_cls,
            replace_previous_quibs_on_artists=replace_previous_quibs_on_artists,
            is_known_graphics_func=is_known_graphics_func
        )
    )


override = functools.partial(override_with_cls, FuncOverride)
