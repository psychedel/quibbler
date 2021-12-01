import pytest

from pyquibbler.third_party_overriding.definitions import OverrideDefinition


@pytest.fixture(autouse=True)
def override(mock_module, func_name_to_override, func_mock_on_module):
    def _override(**quib_creation_flags):
        definition = OverrideDefinition(func_name=func_name_to_override, module_or_cls=mock_module,
                                        quib_creation_flags=quib_creation_flags)
        definition.override()
        return definition
    return _override


def test_overriding_definition_does_not_call_func(overriden_func, func_mock_on_module, override):
    override()
    overriden_func()

    func_mock_on_module.assert_not_called()


def test_overriding_definition_does_call_func_when_set_to_evaluate_now(overriden_func, func_mock_on_module, override):
    override(evaluate_now=True)
    overriden_func()

    func_mock_on_module.assert_called_once()