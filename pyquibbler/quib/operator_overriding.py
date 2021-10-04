"""
Override Quib operators by replacing magic methods with Quibs that represent the getattr of these magic methods
from the original values.
This could also be done by replacing the magic methods with Quib function wrappers
(see commit 6d06b9fe76e3b7279c1dd737152d9c3cc586ebec).
The first method has the advantage of being simple and easy to implement, but the disadvantage of create two quibs per
magic method call, and not being able to handle cases where a magic method is not present on a built-in type but the
operator works anyway (e.g. float.__ceil__).
"""
import functools
from typing import Type, Callable

import magicmethods

from .function_quibs import DefaultFunctionQuib
from .quib import Quib

## Reasons for skipping some magic method groups:
# typeconv:              python checks that the return value is of the expected type
# lifecycle, reflection: don't want to mess with that
# iassign, pickling:     not supported at the moment
# attributes:            overriding manually
# contextmanagers:       doesn't make sense to override
# descriptors:           Quibs shouldn't be used as descriptors
# copying:               already defined on the Quib class
# unary:                 not all builtin types implement them, so getattr fails (e.g. float.__ceil__)
# comparison, callables, representation, containers: change python's behavior unexpectedly
OVERRIDES = magicmethods.arithmetic + magicmethods.rarithmetic


MAGIC_METHOD_IMPLEMENTATIONS = {}
MAGIC_METHOD_IMPLEMENTATIONS_PER_CLASS = {}


def magic_method_implementation(name: str):
    def _decorator(func):
        MAGIC_METHOD_IMPLEMENTATIONS[name] = func
        return func
    return _decorator


def get_magic_method_implementation_for_cls(cls: Type, func_name: str) -> Callable:
    """
    Gets the magic method implementation for a class and a function name.
    When a quib of the above type is called with this magic method, the DefaultFunctionQuib is guaranteed to be built
    with the returned function.
    """
    if func_name not in MAGIC_METHOD_IMPLEMENTATIONS:
        return getattr(cls, func_name)

    @functools.wraps(getattr(cls, func_name))
    def _wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    func = MAGIC_METHOD_IMPLEMENTATIONS[func_name]
    MAGIC_METHOD_IMPLEMENTATIONS_PER_CLASS.setdefault(cls, {}).setdefault(func_name, _wrapper)

    return MAGIC_METHOD_IMPLEMENTATIONS_PER_CLASS[cls][func_name]


@magic_method_implementation('__add__')
def add_wrapper(self, *args, **_):
    # In python, when using the plus sign, Python will first attempt to use .__add__ of the left side, and
    # then if NotImplemented is returned, will use .__radd__ of the right side.
    # Since we always return Quibs, we'll never return a NotImplemented for our __add__, even if potentially our
    # value would in fact return a NotImplemented.
    # If we simply run __add__ when we're finally meant to actually get the result, we're potentially just returning
    # NotImplemented. This is why we need to simulate a plus sign and not just call it.
    return self + args[0]


def get_magic_method_wrapper(name: str):
    def _wrapper(self, *args, **kwargs):
        return DefaultFunctionQuib.create(func=get_magic_method_implementation_for_cls(type(self.get_value()),
                                                                                       func_name=name),
                                          func_args=(self, *args),
                                          func_kwargs=kwargs)

    return _wrapper


def override_quib_operators():
    """
    Make operators (and other magic methods) on quibs return quibs.
    Overriding __getattr__ does not suffice because lookup of magic methods does not go
    through the standard getattr process.
    See more here: https://docs.python.org/3/reference/datamodel.html#special-method-lookup
    """
    # Override a bunch of magic methods to enable operators to work.
    for magic_method_name in OVERRIDES:
        assert magic_method_name not in vars(Quib), magic_method_name
        setattr(Quib, magic_method_name, get_magic_method_wrapper(magic_method_name))
