from __future__ import annotations
import contextlib
import os
import pathlib
import pickle
import numpy as np
from functools import wraps
from functools import cached_property
from abc import ABC, abstractmethod
from dataclasses import dataclass
from operator import getitem
from typing import Set, Any, TYPE_CHECKING, Optional, Tuple, Type, List, Callable, Dict, Union, Iterable
from weakref import WeakSet
from contextlib import contextmanager

from .quib_guard import get_current_quib_guard, is_within_quib_guard
from .assignment.assignment_template import InvalidTypeException
from .assignment.utils import FailedToDeepAssignException
from .function_quibs.external_call_failed_exception_handling import raise_quib_call_exceptions_as_own, \
    add_quib_to_fail_trace_if_raises_quib_call_exception
from .override_choice import OverrideRemoval
from .quib_varname import get_var_name_being_set_outside_of_pyquibbler, get_file_name_and_line_number_of_quib
from .assignment import AssignmentTemplate, RangeAssignmentTemplate, BoundAssignmentTemplate, Overrider, Assignment, \
    AssignmentToQuib
from .function_quibs.cache import create_cache
from .function_quibs.cache.shallow.indexable_cache import transform_cache_to_nd_if_necessary_given_path
from .function_quibs.pretty_converters import MathExpression
from .utils import quib_method, Unpacker, recursively_run_func_on_object
from .assignment import PathComponent
from ..exceptions import PyQuibblerException
from ..env import LEN_RAISE_EXCEPTION, GET_VARIABLE_NAMES, SHOW_QUIB_EXCEPTIONS_AS_QUIB_TRACEBACKS
from ..input_validation_utils import validate_user_input, InvalidArgumentException
from ..logger import logger
from ..project import Project

if TYPE_CHECKING:
    from .graphics import GraphicsFunctionQuib
    from .override_choice import ChoiceContext, OverrideChoice


def get_user_friendly_name_for_requested_valid_path(valid_path: Optional[List[PathComponent]]):
    """
    Get a user-friendly name representing the call to get_value_valid_at_path
    """
    if valid_path is None:
        return 'get_blank_value()'
    elif len(valid_path) == 0:
        return 'get_value()'
    else:
        return f'get_value_valid_at_path({valid_path})'


@dataclass
class QuibIsNotNdArrayException(PyQuibblerException):
    quib: Quib
    value: Any

    def __str__(self):
        return f'The quib {self.quib} evaluates to {self.value}, which is not an ndarray, but a {type(self.value)}'


@dataclass
class OverridingNotAllowedException(PyQuibblerException):
    quib: Quib
    override: Assignment

    def __str__(self):
        return f'Cannot override {self.quib} with {self.override} as it does not allow overriding.'


@dataclass(frozen=True)
class FunctionCall:
    func: Callable
    args: Tuple[Any, ...]
    kwargs: Tuple[Tuple[str, Any], ...]

    @classmethod
    def create(cls, func: Callable, args: Tuple[Any, ...], kwargs: Dict[str, Any]):
        return cls(func, args, tuple(kwargs.items()))


