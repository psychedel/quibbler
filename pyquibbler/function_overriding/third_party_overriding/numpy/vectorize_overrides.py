from typing import Union, Optional

import numpy as np

from pyquibbler.function_definitions import PositionalArgument, KeywordArgument
from pyquibbler.function_definitions.func_call import FuncArgsKwargs
from pyquibbler.function_definitions.func_definition import FuncDefinition
from pyquibbler.function_overriding.function_override import FuncOverride
from pyquibbler.quib.func_calling.func_calls.vectorize.vectorize_call \
    import VectorizeQuibFuncCall
from pyquibbler.quib.graphics import GraphicsUpdateType
from pyquibbler.env import PRETTY_REPR
from pyquibbler.quib.utils.miscellaneous import NoValue
from pyquibbler.translation.translators.vectorize_translator import VectorizeForwardsPathTranslator, \
    VectorizeBackwardsPathTranslator


class VectorizeOverride(FuncOverride):

    def _create_quib_supporting_func(self):
        QVectorize.__quibbler_wrapped__ = self.original_func
        return QVectorize


class VectorizeCallDefinition(FuncDefinition):

    def get_data_source_arguments_with_values(self, func_args_kwargs: FuncArgsKwargs):
        """
        Given a call to a vectorized function, return the arguments which act as data sources.
        We are using func_args_kwargs.args and func_args_kwargs.kwargs instead of the full args dict on purpose,
        to match vectorize function behavior.
        """
        from pyquibbler.quib.func_calling.func_calls.vectorize.utils import iter_arg_ids_and_values
        vectorize, *args = func_args_kwargs.args
        # We do + 1 to positional arguments because `vectorize` was zero and we removed it.
        return [(KeywordArgument(key) if isinstance(key, str) else PositionalArgument(key + 1), val)
                for key, val in iter_arg_ids_and_values(args, func_args_kwargs.kwargs) if key not in vectorize.excluded]


class VectorizeCallOverride(FuncOverride):

    def _get_creation_flags(self, args, kwargs):
        vectorize: QVectorize = args[0]
        return vectorize.func_defintion_flags


class QVectorize(np.vectorize):
    """
    A small wrapper to the np.vectorize class, adding options to __init__ and wrapping __call__
    with a quib function wrapper.
    """

    def __init__(self, *args,
                 is_random: bool = NoValue,
                 is_file_loading: bool = NoValue,
                 is_graphics: Optional[bool] = NoValue,
                 pass_quibs: bool = NoValue,
                 lazy: Optional[bool] = NoValue,
                 signature=None,
                 cache=False,  # We don't need the underlying vectorize object to cache, we are doing that ourselves.
                 **kwargs):
        super().__init__(*args, signature=signature, cache=False, **kwargs)

        self.func_defintion_flags = {name: value for name, value in (
            ('is_random', is_random),
            ('is_file_loading', is_file_loading),
            ('is_graphics', is_graphics),
            ('pass_quibs', pass_quibs),
            ('lazy', lazy),
        ) if value is not NoValue }

    def __repr__(self):
        if PRETTY_REPR:
            return f"np.vectorize({self.pyfunc.__name__}{'' if self.signature is None else ', ' + self.signature})"
        return f"<{self.__class__.__name__} {self.signature}>"


def create_vectorize_overrides():
    return [
        VectorizeOverride(func_name="vectorize", module_or_cls=np),
        VectorizeCallOverride(func_name="__call__", module_or_cls=QVectorize,
                              func_definition=VectorizeCallDefinition(
                                  quib_function_call_cls=VectorizeQuibFuncCall,
                                  is_graphics=None,
                                  forwards_path_translators=[VectorizeForwardsPathTranslator],
                                  backwards_path_translators=[VectorizeBackwardsPathTranslator]
                              )
                              )
    ]
