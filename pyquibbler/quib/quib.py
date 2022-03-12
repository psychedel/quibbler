from __future__ import annotations

import functools
import json
import os
import pathlib
import weakref
import warnings

from pyquibbler.utilities.file_path import PathWithHyperLink
from functools import cached_property
from typing import Set, Any, TYPE_CHECKING, Optional, Tuple, Type, List, Union, Iterable
from weakref import WeakSet

import numpy as np
from matplotlib.artist import Artist

from pyquibbler.env import LEN_RAISE_EXCEPTION, PRETTY_REPR, REPR_RETURNS_SHORT_NAME, REPR_WITH_OVERRIDES
from pyquibbler.graphics import is_within_drag
from pyquibbler.quib.quib_guard import guard_raise_if_not_allowed_access_to_quib, \
    CannotAccessQuibInScopeException
from pyquibbler.quib.pretty_converters import MathExpression, FailedMathExpression, \
    NameMathExpression, pretty_convert
from pyquibbler.quib.utils.translation_utils import get_func_call_for_translation_with_sources_metadata, \
    get_func_call_for_translation_without_sources_metadata
from pyquibbler.utilities.input_validation_utils import validate_user_input, InvalidArgumentValueException
from pyquibbler.logger import logger
from pyquibbler.project import Project
from pyquibbler.assignment import create_assignment_template
from pyquibbler.inversion.exceptions import NoInvertersFoundException
from pyquibbler.assignment import AssignmentTemplate, Overrider, Assignment, \
    AssignmentToQuib
from pyquibbler.path.data_accessing import FailedToDeepAssignException
from pyquibbler.path.path_component import PathComponent, Path, Paths
from pyquibbler.assignment import InvalidTypeException, OverrideRemoval, get_override_group_for_change
from pyquibbler.quib.func_calling.cache_behavior import CacheBehavior, UnknownCacheBehaviorException
from pyquibbler.quib.exceptions import OverridingNotAllowedException, UnknownUpdateTypeException, \
    InvalidCacheBehaviorForQuibException, CannotSaveAsTextException
from pyquibbler.quib.external_call_failed_exception_handling import raise_quib_call_exceptions_as_own
from pyquibbler.quib.graphics import UpdateType
from pyquibbler.utilities.iterators import recursively_run_func_on_object
from pyquibbler.translation.translate import forwards_translate, NoTranslatorsFoundException, \
    backwards_translate
from pyquibbler.utilities.unpacker import Unpacker
from pyquibbler.quib.utils.miscellaneous import copy_and_replace_quibs_with_vals
from pyquibbler.cache.cache import CacheStatus
from pyquibbler.cache import create_cache
from pyquibbler.file_syncing.types import SaveFormat, SAVEFORMAT_TO_FILE_EXT, \
    ResponseToFileNotDefined, FileNotDefinedException
from .get_value_context_manager import get_value_context, is_within_get_value_context
from .utils.miscellaneous import NoValue
from ..file_syncing.quib_file_syncer import QuibFileSyncer

if TYPE_CHECKING:
    from pyquibbler.function_definitions.func_definition import FuncDefinition
    from pyquibbler.assignment.override_choice import ChoiceContext
    from pyquibbler.assignment import OverrideChoice
    from pyquibbler.quib.func_calling import QuibFuncCall


