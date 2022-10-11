from typing import Type, Any

from pyquibbler.path import Path
from pyquibbler.function_definitions import SourceLocation
from pyquibbler.translation import BackwardsPathTranslator, ForwardsPathTranslator, Source
from pyquibbler.translation.translators import BackwardsTranspositionalTranslator, ForwardsTranspositionalTranslator

from .numpy_inverter import NumpyInverter


class TranspositionalOneToOneInverter(NumpyInverter):

    BACKWARDS_TRANSLATOR_TYPE: Type[BackwardsPathTranslator] = BackwardsTranspositionalTranslator
    FORWARDS_TRANSLATOR_TYPE: Type[ForwardsPathTranslator] = ForwardsTranspositionalTranslator
    IS_ONE_TO_MANY_FUNC: bool = False

    def _invert_value(self, source: Source, source_location: SourceLocation, path_in_source: Path,
                      result_value: Any, path_in_result: Path) -> Any:
        return result_value


class TranspositionalOneToManyInverter(TranspositionalOneToOneInverter):
    IS_ONE_TO_MANY_FUNC: bool = True
