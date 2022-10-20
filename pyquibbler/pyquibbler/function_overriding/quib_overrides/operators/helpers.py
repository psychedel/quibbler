import math
import operator
from dataclasses import dataclass

from typing import List, Optional, Tuple

from pyquibbler.quib.quib import Quib

from pyquibbler.function_definitions.func_definition import ElementWiseFuncDefinition
from pyquibbler.function_overriding.function_override import FuncOverride
from pyquibbler.function_overriding.third_party_overriding.general_helpers import override_with_cls
from pyquibbler.utilities.operators_with_reverse import REVERSE_OPERATOR_NAMES_TO_FUNCS

# translators and inverters:
from pyquibbler.inversion.inverters.list_operators import ListOperatorInverter

from pyquibbler.path_translation.translators.elementwise import \
    BinaryElementwiseBackwardsPathTranslator, BinaryElementwiseForwardsPathTranslator, \
    UnaryElementwiseForwardsPathTranslator

from pyquibbler.path_translation.translators.list_operators import \
    ListOperatorBackwardsPathTranslator, ListOperatorForwardsPathTranslator

from pyquibbler.type_translation.translators import ElementwiseTypeTranslator

from pyquibbler.function_overriding.third_party_overriding.numpy.helpers import \
    BINARY_ELEMENTWISE_INVERTERS, UNARY_ELEMENTWISE_INVERTERS, UNARY_ELEMENTWISE_BACKWARDS_TRANSLATORS
from pyquibbler.function_overriding.third_party_overriding.numpy.inverse_functions import InverseFunc


@dataclass
class OperatorOverride(FuncOverride):
    SPECIAL_FUNCS = {
        '__round__': round,
        '__ceil__': math.ceil,
        '__trunc__': math.trunc,
        '__floor__': math.floor,
        '__getitem__': operator.getitem
    }

    def _get_func_from_module_or_cls(self):
        if self.func_name in self.SPECIAL_FUNCS:
            return self.SPECIAL_FUNCS[self.func_name]
        if self.func_name in REVERSE_OPERATOR_NAMES_TO_FUNCS:
            return REVERSE_OPERATOR_NAMES_TO_FUNCS[self.func_name]
        return getattr(operator, self.func_name)


def operator_override(func_name,
                      data_source_indexes: Optional[List] = None,
                      inverters: Optional[List] = None,
                      backwards_path_translators: Optional[List] = None,
                      forwards_path_translators: Optional[List] = None,
                      is_reverse: bool = False,
                      ):
    if is_reverse:
        func_name = '__r' + func_name[2:]

    return override_with_cls(OperatorOverride, Quib,
                             func_name, data_source_indexes,
                             inverters=inverters,
                             backwards_path_translators=backwards_path_translators,
                             forwards_path_translators=forwards_path_translators,
                             )


def binary_operator_override(func_name,
                             inverse_funcs: Tuple[Optional[InverseFunc]] = None,
                             is_reverse: bool = False,
                             ):
    backwards_path_translators = [BinaryElementwiseBackwardsPathTranslator]
    forwards_path_translators = [BinaryElementwiseForwardsPathTranslator]
    inverters = BINARY_ELEMENTWISE_INVERTERS

    # add special translators/invertors for list addition and multiplication:
    if func_name in ['__add__', '__mul__']:
        backwards_path_translators.insert(0, ListOperatorBackwardsPathTranslator)
        forwards_path_translators.insert(0, ListOperatorForwardsPathTranslator)
        inverters.insert(0, ListOperatorInverter)

    if is_reverse:
        func_name = '__r' + func_name[2:]
        inverse_funcs = inverse_funcs[-1::-1]

    return override_with_cls(OperatorOverride, Quib,
                             func_name,
                             data_source_arguments=[0, 1],
                             inverters=inverters,
                             backwards_path_translators=backwards_path_translators,
                             forwards_path_translators=forwards_path_translators,
                             result_type_or_type_translators=[ElementwiseTypeTranslator],
                             inverse_funcs=inverse_funcs,
                             func_definition_cls=ElementWiseFuncDefinition,
                             is_operator=True,
                             )


def unary_operator_override(func_name,
                            inverse_func: InverseFunc,
                            ):
    return override_with_cls(OperatorOverride, Quib,
                             func_name,
                             data_source_arguments=[0],
                             inverters=UNARY_ELEMENTWISE_INVERTERS,
                             backwards_path_translators=UNARY_ELEMENTWISE_BACKWARDS_TRANSLATORS,
                             forwards_path_translators=[UnaryElementwiseForwardsPathTranslator],
                             result_type_or_type_translators=[ElementwiseTypeTranslator],
                             inverse_funcs=(inverse_func, ),
                             func_definition_cls=ElementWiseFuncDefinition,
                             is_operator=True,
                             )
