from typing import Type, Any

from pyquibbler.path import Path
from pyquibbler.function_definitions import SourceLocation
from pyquibbler.translation import BackwardsPathTranslator, ForwardsPathTranslator, Source, Inversal
from pyquibbler.translation.translators import BackwardsTranspositionalTranslator, ForwardsTranspositionalTranslator

from .numpy_inverter import NumpyInverter


class TranspositionalInverter(NumpyInverter):

    BACKWARDS_TRANSLATOR_TYPE: Type[BackwardsPathTranslator] = BackwardsTranspositionalTranslator
    FORWARDS_TRANSLATOR_TYPE: Type[ForwardsPathTranslator] = ForwardsTranspositionalTranslator

    def _invert_value(self, source: Source, source_location: SourceLocation, path_in_source: Path, value: Any)\
            -> Any:
        return value