class QuibHandler:
    """
    takes care of all the functionality of a quib.
    allows the Quib class to only have user functions
    All data is stored on the QuibHandler (the Quib itself is state-less)
    """

    def __init__(self, quib: Quib, quib_function_call: QuibFuncCall,
                 assignment_template: Optional[AssignmentTemplate],
                 allow_overriding: bool,
                 assigned_name: Optional[str],
                 file_name: Optional[str],
                 line_no: Optional[str],
                 graphics_update_type: Optional[UpdateType],
                 save_directory: pathlib.Path,
                 save_format: Optional[SaveFormat],
                 can_contain_graphics: bool,
                 ):

        quib_weakref = weakref.ref(quib)
        self._quib_weakref = quib_weakref
        self._override_choice_cache = {}
        self.quib_function_call = quib_function_call

        self.assignment_template = assignment_template
        self.assigned_name = assigned_name

        self.children = WeakSet()
        self._overrider: Optional[Overrider] = None
        self.file_syncer: QuibFileSyncer = QuibFileSyncer(quib_weakref)
        self.allow_overriding = allow_overriding
        self.assigned_quibs = None
        self.created_in_get_value_context = is_within_get_value_context()
        self.file_name = file_name
        self.line_no = line_no
        self.graphics_update_type = graphics_update_type

        self.save_directory = save_directory

        self.save_format = save_format
        self.can_contain_graphics = can_contain_graphics

        from pyquibbler.quib.graphics.persist import persist_artists_on_quib_weak_ref
        self.quib_function_call.artists_creation_callback = functools.partial(persist_artists_on_quib_weak_ref,
                                                                              weakref.ref(quib))

    """
    relationships
    """

    @property
    def quib(self):
        return self._quib_weakref()

    @property
    def project(self) -> Project:
        return Project.get_or_create()

    def add_child(self, quib: Quib) -> None:
        """
        Add the given quib to the list of quibs that are dependent on this quib.
        """
        self.children.add(quib)

    def remove_child(self, quib_to_remove: Quib):
        """
        Removes a child from the quib, no longer sending invalidations to it
        """
        self.children.remove(quib_to_remove)

    """
    graphics
    """

    def redraw_if_appropriate(self):
        """
        Redraws the quib if it's appropriate
        """
        if self.graphics_update_type in [UpdateType.NEVER, UpdateType.CENTRAL] \
                or (self.graphics_update_type == UpdateType.DROP and is_within_drag()):
            return

        return self.quib.get_value()

    def _iter_artist_lists(self) -> Iterable[List[Artist]]:
        return map(lambda g: g.artists, self.quib_function_call.flat_graphics_collections())

    def _iter_artists(self) -> Iterable[Artist]:
        return (artist for artists in self._iter_artist_lists() for artist in artists)

    def get_axeses(self):
        return {artist.axes for artist in self._iter_artists()}

    def _redraw(self) -> None:
        """
        Redraw all artists that directly or indirectly depend on this quib.
        """
        from pyquibbler.quib.graphics.redraw import redraw_quibs_with_graphics_or_add_in_aggregate_mode
        quibs = self._get_descendant_graphics_quibs_recursively()
        redraw_quibs_with_graphics_or_add_in_aggregate_mode(quibs)

    def _get_descendant_graphics_quibs_recursively(self) -> Set[Quib]:
        """
        Get all artists that directly or indirectly depend on this quib.
        """
        return {child for child in self.quib.get_descendants() if child.func_can_create_graphics}

    """
    Invalidation
    """

    def invalidate_self(self, path: Path):
        """
        This method is called whenever a quib itself is invalidated; subclasses will override this with their
        implementations for invalidations.
        For example, a simple implementation for a quib which is a function could be setting a boolean to true or
        false signifying validity
        """
        if len(path) == 0:
            self.quib_function_call.on_type_change()
            self.quib_function_call.reset_cache()

        self.quib_function_call.invalidate_cache_at_path(path)

    def invalidate_and_redraw_at_path(self, path: Optional[Path] = None) -> None:
        """
        Perform all actions needed after the quib was mutated (whether by function_definitions or inverse assignment).
        If path is not given, the whole quib is invalidated.
        """
        from pyquibbler import timer
        if path is None:
            path = []

        with timer("quib_invalidation", lambda x: logger.info(f"invalidate {x}")):
            self._invalidate_children_at_path(path)

        self._redraw()

    def _invalidate_children_at_path(self, path: Path) -> None:
        """
        Change this quib's state according to a change in a dependency.
        """
        for child in set(self.children):  # We copy of the set because children can change size during iteration

            child.handler._invalidate_quib_with_children_at_path(self.quib, path)

    def _invalidate_quib_with_children_at_path(self, invalidator_quib: Quib, path: Path):
        """
        Invalidate a quib and it's children at a given path.
        This method should be overriden if there is any 'special' implementation for either invalidating oneself
        or for translating a path for invalidation
        """
        new_paths = self._get_paths_for_children_invalidation(invalidator_quib, path)
        for new_path in new_paths:
            if new_path is not None:
                self.invalidate_self(new_path)
                if len(path) == 0 or not self._is_completely_overridden_at_first_component(new_path):
                    self._invalidate_children_at_path(new_path)

    def _forward_translate_without_retrieving_metadata(self, invalidator_quib: Quib, path: Path) -> Paths:
        func_call, sources_to_quibs = get_func_call_for_translation_without_sources_metadata(
            self.quib_function_call
        )
        quibs_to_sources = {quib: source for source, quib in sources_to_quibs.items()}
        sources_to_forwarded_paths = forwards_translate(
            func_call=func_call,
            sources_to_paths={
                quibs_to_sources[invalidator_quib]: path
            },
        )
        return sources_to_forwarded_paths.get(quibs_to_sources[invalidator_quib], [])

    def _forward_translate_with_retrieving_metadata(self, invalidator_quib: Quib, path: Path) -> Paths:
        func_call, sources_to_quibs = get_func_call_for_translation_with_sources_metadata(
            self.quib_function_call
        )
        quibs_to_sources = {quib: source for source, quib in sources_to_quibs.items()}
        sources_to_forwarded_paths = forwards_translate(
            func_call=func_call,
            sources_to_paths={
                quibs_to_sources[invalidator_quib]: path
            },
            shape=self.quib.get_shape(),
            type_=self.quib.get_type(),
            **self.quib_function_call.get_result_metadata()
        )
        return sources_to_forwarded_paths.get(quibs_to_sources[invalidator_quib], [])

    def _forward_translate_source_path(self, invalidator_quib: Quib, path: Path) -> Paths:
        """
        Forward translate a path, first attempting to do it WITHOUT using getting the shape and type, and if/when
        failure does grace us, we attempt again with shape and type
        """
        try:
            return self._forward_translate_without_retrieving_metadata(invalidator_quib, path)
        except NoTranslatorsFoundException:
            try:
                return self._forward_translate_with_retrieving_metadata(invalidator_quib, path)
            except NoTranslatorsFoundException:
                return [[]]

    def _get_paths_for_children_invalidation(self, invalidator_quib: Quib,
                                             path: Path) -> Paths:
        """
        Forward translate a path for invalidation, first attempting to do it WITHOUT using getting the shape and type,
        and if/when failure does grace us, we attempt again with shape and type.
        If we have no translators, we forward the path to invalidate all, as we have no more specific way to do it
        """
        # We always invalidate all if it's a parameter source quib
        if invalidator_quib not in self.quib_function_call.get_data_sources():
            return [[]]

        try:
            return self._forward_translate_without_retrieving_metadata(invalidator_quib, path)
        except NoTranslatorsFoundException:
            try:
                return self._forward_translate_with_retrieving_metadata(invalidator_quib, path)
            except NoTranslatorsFoundException:
                return [[]]

    """
    assignments
    """

    @property
    def overrider(self):
        if self._overrider is None:
            self._overrider = Overrider()
        return self._overrider

    @property
    def is_overridden(self):
        return self._overrider is not None and len(self._overrider)

    def override(self, assignment: Assignment, allow_overriding_from_now_on=True):
        """
        Overrides a part of the data the quib represents.
        """
        if allow_overriding_from_now_on:
            self.allow_overriding = True
        if not self.allow_overriding:
            raise OverridingNotAllowedException(self.quib, assignment)
        self.overrider.add_assignment(assignment)
        if len(assignment.path) == 0:
            self.quib_function_call.on_type_change()

        try:
            self.invalidate_and_redraw_at_path(assignment.path)
        except FailedToDeepAssignException as e:
            raise FailedToDeepAssignException(exception=e.exception, path=e.path) from None
        except InvalidTypeException as e:
            raise InvalidTypeException(e.type_) from None

        if not is_within_drag():
            self.project.push_assignment_to_undo_stack(quib=self.quib,
                                                       assignment=assignment,
                                                       index=len(self.overrider) - 1,
                                                       overrider=self.overrider)
            self.file_syncer.data_changed()

    def remove_override(self, path: Path):
        """
        Remove function_definitions in a specific path in the quib.
        """
        assignment_removal = self.overrider.remove_assignment(path)
        if assignment_removal is not None and not is_within_drag():
            self.project.push_assignment_to_undo_stack(assignment=assignment_removal,
                                                       index=len(self.overrider) - 1,
                                                       overrider=self.overrider,
                                                       quib=self.quib)
            self.file_syncer.data_changed()
        if len(path) == 0:
            self.quib_function_call.on_type_change()
        self.invalidate_and_redraw_at_path(path=path)

    def apply_assignment(self, assignment: Assignment) -> None:
        """
        Create an assignment with an Assignment object,
        function_definitions the current values at the assignment's paths with the assignment's value
        """
        get_override_group_for_change(AssignmentToQuib(self.quib, assignment)).apply()

    def get_inversions_for_override_removal(self, override_removal: OverrideRemoval) -> List[OverrideRemoval]:
        """
        Get a list of overide removals to parent quibs which could be applied instead of the given override removal
        and produce the same change in the value of this quib.
        """
        from pyquibbler.quib.utils.translation_utils import get_func_call_for_translation_with_sources_metadata
        func_call, sources_to_quibs = get_func_call_for_translation_with_sources_metadata(self.quib_function_call)
        try:
            sources_to_paths = backwards_translate(func_call=func_call, path=override_removal.path,
                                                   shape=self.quib.get_shape(), type_=self.quib.get_type())
        except NoTranslatorsFoundException:
            return []
        else:
            return [OverrideRemoval(sources_to_quibs[source], path) for source, path in sources_to_paths.items()]

    def get_inversions_for_assignment(self, assignment: Assignment) -> List[AssignmentToQuib]:
        """
        Get a list of assignments to parent quibs which could be applied instead of the given assignment
        and produce the same change in the value of this quib.
        """
        from pyquibbler.quib.utils.translation_utils import get_func_call_for_translation_with_sources_metadata
        func_call, data_sources_to_quibs = get_func_call_for_translation_with_sources_metadata(self.quib_function_call)

        try:
            value = self.quib.get_value()
            # TODO: need to take care of out-of-range assignments:
            # value = self.get_value_valid_at_path(assignment.path)

            from pyquibbler.inversion.invert import invert
            inversals = invert(func_call=func_call,
                               previous_result=value,
                               assignment=assignment)
        except NoInvertersFoundException:
            return []

        return [
            AssignmentToQuib(
                quib=data_sources_to_quibs[inversal.source],
                assignment=inversal.assignment
            )
            for inversal in inversals
        ]

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

    @staticmethod
    def _apply_assignment_to_cache(original_value, cache, assignment):
        """
        Apply an assignment to a cache, setting valid if it was an assignment and invalid if it was an assignmentremoval
        """
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
        if not self.is_overridden:
            return False

        assignments = list(self.overrider)
        path = path[:1]
        original_value = self.quib.get_value_valid_at_path(None)
        cache = create_cache(original_value)
        for assignment in assignments:
            cache = self._apply_assignment_to_cache(original_value, cache, assignment)
        return len(cache.get_uncached_paths(path)) == 0

    """
    get_value
    """

    def get_value_valid_at_path(self, path: Optional[Path]) -> Any:
        """
        Get the actual data that this quib represents, valid at the path given in the argument.
        The value will necessarily return in the shape of the actual result, but only the values at the given path
        are guaranteed to be valid
        """
        try:
            guard_raise_if_not_allowed_access_to_quib(self.quib)
        except CannotAccessQuibInScopeException:
            raise

        with get_value_context():
            result = self.quib_function_call.run(path)

        return self._overrider.override(result, self.assignment_template) if self.is_overridden \
            else result

    """
    file syncing
    """

    def save_assignments(self, file_path: pathlib.Path):
        save_format = self.quib.actual_save_format
        if save_format == SaveFormat.VALUE_TXT:
            return self._save_value_as_txt(file_path)
        elif save_format == SaveFormat.BIN:
            return self.overrider.save_to_binary(file_path)
        elif save_format == SaveFormat.TXT:
            return self.overrider.save_to_txt(file_path)

    def load_assignments(self, file_path: pathlib.Path):
        save_format = self.quib.actual_save_format
        if save_format == SaveFormat.VALUE_TXT:
            self._load_value_from_txt(file_path)
        else:
            if save_format == SaveFormat.BIN:
                changed_paths = self.overrider.load_from_binary(file_path)
            elif save_format == SaveFormat.TXT:
                changed_paths = self.overrider.load_from_txt(file_path)
            else:
                return
            self.project.clear_undo_and_redo_stacks()
            for path in changed_paths:
                self.invalidate_and_redraw_at_path(path)

    def _save_value_as_txt(self, file_path: pathlib.Path):
        """
        Save the quib's value as a text file.
        In contrast to the normal save, this will save the value of the quib regardless
        of whether the quib has overrides, as a txt file is used for the user to be able to see the quib and change it
        in a textual manner.
        Note that this WILL fail with CannotSaveAsTextException in situations where the iquib
        cannot be represented textually.
        """
        value = self.get_value_valid_at_path([])
        try:
            if isinstance(value, np.ndarray):
                np.savetxt(str(file_path), value)
            else:
                with open(file_path, 'w') as f:
                    json.dump(value, f)
        except TypeError:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise CannotSaveAsTextException()

    def _load_value_from_txt(self, file_path):
        """
        Load the quib from the corresponding text file is possible
        """

        # TODO: this method is more of a stud. needs attention
        if issubclass(self.get_type(), np.ndarray):
            self.quib.assign(np.array(np.loadtxt(str(file_path)), dtype=self.get_value().dtype))
        else:
            with open(file_path, 'r') as f:
                self.assign(json.load(f))


