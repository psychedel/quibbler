import contextlib
from dataclasses import dataclass, field
from typing import List, Set, Dict, Tuple

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.widgets import AxesWidget

from pyquibbler.graphics.attribute_copying import update_new_artists_from_previous_artists
from pyquibbler.quib.function_quibs.external_call_failed_exception_handling import \
    external_call_failed_exception_handling
from pyquibbler.graphics.global_collecting import ArtistsCollector, AxesWidgetsCollector
from pyquibbler.graphics.utils import get_artist_array, \
    get_axeses_to_array_names_to_starting_indices_and_artists, remove_artist,\
    get_axeses_to_array_names_to_artists, ArrayNameToArtists


@dataclass
class GraphicsCollection:
    widgets: List = field(default_factory=list)
    artists: List = field(default_factory=list)

    def _get_artists_still_in_axes(self):
        """
        Remove any artists that we created that were removed by another means other than us (for example, cla())
        """
        return [artist for artist in self.artists if artist in get_artist_array(artist)]

    def remove_artists(self):
        for artist in self.artists:
            remove_artist(artist)
        self.artists = []

    def _handle_new_artists(self,
                            kwargs_specified_in_artists_creation,
                            previous_axeses_to_array_names_to_indices_and_artists,
                            new_artists: Set[Artist]):
        """
        Handle new artists and update graphics collection appropriately
        """
        self.artists = list(new_artists)
        current_axeses_to_array_names_to_artists = get_axeses_to_array_names_to_artists(new_artists)
        update_new_artists_from_previous_artists(kwargs_specified_in_artists_creation,
                                                 previous_axeses_to_array_names_to_indices_and_artists,
                                                 current_axeses_to_array_names_to_artists)

    def _handle_new_widgets(self, new_widgets: List[AxesWidget]):
        """
        Handle new widgets and update the graphics collection appropriately
        """
        from .widget_utils import destroy_widgets, transfer_data_from_new_widgets_to_previous_widgets
        if len(self.widgets) > 0:
            destroy_widgets(new_widgets)
            transfer_data_from_new_widgets_to_previous_widgets(previous_widgets=self.widgets,
                                                               new_widgets=new_widgets)
        else:
            self.widgets = new_widgets

    @contextlib.contextmanager
    def track(self, kwargs_specified_in_artists_creation: Set[str]):
        self.artists = self._get_artists_still_in_axes()

        # Get the *current* artists together with their starting indices (per axes per artists array) so we can
        # place the new artists we create in their correct locations
        previous_axeses_to_array_names_to_indices_and_artists = \
            get_axeses_to_array_names_to_starting_indices_and_artists(self.artists)
        self.remove_artists()

        # TODO: move quibguard to outside quib
        with ArtistsCollector() as artists_collector, AxesWidgetsCollector() as widgets_collector, \
                external_call_failed_exception_handling():
            yield

        # TODO: Move this logic somewhere else
        # if len(self.widgets) > 0 and isinstance(ret_val, AxesWidget):
        #     assert len(widgets_collector.objects_collected) == 1
        #     assert len(graphics_collection.widgets) == 1
        #     ret_val = list(graphics_collection.widgets)[0]
        # We don't allow returning quibs as results from functions
        # from pyquibbler.quib import Quib
        # if isinstance(ret_val, Quib):
        #     ret_val = ret_val.get_value()
        #

        self._handle_new_widgets(new_widgets=widgets_collector.objects_collected)
        self._handle_new_artists(kwargs_specified_in_artists_creation,
                                 previous_axeses_to_array_names_to_indices_and_artists,
                                 new_artists=artists_collector.objects_collected)