def cache_method_until_full_invalidation(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(self: Quib, *args, **kwargs):
        call = FunctionCall.create(func, (self, *args), kwargs)
        if call in self.method_cache:
            return self.method_cache[call]
        result = func(self, *args, **kwargs)
        self.method_cache[call] = result
        return result

    return wrapper


class Quib(ABC):
    """
    An abstract class to describe the common methods and attributes of all quib types.
    """
    _DEFAULT_ALLOW_OVERRIDING = False
    _IS_WITHIN_GET_VALUE_CONTEXT = False

    def __init__(self, assignment_template: Optional[AssignmentTemplate] = None,
                 allow_overriding: Optional[bool] = None):
        self._assignment_template = assignment_template
        # Can't use WeakSet because it can change during iteration
        self._children = WeakSet()
        self._overrider = Overrider()
        if allow_overriding is None:
            allow_overriding = self._DEFAULT_ALLOW_OVERRIDING
        self._allow_overriding = allow_overriding
        self.method_cache = {}
        self._quibs_allowed_to_assign_to = None
        self._override_choice_cache = {}

        try:
            self._name = get_var_name_being_set_outside_of_pyquibbler() if GET_VARIABLE_NAMES else None
            self.file_name, self.line_no = get_file_name_and_line_number_of_quib() \
                if SHOW_QUIB_EXCEPTIONS_AS_QUIB_TRACEBACKS else None, None
        except Exception as e:
            logger.warning(f"Failed to get name, exception {e}")
            self._name = None
            self.file_name = None
            self.line_no = None

        self.project.register_quib(self)
        self._user_defined_save_directory = None
        self.created_in_get_value_context = self._IS_WITHIN_GET_VALUE_CONTEXT

    @property
    def project(self) -> Project:
        return Project.get_or_create()

    def setp(self, allow_overriding: bool = None, assignment_template=None,
             save_directory: Union[str, pathlib.Path] = None,
             **kwargs):
        """
        Configure a quib with certain attributes- because this function is expected to be used by users, we never
        setattr to anything before checking the types.
        """
        if allow_overriding is not None:
            self.set_allow_overriding(allow_overriding)
        if assignment_template is not None:
            self.set_assignment_template(assignment_template)
        if save_directory is not None:
            self.set_save_directory(save_directory)
        if 'name' in kwargs:
            self.set_name(kwargs.pop('name'))
        return self

    @validate_user_input(allow_overriding=bool)
    def set_allow_overriding(self, allow_overriding: bool):
        """
        Set whether the quib can be overridden- this defaults to True in iquibs and False in function quibs
        """
        self._allow_overriding = allow_overriding

    @property
    def children(self) -> Set[Quib]:
        """
        Return a copy of the current children weakset.
        """
        # We return a copy of the set because self._children can change size during iteration
        return set(self._children)

    def store_override_choice(self, context: ChoiceContext, choice: OverrideChoice) -> None:
        """
        Store a user override choice in the cache for future use.
        """
        self._override_choice_cache[context] = choice

    def try_load_override_choice(self, context: ChoiceContext) -> Optional[OverrideChoice]:
        """
        If a choice fitting the current options has been cached, return it. Otherwise return None.
        """
        return self._override_choice_cache.get(context)

    def _get_children_recursively(self) -> Set[Quib]:
        children = self.children
        for child in self.children:
            children |= child._get_children_recursively()
        return children

    def _get_graphics_function_quibs_recursively(self) -> Set[GraphicsFunctionQuib]:
        """
        Get all artists that directly or indirectly depend on this quib.
        """
        from pyquibbler.quib.graphics import GraphicsFunctionQuib
        return {child for child in self._get_children_recursively() if isinstance(child, GraphicsFunctionQuib)}

    def _redraw(self) -> None:
        """
        Redraw all artists that directly or indirectly depend on this quib.
        """
        from pyquibbler.quib.graphics.redraw import redraw_graphics_function_quibs_or_add_in_aggregate_mode
        quibs = self._get_graphics_function_quibs_recursively()
        redraw_graphics_function_quibs_or_add_in_aggregate_mode(quibs)

    def set_assigned_quibs(self, quibs: Optional[Iterable[Quib]]) -> None:
        """
        Set the quibs to which assignments to this quib could translate to overrides in.
        When None is given, a dialog will be used to choose between options.
        """
        self._quibs_allowed_to_assign_to = quibs if quibs is None else set(quibs)

    def allows_assignment_to(self, quib: Quib) -> bool:
        """
        Returns True if this quib allows assignments to it to be translated into assignments to the given quib,
        and False otherwise.
        """
        return True if self._quibs_allowed_to_assign_to is None else quib in self._quibs_allowed_to_assign_to

    def invalidate_and_redraw_at_path(self, path: Optional[List[PathComponent]] = None) -> None:
        """
        Perform all actions needed after the quib was mutated (whether by overriding or inverse assignment).
        If path is not given, the whole quib is invalidated.
        """
        from pyquibbler import timer
        if path is None:
            path = []

        with timer("quib_invalidation", lambda x: logger.info(f"invalidation {x}")):
            self._invalidate_children_at_path(path)
        self._redraw()

    def _invalidate_children_at_path(self, path: List[PathComponent]) -> None:
        """
        Change this quib's state according to a change in a dependency.
        """
        for child in self.children:
            child._invalidate_quib_with_children_at_path(self, path)

    def _get_paths_for_children_invalidation(self, invalidator_quib: Quib,
                                             path: List[PathComponent]) -> List[Optional[List[PathComponent]]]:
        """
        Get the new paths for invalidating children- a quib overrides this method if it has a specific way to translate
        paths to new invalidation paths.
        If not, invalidate all children all over; as you have no more specific way to invalidate them
        """
        return [[]]

    def _on_type_change(self):
        self.method_cache.clear()

    def _invalidate_self(self, path: List[PathComponent]):
        """
        This method is called whenever a quib itself is invalidated; subclasses will override this with their
        implementations for invalidations.
        For example, a simple implementation for a quib which is a function could be setting a boolean to true or
        false signifying validity
        """

    @staticmethod
    def _apply_assignment_to_cache(original_value, cache, assignment):
        """
        Apply an assignment to a cache, setting valid if it was an assignment and invalid if it was an assignmentremoval
        """
        cache = transform_cache_to_nd_if_necessary_given_path(cache, assignment.path)
        try:
            if isinstance(assignment, Assignment):
                # Our cache only accepts shallow paths, so any validation to a non-shallow path is not necessarily
                # overridden at the first component completely- so we ignore it
                if len(assignment.path) <= 1:
                    cache.set_valid_value_at_path(assignment.path, assignment.value)
            else:
                # Our cache only accepts shallow paths, so we need to consider any invalidation to a path deeper
                # than one component as an invalidation to the entire first component of that path
                if len(assignment.path) == 0:
                    cache = create_cache(original_value)
                else:
                    cache.set_invalid_at_path(assignment.path[:1])

        except (IndexError, TypeError):
            # it's very possible there's an old assignment that doesn't match our new "shape" (not specifically np)-
            # if so we don't care about it
            pass

        return cache

    def _is_completely_overridden_at_first_component(self, path) -> bool:
        """
        Get a list of all the non overridden paths (at the first component)
        """
        path = path[:1]
        assignments = list(self._overrider)
        if assignments:
            original_value = self._get_inner_value_valid_at_path(None)
            cache = create_cache(original_value)
            cache = transform_cache_to_nd_if_necessary_given_path(cache, path)
            for assignment in assignments:
                cache = self._apply_assignment_to_cache(original_value, cache, assignment)
            return len(cache.get_uncached_paths(path)) == 0
        return False

    def _invalidate_quib_with_children_at_path(self, invalidator_quib, path: List[PathComponent]):
        """
        Invalidate a quib and it's children at a given path.
        This method should be overriden if there is any 'special' implementation for either invalidating oneself
        or for translating a path for invalidation
        """
        new_paths = self._get_paths_for_children_invalidation(invalidator_quib, path)
        for new_path in new_paths:
            if new_path is not None:
                self._invalidate_self(new_path)
                if len(path) == 0 or not self._is_completely_overridden_at_first_component(new_path):
                    self._invalidate_children_at_path(new_path)

    def add_child(self, quib: Quib) -> None:
        """
        Add the given quib to the list of quibs that are dependent on this quib.
        """
        self._children.add(quib)

    def __len__(self):
        if LEN_RAISE_EXCEPTION:
            raise TypeError('len(Q), where Q is a quib, is not allowed. '
                            'To get a functional quib, use q(len,Q). '
                            'To get the len of the current value of Q, use len(Q.get_value()).')
        else:
            return len(self.get_value_valid_at_path(None))

    def __iter__(self):
        raise TypeError('Cannot iterate over quibs, as their size can vary. '
                        'Try Quib.iter_first() to iterate over the n-first items of the quib.')

    def override(self, assignment: Assignment, allow_overriding_from_now_on=True):
        """
        Overrides a part of the data the quib represents.
        """
        if allow_overriding_from_now_on:
            self._allow_overriding = True
        if not self._allow_overriding:
            raise OverridingNotAllowedException(self, assignment)
        self._overrider.add_assignment(assignment)
        if len(assignment.path) == 0:
            self._on_type_change()

        try:
            self.invalidate_and_redraw_at_path(assignment.path)
        except FailedToDeepAssignException as e:
            raise FailedToDeepAssignException(exception=e.exception, path=e.path) from None
        except InvalidTypeException as e:
            raise InvalidTypeException(e.type_) from None

        from pyquibbler.quib.graphics.widgets import is_within_drag
        if not is_within_drag():
            self.project.push_assignment_to_undo_stack(quib=self,
                                                       assignment=assignment,
                                                       index=len(list(self._overrider)) - 1,
                                                       overrider=self._overrider)

    def remove_override(self, path: List[PathComponent], invalidate_and_redraw: bool = True):
        """
        Remove overriding in a specific path in the quib.
        """
        assignment_removal = self._overrider.remove_assignment(path)
        if assignment_removal is not None:
            self.project.push_assignment_to_undo_stack(assignment=assignment_removal,
                                                       index=len(list(self._overrider)) - 1,
                                                       overrider=self._overrider,
                                                       quib=self)
        if len(path) == 0:
            self._on_type_change()
        if invalidate_and_redraw:
            self.invalidate_and_redraw_at_path(path=path)

    def assign(self, assignment: Assignment) -> None:
        """
        Create an assignment with an Assignment object, overriding the current values at the assignment's paths with the
        assignment's value
        """
        self.override(assignment, allow_overriding_from_now_on=False)

    @raise_quib_call_exceptions_as_own
    def assign_value(self, value: Any) -> None:
        """
        Helper method to assign a single value and override the whole value of the quib
        """
        self.assign(Assignment(value=value, path=[]))

    @raise_quib_call_exceptions_as_own
    def assign_value_to_key(self, key: Any, value: Any) -> None:
        """
        Helper method to assign a value at a specific key
        """
        from .assignment.assignment import PathComponent
        self.assign(Assignment(path=[PathComponent(component=key, indexed_cls=self.get_type())], value=value))

    def __getitem__(self, item):
        # We don't use the normal operator_overriding interface for two reasons:
        # 1. It can create issues with hinting in IDEs (for example, Pycharm will not recognize that Quibs have a
        # getitem and will issue a warning)
        # 2. We need the function to not be created dynamically as it needs to be in the inverser's supported functions
        # in order to be inversed correctly (and not simply override)
        from pyquibbler.quib.function_quibs.transpositional.getitem_function_quib import GetItemFunctionQuib
        return GetItemFunctionQuib.create(func=getitem, func_args=[self, item])

    def __setitem__(self, key, value):
        from .assignment.assignment import PathComponent
        if isinstance(key, Quib):
            key = key.get_value()
        self.assign(Assignment(value=value, path=[PathComponent(component=key, indexed_cls=self.get_type())]))

    @validate_user_input(name=(str, type(None)))
    def set_name(self, name: Optional[str]):
        """
        Set the quib's name- this will override any name automatically created if it exists.
        """
        if name is None or name.isidentifier():
            self._name = name
        else:
            raise ValueError('name must be None or a valid alphanumeic python identifier')

    @property
    def name(self) -> Optional[str]:
        """
        Get the name of the quib- this can either be an automatic name if created (the var name), a given name if given,
        and None if neither
        """
        return self._name

    @property
    def allow_overriding(self) -> bool:
        return self._allow_overriding

    @abstractmethod
    def _get_inner_functional_representation_expression(self) -> Union[MathExpression, str]:
        pass

    def get_functional_representation_expression(self) -> Union[MathExpression, str]:
        try:
            return self._get_inner_functional_representation_expression()
        except Exception as e:
            logger.warning(f"Failed to get repr {e}")
            return "[exception during repr]"

    @property
    def functional_representation(self) -> str:
        """
        Get a string representing a functional representation of the quib.
        For example, in
        ```
        a = iquib(4)
        ```
        "iquib(4)" would be the functional representation
        """
        return str(self.get_functional_representation_expression())

    def pretty_repr(self):
        """
        Returns a pretty representation of the quib. Might calculate values of parent quibs.
        """
        return f"{self.name} = {self.functional_representation}" \
            if self.name is not None else self.functional_representation

    def __str__(self):
        return self.pretty_repr()

    def get_assignment_template(self) -> AssignmentTemplate:
        return self._assignment_template

    def set_assignment_template(self, *args) -> None:
        """
        Sets an assignment template for the quib.
        Usage:

        - quib.set_assignment_template(assignment_template): set a specific AssignmentTemplate object.
        - quib.set_assignment_template(min, max): set the template to a bound template between min and max.
        - quib.set_assignment_template(start, stop, step): set the template to a bound template between min and max.
        """
        if len(args) == 1 and isinstance(args[0], tuple):
            args = args[0]

        if len(args) == 1:
            if not isinstance(args[0], AssignmentTemplate):
                raise InvalidArgumentException(expected_type=(AssignmentTemplate, tuple),
                                               var_name="assignment template")
            template, = args
        elif len(args) == 2:
            minimum, maximum = args
            template = BoundAssignmentTemplate(minimum, maximum)
        elif len(args) == 3:
            start, stop, step = args
            template = RangeAssignmentTemplate(start, stop, step)
        else:
            raise TypeError('Unsupported number of arguments, see docstring for usage')
        self._assignment_template = template

    @abstractmethod
    def _get_inner_value_valid_at_path(self, path: Optional[List[PathComponent]]) -> Any:
        """
        Get the data this quib represents valid at the pat given, before applying quib features like overrides.
        Perform calculations if needed.
        """

    @raise_quib_call_exceptions_as_own
    def get_value_valid_at_path(self, path: Optional[List[PathComponent]]) -> Any:
        """
        Get the actual data that this quib represents, valid at the path given in the argument.
        The value will necessarily return in the shape of the actual result, but only the values at the given path
        are guaranteed to be valid
        """
        if is_within_quib_guard():
            context = get_current_quib_guard().get_value_context_manager(self)
        else:
            context = contextlib.nullcontext()

        with context:
            name_for_call = get_user_friendly_name_for_requested_valid_path(path)
            with add_quib_to_fail_trace_if_raises_quib_call_exception(quib=self,
                                                                      call=name_for_call,
                                                                      replace_last=False):
                inner_value = self._get_inner_value_valid_at_path(path)

        return self._overrider.override(inner_value, self._assignment_template)

    @staticmethod
    @contextmanager
    def _get_value_context():
        """
        Change cls._IS_WITHIN_GET_VALUE_CONTEXT while in the process of running get_value.
        This has to be a static method as the _IS_WITHIN_GET_VALUE_CONTEXT is a global state for all quib types
        """
        if Quib._IS_WITHIN_GET_VALUE_CONTEXT:
            yield
        else:
            Quib._IS_WITHIN_GET_VALUE_CONTEXT = True
            try:
                yield
            finally:
                Quib._IS_WITHIN_GET_VALUE_CONTEXT = False

    @raise_quib_call_exceptions_as_own
    def get_value(self) -> Any:
        """
        Get the entire actual data that this quib represents, all valid.
        This function might perform several different computations - function quibs
        are lazy, so a function quib might need to calculate uncached values and might
        even have to calculate the values of its dependencies.
        """
        with self._get_value_context():
            return self.get_value_valid_at_path([])

    def get_override_list(self) -> Overrider:
        """
        Returns an Overrider object representing a list of overrides performed on the quib.
        """
        return self._overrider

    # We cache the type, so quibs without cache will still remember their types.
    @cache_method_until_full_invalidation
    def get_type(self) -> Type:
        """
        Get the type of wrapped value.
        """
        with add_quib_to_fail_trace_if_raises_quib_call_exception(quib=self, call='get_type()', replace_last=True):
            return type(self.get_value_valid_at_path(None))

    # We cache the shape, so quibs without cache will still remember their shape.
    @cache_method_until_full_invalidation
    def get_shape(self) -> Tuple[int, ...]:
        """
        Assuming this quib represents a numpy ndarray, returns a quib of its shape.
        """
        with add_quib_to_fail_trace_if_raises_quib_call_exception(quib=self, call='get_shape()', replace_last=True):
            res = self.get_value_valid_at_path(None)

        try:
            return np.shape(res)
        except ValueError:
            if hasattr(res, '__len__'):
                return len(res),
            raise

    @cache_method_until_full_invalidation
    def get_ndim(self) -> int:
        """
        Assuming this quib represents a numpy ndarray, returns a quib of its shape.
        """
        with add_quib_to_fail_trace_if_raises_quib_call_exception(quib=self, call='get_ndim()', replace_last=True):
            res = self.get_value_valid_at_path(None)

        try:
            return np.ndim(res)
        except ValueError:
            if hasattr(res, '__len__'):
                return 1
            raise

    @quib_method('elementwise')
    def get_override_mask(self):
        """
        Assuming this quib represents a numpy ndarray, return a quib representing its override mask.
        The override mask is a boolean array of the same shape, in which every value is
        set to True if the matching value in the array is overridden, and False otherwise.
        """
        if issubclass(self.get_type(), np.ndarray):
            mask = np.zeros(self.get_shape(), dtype=np.bool)
        else:
            mask = recursively_run_func_on_object(func=lambda x: False, obj=self.get_value())
        return self._overrider.fill_override_mask(mask)

    def iter_first(self, amount: Optional[int] = None):
        """
        Returns an iterator to the first `amount` elements of the quib.
        `a, b = quib.iter_first(2)` is the same as `a, b = quib[0], quib[1]`.
        When `amount` is not given, quibbler will try to detect the correct amount automatically, and
        might fail with a RuntimeError.
        For example, `a, b = iquib([1, 2]).iter_first()` is the same as `a, b = iquib([1, 2]).iter_first(2)`.
        But note that even if the quib is larger than the unpacked amount, the iterator will still yield only the first
        items - `a, b = iquib([1, 2, 3, 4]).iter_first()` is the same as `a, b = iquib([1, 2, 3, 4]).iter_first(2)`.
        """
        return Unpacker(self, amount)

    def remove_child(self, quib_to_remove: Quib):
        """
        Removes a child from the quib, no longer sending invalidations to it
        """
        self._children.remove(quib_to_remove)

    @property
    @abstractmethod
    def parents(self) -> Set[Quib]:
        """
        Returns a list of quibs that this quib depends on.
        """

    @cached_property
    def ancestors(self) -> Set[Quib]:
        """
        Return all ancestors of the quib, going recursively up the tree
        """
        ancestors = set()
        for parent in self.parents:
            ancestors.add(parent)
            ancestors |= parent.ancestors
        return ancestors

    def get_inversions_for_override_removal(self, override_removal: OverrideRemoval) -> List[OverrideRemoval]:
        """
        Get a list of overide removals to parent quibs which could be applied instead of the given override removal
        and produce the same change in the value of this quib.
        """
        return []

    def get_inversions_for_assignment(self, assignment: Assignment) -> List[AssignmentToQuib]:
        """
        Get a list of assignments to parent quibs which could be applied instead of the given assignment
        and produce the same change in the value of this quib.
        """
        return []

    @property
    @abstractmethod
    def _default_save_directory(self) -> Optional[pathlib.Path]:
        pass

    @property
    def _save_path(self) -> Optional[pathlib.Path]:
        save_name = self.name if self.name else hash(self.functional_representation)
        return self._save_directory / f"{save_name}.quib" if self._default_save_directory else None

    @property
    def _save_directory(self):
        return self._user_defined_save_directory \
            if self._user_defined_save_directory is not None else self._default_save_directory

    @validate_user_input(path=(str, pathlib.Path))
    def set_save_directory(self, path: Union[str, pathlib.Path]):
        """
        Set the save path of the quib (where it will be loaded/saved)
        """
        if isinstance(path, str):
            path = pathlib.Path(path)
        self._user_defined_save_directory = path.resolve()

    def save_if_relevant(self):
        """
        Save the quib if relevant- this will NOT save if the quib does not have overrides, as there is nothing to save
        """
        os.makedirs(self._save_path.parent, exist_ok=True)
        if len(list(self._overrider)) > 0:
            with open(self._save_path, 'wb') as f:
                pickle.dump(self._overrider, f)

    def load(self):
        if self._save_path and os.path.exists(self._save_path):
            with open(self._save_path, 'rb') as f:
                self._overrider = pickle.load(f)
                self.invalidate_and_redraw_at_path([])
