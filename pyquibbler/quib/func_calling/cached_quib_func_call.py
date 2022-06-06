from __future__ import annotations

from contextlib import ExitStack
from sys import getsizeof
from time import perf_counter
from typing import Optional, Tuple, Dict, Any, Set, Mapping, Callable, List, Union

from pyquibbler.cache.cache_utils import _truncate_path_to_match_shallow_caches, _ensure_cache_matches_result, \
    get_cached_data_at_truncated_path_given_result_at_uncached_path
from pyquibbler.cache import PathCannotHaveComponentsException, get_uncached_paths_matching_path

from pyquibbler.function_definitions import load_source_locations_before_running

from pyquibbler.graphics.graphics_collection import GraphicsCollection
from pyquibbler.path import Path
from pyquibbler.quib import consts
from pyquibbler.quib.external_call_failed_exception_handling import external_call_failed_exception_handling
from pyquibbler.quib.func_calling import QuibFuncCall
from pyquibbler.quib.func_calling.cache_mode import CacheMode
from pyquibbler.quib.quib import Quib
from pyquibbler.quib.quib_guard import QuibGuard
from pyquibbler.quib.utils.translation_utils import get_func_call_for_translation_with_sources_metadata, \
    get_func_call_for_translation_without_sources_metadata
from pyquibbler.translation import NoTranslatorsFoundException
from pyquibbler.translation.translate import backwards_translate


