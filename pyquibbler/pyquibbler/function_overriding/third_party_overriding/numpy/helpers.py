import functools
from typing import Callable, Tuple, Union, Optional, Dict

import numpy as np

from pyquibbler.env import ALLOW_ARRAY_WITH_DTYPE_OBJECT, INPUT_AWARE_INVERSION

from pyquibbler.function_overriding.function_override import FuncOverride
from pyquibbler.function_overriding.third_party_overriding.general_helpers import override, \
    file_loading_override, override_with_cls

from pyquibbler.path_translation.translators import \
    TranspositionalBackwardsPathTranslator, TranspositionalForwardsPathTranslator, \
    AxisAccumulationBackwardsPathTranslator, AxisAccumulationForwardsPathTranslator, \
    AxisReductionBackwardsPathTranslator, AxisReductionForwardsPathTranslator, \
    AxisAllToAllBackwardsPathTranslator, AxisAllToAllForwardsPathTranslator, \
    ShapeOnlyBackwardsPathTranslator, ShapeOnlyForwardsPathTranslator, \
    BinaryElementwiseBackwardsPathTranslator, BinaryElementwiseForwardsPathTranslator, \
    UnaryElementwiseBackwardsPathTranslator, UnaryElementwiseForwardsPathTranslator

from pyquibbler.inversion.inverters.transpositional import \
    TranspositionalOneToManyInverter, TranspositionalOneToOneInverter
from pyquibbler.inversion.inverters.elementwise import BinaryElementwiseInverter, UnaryElementwiseInverter
from pyquibbler.inversion.inverters.elementwise_single_arg_no_shape import UnaryElementwiseNoShapeInverter

from pyquibbler.function_definitions.func_definition import \
    UnaryElementWiseFuncDefinition, BinaryElementWiseFuncDefinition
from pyquibbler.path_translation.translators.elementwise import \
    UnaryElementwiseNoShapeBackwardsPathTranslator
from pyquibbler.type_translation.translators import ElementwiseTypeTranslator


class NumpyArrayOverride(FuncOverride):

    # We do not create quib for np.array([quib, ...], dtype=object).
    # This way, we can allow building object arrays containing quibs.

    @staticmethod
    def should_create_quib(func, args, kwargs):
        return ALLOW_ARRAY_WITH_DTYPE_OBJECT or kwargs.get('dtype', None) is not object


numpy_override = functools.partial(override, np)

numpy_override_random = functools.partial(override, np.random, is_random=True)

numpy_override_read_file = functools.partial(file_loading_override, np)

numpy_override_transpositional_one_to_many = \
    functools.partial(numpy_override, inverters=[TranspositionalOneToManyInverter],
                      backwards_path_translators=[TranspositionalBackwardsPathTranslator],
                      forwards_path_translators=[TranspositionalForwardsPathTranslator])

numpy_override_transpositional_one_to_one = \
    functools.partial(numpy_override, inverters=[TranspositionalOneToOneInverter],
                      backwards_path_translators=[TranspositionalBackwardsPathTranslator],
                      forwards_path_translators=[TranspositionalForwardsPathTranslator])

numpy_array_override = functools.partial(override_with_cls, NumpyArrayOverride, np,
                                         inverters=[TranspositionalOneToOneInverter],
                                         backwards_path_translators=[TranspositionalBackwardsPathTranslator],
                                         forwards_path_translators=[TranspositionalForwardsPathTranslator])

numpy_override_accumulation = functools.partial(numpy_override, data_source_arguments=[0],
                                                backwards_path_translators=[AxisAccumulationBackwardsPathTranslator],
                                                forwards_path_translators=[AxisAccumulationForwardsPathTranslator])

numpy_override_reduction = functools.partial(numpy_override, data_source_arguments=[0],
                                             backwards_path_translators=[AxisReductionBackwardsPathTranslator],
                                             forwards_path_translators=[AxisReductionForwardsPathTranslator])

numpy_override_axis_wise = functools.partial(numpy_override, data_source_arguments=[0],
                                             backwards_path_translators=[AxisAllToAllBackwardsPathTranslator],
                                             forwards_path_translators=[AxisAllToAllForwardsPathTranslator])

numpy_override_shape_only = functools.partial(numpy_override, data_source_arguments=[0],
                                              backwards_path_translators=[ShapeOnlyBackwardsPathTranslator],
                                              forwards_path_translators=[ShapeOnlyForwardsPathTranslator])

UNARY_ELEMENTWISE_FUNCS_TO_INVERSE_FUNCS = {}
BINARY_ELEMENTWISE_FUNCS_TO_INVERSE_FUNCS = {}

BINARY_ELEMENTWISE_INVERTERS = [BinaryElementwiseInverter]
UNARY_ELEMENTWISE_INVERTERS = [UnaryElementwiseNoShapeInverter, UnaryElementwiseInverter]

UNARY_ELEMENTWISE_BACKWARDS_TRANSLATORS = [UnaryElementwiseNoShapeBackwardsPathTranslator,
                                           UnaryElementwiseBackwardsPathTranslator]

def get_binary_inverse_funcs_for_func(func_name: str):
    return BINARY_ELEMENTWISE_FUNCS_TO_INVERSE_FUNCS[func_name]


def get_unary_inverse_funcs_for_func(func_name: str):
    return UNARY_ELEMENTWISE_FUNCS_TO_INVERSE_FUNCS[func_name]


def binary_elementwise(func_name: str,
                       inverse_funcs: Dict[int, Optional[Callable]]):

    is_inverse = inverse_funcs[0] or inverse_funcs[1]
    # if is_inverse:
    BINARY_ELEMENTWISE_FUNCS_TO_INVERSE_FUNCS[func_name] = inverse_funcs

    return numpy_override(
        func_name=func_name,
        data_source_arguments=[0, 1],
        backwards_path_translators=[BinaryElementwiseBackwardsPathTranslator],
        forwards_path_translators=[BinaryElementwiseForwardsPathTranslator],
        result_type_or_type_translators=[ElementwiseTypeTranslator],
        inverters=BINARY_ELEMENTWISE_INVERTERS if is_inverse else [],
        inverse_funcs=inverse_funcs,
        func_definition_cls=BinaryElementWiseFuncDefinition,
    )


def unary_elementwise(func_name: str,
                      inverse_func: Union[None, Callable, Tuple[Callable]]):

    inverse_func_requires_input = False
    if isinstance(inverse_func, tuple):
        if INPUT_AWARE_INVERSION:
            inverse_func = inverse_func[1]
            inverse_func_requires_input = True
        else:
            inverse_func = inverse_func[0]

    if inverse_func:
        UNARY_ELEMENTWISE_FUNCS_TO_INVERSE_FUNCS[func_name] = (inverse_func, inverse_func_requires_input)

    return numpy_override(
        func_name=func_name,
        data_source_arguments=[0],
        backwards_path_translators=UNARY_ELEMENTWISE_BACKWARDS_TRANSLATORS,
        forwards_path_translators=[UnaryElementwiseForwardsPathTranslator],
        result_type_or_type_translators=[ElementwiseTypeTranslator],
        inverters=UNARY_ELEMENTWISE_INVERTERS if inverse_func else [],
        inverse_func=inverse_func,
        inverse_func_requires_input=inverse_func_requires_input,
        func_definition_cls=UnaryElementWiseFuncDefinition,
    )