class Quib:
    """
    A Quib is a node representing a singular call of a function with it's arguments (it's parents in the graph)
    """

    def __init__(self, quib_function_call: QuibFuncCall,
                 assignment_template: Optional[AssignmentTemplate],
                 allow_overriding: bool,
                 assigned_name: Optional[str],
                 file_name: Optional[str],
                 line_no: Optional[str],
                 graphics_update_type: Optional[UpdateType],
                 save_directory: pathlib.Path,
                 save_format: Optional[SaveFormat],
                 can_contain_graphics: bool,
                 ):

        self.handler = QuibHandler(self, quib_function_call,
                                   assignment_template,
                                   allow_overriding,
                                   assigned_name,
                                   file_name,
                                   line_no,
                                   graphics_update_type,
                                   save_directory,
                                   save_format,
                                   can_contain_graphics,
                                   )

    """
    Func metadata funcs
    """

    @property
    def func(self):
        return self.handler.quib_function_call.func

    @property
    def args(self):
        return self.handler.quib_function_call.args

    @property
    def kwargs(self):
        return self.handler.quib_function_call.kwargs

    @property
    def func_definition(self) -> FuncDefinition:
        from pyquibbler.function_definitions import get_definition_for_function
        return get_definition_for_function(self.func)

    @property
    def is_impure_func(self):
        return self.is_random_func or self.is_file_loading_func

    @property
    def is_random_func(self):
        return self.func_definition.is_random_func

    @property
    def is_file_loading_func(self):
        return self.func_definition.is_file_loading_func

    """
    cache
    """

    @property
    def cache_status(self):
        """
        User interface to check cache validity.
        """
        return self.handler.quib_function_call.cache.get_cache_status() \
            if self.handler.quib_function_call.cache is not None else CacheStatus.ALL_INVALID

    @property
    def cache_behavior(self):
        """
        Set the value caching mode for the quib:
        'auto':     caching is decided automatically according to the ratio between evaluation time and
                    memory consumption.
        'off':      do not cache.
        'on':       always caching.

        Returns
        -------
        'auto', 'on', or 'off'

        See Also
        --------
        CacheBehavior
        """
        return self.handler.quib_function_call.get_cache_behavior().value

    @cache_behavior.setter
    @validate_user_input(cache_behavior=(str, CacheBehavior))
    def cache_behavior(self, cache_behavior: Union[str, CacheBehavior]):
        if isinstance(cache_behavior, str):
            try:
                cache_behavior = CacheBehavior[cache_behavior.upper()]
            except KeyError:
                raise UnknownCacheBehaviorException(cache_behavior) from None
        if self.is_random_func and cache_behavior != CacheBehavior.ON:
            raise InvalidCacheBehaviorForQuibException(self.handler.quib_function_call.default_cache_behavior)
        self.handler.quib_function_call.default_cache_behavior = cache_behavior

    """
    Graphics
    """

    @property
    def func_can_create_graphics(self):
        return self.handler.quib_function_call.func_can_create_graphics or self.handler.can_contain_graphics

    @property
    def graphics_update_type(self) -> Union[None, str]:
        """
        Return the graphics_update_type indicating whether the quib should refresh upon upstream assignments.
        Options are:
        "drag":     refresh immediately as upstream objects are dragged
        "drop":     refresh at end of dragging upon graphic object drop.
        "central":  do not automatically refresh. Refresh, centrally upon refresh_graphics().
        "never":    Never refresh.

        Returns
        -------
        "drag", "drop", "central", "never", or None

        See Also
        --------
        UpdateType, Project.refresh_graphics
        """
        return self.handler.graphics_update_type.value if self.handler.graphics_update_type else None

    @graphics_update_type.setter
    @validate_user_input(graphics_update_type=(type(None), str, UpdateType))
    def graphics_update_type(self, graphics_update_type: Union[None, str, UpdateType]):
        if isinstance(graphics_update_type, str):
            try:
                graphics_update_type = UpdateType[graphics_update_type.upper()]
            except KeyError:
                raise UnknownUpdateTypeException(graphics_update_type) from None
        self.handler.graphics_update_type = graphics_update_type

    """
    Assignment
    """

    @property
    def allow_overriding(self):
        """
        Indicates whether the quib can be overridden.
        The default for allow_overriding is True for iquibs and False in function quibs.

        Returns
        -------
        bool

        See Also
        --------
        assigned_quibs

        """
        return self.handler.allow_overriding

    @allow_overriding.setter
    @validate_user_input(allow_overriding=bool)
    def allow_overriding(self, allow_overriding: bool):
        self.handler.allow_overriding = allow_overriding

    @raise_quib_call_exceptions_as_own
    def assign(self, value: Any, key: Optional[Any] = NoValue) -> None:
        """
        Assign a specified value to the whole array, or to a specific key if specified
        """
        from pyquibbler import default

        key = copy_and_replace_quibs_with_vals(key)
        value = copy_and_replace_quibs_with_vals(value)
        path = [] if key is NoValue else [PathComponent(component=key, indexed_cls=self.get_type())]
        if value is default:
            self.handler.remove_override(path)
        else:
            self.handler.apply_assignment(Assignment(path=path, value=value))

    def __setitem__(self, key, value):
        from pyquibbler import default

        key = copy_and_replace_quibs_with_vals(key)
        value = copy_and_replace_quibs_with_vals(value)
        path = [PathComponent(component=key, indexed_cls=self.get_type())]
        if value is default:
            self.handler.remove_override(path)
        else:
            self.handler.apply_assignment(Assignment(value=value, path=path))

    @property
    def assigned_quibs(self) -> Union[None, Set[Quib, ...]]:
        """
        Set of quibs to which assignments to this quib could translate to and override.
        When assigned_quibs is None, a dialog will be used to choose between options.
        """
        return self.handler.assigned_quibs

    @assigned_quibs.setter
    def assigned_quibs(self, quibs: Optional[Iterable[Quib]]) -> None:
        if quibs is not None:
            try:
                quibs = set(quibs)
                if not all(map(lambda x: isinstance(x, Quib), quibs)):
                    raise Exception
            except Exception:
                raise InvalidArgumentValueException(
                    var_name='assigned_quibs',
                    message='a set of quibs.',
                ) from None

        self.handler.assigned_quibs = quibs

    @property
    def assignment_template(self) -> AssignmentTemplate:
        """
        Returns an AssignmentTemplate object indicating type and range restricting assignments to the quib.

        See also:
            assign
            AssignmentTemplate
        """
        return self.handler.assignment_template

    @assignment_template.setter
    @validate_user_input(template=AssignmentTemplate)
    def assignment_template(self, template):
        self.handler.assignment_template = template

    def set_assignment_template(self, *args) -> None:
        """
        Sets an assignment template for the quib.
        Usage:

        - quib.set_assignment_template(assignment_template): set a specific AssignmentTemplate object.
        - quib.set_assignment_template(min, max): set the template to a bound template between min and max.
        - quib.set_assignment_template(start, stop, step): set the template to a bound template between min and max.
        """
        self.handler.assignment_template = create_assignment_template(*args)

    """
    setp
    """

    def setp(self,
             allow_overriding: bool = NoValue,
             assignment_template: Union[tuple, AssignmentTemplate] = NoValue,
             save_directory: Union[str, pathlib.Path] = NoValue,
             save_format: Union[None, str, SaveFormat] = NoValue,
             cache_behavior: Union[str, CacheBehavior] = NoValue,
             assigned_name: Union[None, str] = NoValue,
             name: Union[None, str] = NoValue,
             graphics_update_type: Union[None, str] = NoValue,
             ):
        """
        Set one or more properties on a quib.

        Settable properties:
             allow_overriding: bool
             assignment_template: Union[tuple, AssignmentTemplate],
             save_directory: Union[str, pathlib.Path],
             save_format: Union[None, str, SaveFormat],
             cache_behavior: Union[str, CacheBehavior],
             assigned_name: Union[None, str],
             name: Union[None, str],
             graphics_update_type: Union[None, str]

        Examples:
            a = iquib(7).setp(assigned_name='my_number')
            b = (2 * a).setp(allow_overriding=True)
        """

        from pyquibbler.quib.factory import get_quib_name
        if allow_overriding is not NoValue:
            self.allow_overriding = allow_overriding
        if assignment_template is not NoValue:
            self.set_assignment_template(assignment_template)
        if save_directory is not NoValue:
            self.save_directory = save_directory
        if save_format is not NoValue:
            self.save_format = save_format
        if cache_behavior is not NoValue:
            self.cache_behavior = cache_behavior
        if assigned_name is not NoValue:
            self.assigned_name = assigned_name
        if name is not NoValue:
            self.assigned_name = name
        if graphics_update_type is not NoValue:
            self.graphics_update_type = graphics_update_type

        var_name = get_quib_name()
        if var_name:
            self.assigned_name = var_name

        return self

    """
    iterations
    """

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

    """
    get_value
    """

    @raise_quib_call_exceptions_as_own
    def get_value_valid_at_path(self, path: Optional[Path]) -> Any:
        """
        Get the actual data that this quib represents, valid at the path given in the argument.
        The value will necessarily return in the shape of the actual result, but only the values at the given path
        are guaranteed to be valid
        """
        return self.handler.get_value_valid_at_path(path)

    @raise_quib_call_exceptions_as_own
    def get_value(self) -> Any:
        """
        Get the entire actual data that this quib represents, all valid.
        This function might perform several different computations - function quibs
        are lazy, so a function quib might need to calculate uncached values and might
        even have to calculate the values of its dependencies.
        """
        return self.handler.get_value_valid_at_path([])

    @raise_quib_call_exceptions_as_own
    def get_type(self) -> Type:
        """
        Get the type of wrapped value.
        """
        return self.handler.quib_function_call.get_type()

    @raise_quib_call_exceptions_as_own
    def get_shape(self) -> Tuple[int, ...]:
        """
        Assuming this quib represents a numpy ndarray, returns a quib of its shape.
        """
        return self.handler.quib_function_call.get_shape()

    @raise_quib_call_exceptions_as_own
    def get_ndim(self) -> int:
        """
        Assuming this quib represents a numpy ndarray, returns a quib of its shape.
        """
        return self.handler.quib_function_call.get_ndim()

    """
    overrides
    """

    def get_override_list(self) -> Overrider:
        """
        Returns an Overrider object representing a list of overrides performed on the quib.
        """
        return self.handler.overrider

    def get_override_mask(self):
        """
        Assuming this quib represents a numpy ndarray, return a quib representing its override mask.
        The override mask is a boolean array of the same shape, in which every value is
        set to True if the matching value in the array is overridden, and False otherwise.
        """
        from pyquibbler.quib.specialized_functions import proxy
        quib = self.args[0] if self.func == proxy else self
        if issubclass(quib.get_type(), np.ndarray):
            mask = np.zeros(quib.get_shape(), dtype=np.bool)
        else:
            mask = recursively_run_func_on_object(func=lambda x: False, obj=quib.get_value())
        return quib.handler.overrider.fill_override_mask(mask)

    """
    relationships
    """

    def get_children(self) -> Set[Quib]:
        # we make a copy since children itself may change size during iteration
        return set(self.handler.children)

    def get_descendants(self) -> Set[Quib]:
        children = self.get_children()
        for child in self.get_children():
            children |= child.get_descendants()
        return children

    @property
    def parents(self) -> Set[Quib]:
        """
        Returns a list of quibs that this quib depends on.
        """
        return set(self.handler.quib_function_call.get_objects_of_type_in_args_kwargs(Quib))

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

    """
    File saving
    """

    def _upon_file_name_change(self):
        # TODO: announce name change due to project directory change
        self.handler.file_syncer.file_name_changed()

    @property
    def project(self) -> Project:
        return self.handler.project

    @property
    def save_format(self):
        """
        Indicates the file format in which quib assignments are saved.

        Options:
            'txt' - save assignments as text file.
            'binary' - save assignments as a binary file.
            'value_txt' - save the quib value as a text file.
            None - yield to the Project default save_format

        See also:
             SaveFormat
        """
        return self.handler.save_format

    @save_format.setter
    @validate_user_input(save_format=(str, SaveFormat))
    def save_format(self, save_format):
        if isinstance(save_format, str):
            save_format = SaveFormat(save_format)
        self.handler.save_format = save_format
        self._upon_file_name_change()

    @property
    def actual_save_format(self) -> SaveFormat:
        """
        The actual save_format used by the quib.

        The quib's actual_save_format is its save_format if defined.
        Otherwise it defaults to the project's save_format.

        Returns:
            SaveFormat

        See also:
            save_format
            SaveFormat
        """
        return self.save_format if self.save_format else self.project.save_format

    @property
    def file_path(self) -> Optional[PathWithHyperLink]:
        """
        The full path for the file where quib assignments are saved.
        The path is defined as the [actual_save_directory]/[assigned_name].ext
        ext is determined by the actual_save_format

        Returns:
            Path or None

        See also:
            save_directory
            actual_save_directory
            save_format
            actual_save_format
            assigned_name
            Project.directory
        """
        return self._get_file_path()

    def _get_file_path(self, response_to_file_not_defined: ResponseToFileNotDefined = ResponseToFileNotDefined.IGNORE) \
            -> Optional[PathWithHyperLink]:

        if self.assigned_name is None or self.actual_save_directory is None or self.actual_save_format is None:
            path = None
            exception = FileNotDefinedException(
                self.assigned_name, self.actual_save_directory, self.actual_save_format)
            if response_to_file_not_defined == ResponseToFileNotDefined.RAISE:
                raise exception
            elif response_to_file_not_defined == ResponseToFileNotDefined.WARN \
                    or response_to_file_not_defined == ResponseToFileNotDefined.WARN_IF_DATA \
                    and self.handler.is_overridden():
                warnings.warn(str(exception))
        else:
            path = PathWithHyperLink(self.actual_save_directory /
                                     (self.assigned_name + SAVEFORMAT_TO_FILE_EXT[self.actual_save_format]))

        return path

    @property
    def save_directory(self) -> PathWithHyperLink:
        """
        The directory where quib assignments are saved.

        Can be set to a str or Path object.

        If the directory is absolute, it is used as is.
        If directory is relative, it is used relative to the project directory.
        If directory is None, the project directory is used.

        Returns:
            Path

        See also:
            file_path
        """
        return PathWithHyperLink(self.handler.save_directory)

    @save_directory.setter
    @validate_user_input(directory=(str, pathlib.Path))
    def save_directory(self, directory: Union[str, pathlib.Path]):
        if isinstance(directory, str):
            directory = pathlib.Path(directory)
        self.handler.save_directory = directory
        self._upon_file_name_change()

    @property
    def actual_save_directory(self) -> Optional[pathlib.Path]:
        """
        The actual directory where quib file is saved.

        By default, the quib's save_directory is None and the actual_save_directory defaults to the
        project's save_directory.
        Otherwise, if the quib's save_directory is defined as an absolute directory then it is used as is,
        and if it is defined as a relative path it is used relative to the project's directory.

        Returns:
            Path

        See also:
            save_directory
            Project.directory
            SaveFormat
        """
        save_directory = self.handler.save_directory
        if save_directory is not None and save_directory.is_absolute():
            return save_directory  # absolute directory
        elif self.project.directory is None:
            return None
        else:
            return self.project.directory if save_directory is None \
                else self.project.directory / save_directory

    def save(self, response_to_file_not_defined: ResponseToFileNotDefined = ResponseToFileNotDefined.RAISE):
        """
        Save the quib assignments to file.

        See also:
            load
            sync
            save_directory
            actual_save_directory
            save_format
            actual_save_format
            assigned_name
            Project.directory
        """
        self._get_file_path(response_to_file_not_defined)
        self.handler.file_syncer.save()

    def load(self, response_to_file_not_defined: ResponseToFileNotDefined = ResponseToFileNotDefined.RAISE):
        """
        Load quib assignments from the quib's file.

        See also:
            save
            sync
            save_directory
            actual_save_directory
            save_format
            actual_save_format
            assigned_name
            Project.directory
        """
        self._get_file_path(response_to_file_not_defined)
        self.handler.file_syncer.load()

    def sync(self, response_to_file_not_defined: ResponseToFileNotDefined = ResponseToFileNotDefined.RAISE):
        """
        Sync quib assignments with the quib's file.

        If the file was changed it will be read to the quib.
        If the quib assignments were changed, the file will be updated.
        If both changed, a dialog is presented to resolve conflict.

        See also:
            save
            load
            save_directory
            actual_save_directory
            save_format
            actual_save_format
            assigned_name
            Project.directory
        """
        self._get_file_path(response_to_file_not_defined)
        self.handler.file_syncer.sync()

    """
    Repr
    """

    @property
    def assigned_name(self) -> Optional[str]:
        """
        Returns the assigned_name of the quib
        The assigned_name can either be a name automatically created based on the variable name to which the quib
        was first assigned, or a manually assigned name set by setp or by assigning to assigned_name,
        or None indicating unnamed quib.

        The name must be a string starting with a letter and continuing with alpha-numeric charaters. Spaces
        are also allowed.

        The assigned_name is also used for setting the file name for saving overrides.

        Returns
        -------
        str, None

        See Also
        --------
        name, setp, Project.save_quibs, Project.load_quibs
        """
        return self.handler.assigned_name

    @assigned_name.setter
    @validate_user_input(assigned_name=(str, type(None)))
    def assigned_name(self, assigned_name: Optional[str]):
        if assigned_name is None \
                or len(assigned_name) \
                and assigned_name[0].isalpha() and all([c.isalnum() or c in ' _' for c in assigned_name]):
            self.handler.assigned_name = assigned_name
            self._upon_file_name_change()
        else:
            raise ValueError('name must be None or a string starting with a letter '
                             'and continuing alpha-numeric characters or spaces')

    @property
    def name(self) -> Optional[str]:
        """
        Returns the name of the quib

        The name of the quib can either be the given assigned_name if not None,
        or an automated name representing the function of the quib (the functional_representation attribute).

        Assigning into name is equivalent to assigning into assigned_name

        Returns
        -------
        str

        See Also
        --------
        assigned_name, setp, functional_representation
        """
        return self.assigned_name or self.functional_representation

    @name.setter
    def name(self, name: str):
        self.assigned_name = name

    def _get_functional_representation_expression(self) -> MathExpression:
        try:
            return pretty_convert.get_pretty_value_of_func_with_args_and_kwargs(self.func, self.args, self.kwargs)
        except Exception as e:
            logger.warning(f"Failed to get repr {e}")
            return FailedMathExpression()

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
        return str(self._get_functional_representation_expression())

    def get_math_expression(self) -> MathExpression:
        return NameMathExpression(self.assigned_name) if self.assigned_name is not None \
            else self._get_functional_representation_expression()

    def ugly_repr(self):
        return f"<{self.__class__.__name__} - {self.func}"

    def pretty_repr(self):
        """
        Returns a pretty representation of the quib.
        """
        return f"{self.assigned_name} = {self.functional_representation}" \
            if self.assigned_name is not None else self.functional_representation

    def __repr__(self):
        return str(self)

    def __str__(self):
        if PRETTY_REPR:
            if REPR_RETURNS_SHORT_NAME:
                return str(self.get_math_expression())
            elif REPR_WITH_OVERRIDES and self.handler.is_overridden:
                return self.pretty_repr() + '\n' + self.handler.overrider.pretty_repr(self.assigned_name)
            return self.pretty_repr()
        return self.ugly_repr()

    @property
    def line_no(self):
        return self.handler.line_no

    @property
    def file_name(self):
        return self.handler.file_name
