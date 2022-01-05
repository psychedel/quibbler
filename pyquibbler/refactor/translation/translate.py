from typing import Callable, Type, Dict, Any, List

from pyquibbler.refactor.function_definitions.function_definition import FunctionDefinition
from pyquibbler.refactor.multiple_instance_runner import MultipleInstanceRunner
from pyquibbler.refactor.path.path_component import Path
from pyquibbler.refactor.function_definitions.func_call import FuncCall
from pyquibbler.refactor.translation.backwards_path_translator import BackwardsPathTranslator
from pyquibbler.refactor.translation.exceptions import FailedToTranslateException, NoTranslatorsFoundException
from pyquibbler.refactor.translation.forwards_path_translator import ForwardsPathTranslator
from pyquibbler.refactor.translation.types import Source


def backwards_translate(func_call: FuncCall,
                        path, shape=None, type_=None, **kwargs) -> Dict[Source, Path]:
    """
    Backwards translate a path given a func_call
    This gives a mapping of sources to paths that were referenced in given path in the result of the function
    """
    return MultipleBackwardsTranslatorRunner(func_call=func_call, path=path, shape=shape, type_=type_,
                                             extra_kwargs_for_translator=kwargs).run()


def forwards_translate(func_call: FuncCall,
                       sources_to_paths, shape=None, type_=None, **kwargs) -> Dict[Source, Path]:
    """
    Forwards translate a mapping of sources to paths through a function, giving for each source a list of paths that
    were affected by the given path for the source
    """
    return MultipleForwardsTranslatorRunner(func_call=func_call, sources_to_paths=sources_to_paths,
                                            shape=shape, type_=type_, extra_kwargs_for_translator=kwargs).run()


class MultipleBackwardsTranslatorRunner(MultipleInstanceRunner):
    expected_runner_exception = FailedToTranslateException
    exception_to_raise_on_none_found = NoTranslatorsFoundException

    def __init__(self, func_call: FuncCall, path: Path, shape, type_: Type, extra_kwargs_for_translator):
        super().__init__(func_call)
        self._path = path
        self._shape = shape
        self._type = type_
        self._extra_kwargs_for_translator = extra_kwargs_for_translator

    def _get_runners_from_definition(self, definition: FunctionDefinition) -> List:
        return definition.backwards_path_translators

    def _run_runner(self, runner: Type[BackwardsPathTranslator]):
        return runner(
            func_call=self._func_call,
            path=self._path,
            shape=self._shape,
            type_=self._type,
            **self._extra_kwargs_for_translator
        ).translate_in_order()


class MultipleForwardsTranslatorRunner(MultipleInstanceRunner):

    expected_runner_exception = FailedToTranslateException
    exception_to_raise_on_none_found = NoTranslatorsFoundException

    def __init__(self, func_call: FuncCall, sources_to_paths, shape=None, type_=None,
                 extra_kwargs_for_translator: Dict = None):
        super().__init__(func_call)
        self._sources_to_paths = sources_to_paths
        self._shape = shape
        self._type = type_
        self._extra_kwargs_for_translator = extra_kwargs_for_translator

    def _run_runner(self, runner: Type[ForwardsPathTranslator]):
        return runner(
            func_call=self._func_call,
            shape=self._shape,
            type_=self._type,
            sources_to_paths=self._sources_to_paths,
            **self._extra_kwargs_for_translator
        ).translate()

    def _get_runners_from_definition(self, definition: FunctionDefinition) -> List:
        return definition.forwards_path_translators