class CachedQuibFuncCall(QuibFuncCall):
    """
    Represents a FuncCall with Quibs as argument sources- this will handle running a function with quibs as arguments,
    by caching results and only asking for necessary values from argument quibs
    """

    DEFAULT_CACHE_MODE = CacheMode.AUTO

    def _get_cache_behavior(self):
        if self.func_definition.is_random or self.func_can_create_graphics:
            return CacheMode.ON
        return self.cache_mode

    def _should_cache(self, result: Any, elapsed_seconds: float):
        """
        Decide if the result of the calculation is worth caching according to its size and the calculation time.
        Note that there is no accurate way (and no efficient way to even approximate) the complete size of composite
        types in python, so we only measure the outer size of the object.
        """
        cache_mode = self._get_cache_behavior()
        if cache_mode is CacheMode.ON:
            return True
        if cache_mode is CacheMode.OFF:
            return False
        assert cache_mode is CacheMode.AUTO, \
            f'self.cache_mode has unexpected value: "{cache_mode}"'
        return elapsed_seconds > consts.MIN_SECONDS_FOR_CACHE \
            and getsizeof(result) / elapsed_seconds < consts.MAX_BYTES_PER_SECOND

    def _reset_cache(self):
        self.cache = None
        self._caching = True if self._get_cache_behavior() == CacheMode.ON else False
        self._result_metadata = None

    def on_type_change(self):
        self._reset_cache()
        super(CachedQuibFuncCall, self).on_type_change()

    def _run_single_call(self, func: Callable, graphics_collection: GraphicsCollection,
                         args: Tuple[Any, ...], kwargs: Mapping[str, Any], quibs_allowed_to_access: Set[Quib]):

        with ExitStack() as stack:
            if self.func_definition.is_graphics is not False:
                stack.enter_context(graphics_collection.track_and_handle_new_graphics(
                    kwargs_specified_in_artists_creation=set(
                        key for key, value in self.kwargs.items() if value is not None)))
            stack.enter_context(QuibGuard(quibs_allowed_to_access))
            stack.enter_context(external_call_failed_exception_handling())

            res = func(*args, **kwargs)

        # We don't allow returning quibs as results from functions
        from pyquibbler.quib.quib import Quib
        if isinstance(res, Quib):
            res = res.get_value()

        if self.artists_creation_callback:
            self.artists_creation_callback(graphics_collection.artists, self.func_args_kwargs)

        return res

    def _backwards_translate_path(self, valid_path: Path) -> Dict[Quib, Path]:
        """
        Backwards translate a path- first attempt without shape + type, and then if G-d's good graces fail us and we
        find we are without the ability to do this, try with shape + type
        """
        if not self.get_data_sources():
            return {}

        try_with_shape = False
        try:
            func_call, sources_to_quibs = get_func_call_for_translation_without_sources_metadata(func_call=self)
            sources_to_paths = backwards_translate(
                func_call=func_call,
                path=valid_path,
            )
        except NoTranslatorsFoundException:
            try_with_shape = True

        if try_with_shape:
            func_call, sources_to_quibs = get_func_call_for_translation_with_sources_metadata(func_call=self)
            try:
                sources_to_paths = backwards_translate(
                    func_call=func_call,
                    path=valid_path,
                    shape=self.get_shape(),
                    type_=self.get_type(),
                    **self.get_result_metadata()
                )
            except NoTranslatorsFoundException:
                return {}

        return {
            quib: sources_to_paths.get(source, None)
            for source, quib in sources_to_quibs.items()
        }

    def _proxify_args(self):
        from pyquibbler.quib.specialized_functions.proxy import create_proxy
        quibs_allowed_to_access = set()

        def _proxify(arg):
            proxy = create_proxy(arg)
            quibs_allowed_to_access.add(proxy)
            return proxy

        args, kwargs = self.transform_sources_in_args_kwargs(transform_parameter_func=_proxify,
                                                             transform_data_source_func=_proxify)
        return args, kwargs, quibs_allowed_to_access

    def _run_on_path(self, valid_path: Path):
        graphics_collection: GraphicsCollection = self.graphics_collections[()]

        if self._pass_quibs:
            args, kwargs, quibs_allowed_to_access = self._proxify_args()
        else:
            quibs_to_paths = {} if valid_path is None else self._backwards_translate_path(valid_path)
            args, kwargs = self._get_args_and_kwargs_valid_at_quibs_to_paths(quibs_to_paths)
            quibs_allowed_to_access = set()

        return self._run_single_call(
            func=self.func,
            args=args,
            kwargs=kwargs,
            graphics_collection=graphics_collection,
            quibs_allowed_to_access=quibs_allowed_to_access
        )

    def _run_on_uncached_paths_within_path(self, valid_paths: List[Union[None, Path]]):
        uncached_paths = []
        for valid_path in valid_paths:
            uncached_paths.extend(get_uncached_paths_matching_path(cache=self.cache, path=valid_path))

        if len(uncached_paths) == 0:
            if self.cache is None:
                result = self._run_on_path(None)
                self.cache = _ensure_cache_matches_result(self.cache, result)
            return self.cache.get_value()

        result = None

        for uncached_path in uncached_paths:
            result = self._run_on_path(uncached_path)

            truncated_path = _truncate_path_to_match_shallow_caches(uncached_path)
            self.cache = _ensure_cache_matches_result(self.cache, result)

            if truncated_path is not None:
                value = get_cached_data_at_truncated_path_given_result_at_uncached_path(self.cache,
                                                                                        result,
                                                                                        truncated_path,
                                                                                        uncached_path)

                try:
                    self.cache.set_valid_value_at_path(truncated_path, value)
                except PathCannotHaveComponentsException:
                    # We do not have a diverged cache for this type, we can't store the value; this is not a problem as
                    # everything will work as expected, but we will simply not cache
                    assert len(uncached_paths) == 1, "There should never be a situation in which we have multiple " \
                                                     "uncached paths but our cache can't handle setting a value at a " \
                                                     "specific component"
                else:
                    # We need to get the result from the cache (as opposed to simply using the last run), since we
                    # don't want to only take the last run
                    result = self.cache.get_value()

                    # assert is commented as this is not the case for a list cache
                    # accessed with array indexing.
                    # (see test_get_partial_value_of_a_list_iquib_with_boolean_indexing)
                    # assert len(self.cache.get_uncached_paths(truncated_path)) == 0

        return result

    @load_source_locations_before_running
    def _get_args_and_kwargs_valid_at_quibs_to_paths(self, quibs_to_valid_paths: Dict[Quib, Optional[Path]]):
        """
        Prepare arguments to call self.func with - replace quibs with values valid at the given path
        """

        def _transform_data_source_quib(quib):
            # If the quib is a data source, and we didn't see it in the result, we don't need it to be valid at any
            # paths (it did not appear in quibs_to_paths)
            path = quibs_to_valid_paths.get(quib)
            return quib.get_value_valid_at_path(path)

        def _transform_parameter_source_quib(quib):
            # This is a paramater quib- we always need a parameter quib to be completely valid regardless of where
            # we need ourselves (this quib) to be valid
            return quib.get_value_valid_at_path([])

        new_args, new_kwargs = self.transform_sources_in_args_kwargs(
            transform_data_source_func=_transform_data_source_quib,
            transform_parameter_func=_transform_parameter_source_quib
        )

        return new_args, new_kwargs

    def invalidate_cache_at_path(self, path: Path):
        if self.cache is not None:
            self.cache.set_invalid_at_path(path)

    def run(self, valid_paths: List[Union[None, Path]]) -> Any:
        """
        Get the actual data that this quib represents, valid at the paths given in the argument.
        The value will necessarily return in the shape of the actual result, but only the values at the given path
        are guaranteed to be valid
        """
        self._initialize_graphics_collections()

        start_time = perf_counter()

        result = self._run_on_uncached_paths_within_path(valid_paths)

        elapsed_seconds = perf_counter() - start_time

        if self._should_cache(result, elapsed_seconds):
            self._caching = True
        if not self._caching:
            self.cache = None

        return result
