from typing import TYPE_CHECKING, Any, Callable, Iterable, List

from matplotlib.backend_bases import MouseEvent, PickEvent

from pyquibbler.quib.assignment.assignment import QuibWithAssignment
from pyquibbler.quib.override_choice import AssignmentCancelledByUserException

if TYPE_CHECKING:
    from pyquibbler.quib.graphics import GraphicsFunctionQuib

GRAPHICS_REVERSE_ASSIGNERS = {}


def graphics_inverse_assigner(graphics_func_name_to_handle: str):
    """
    Decorate a function capable of inverse assigning to argument quibs given a mouse event
    """

    def _decorator(func: Callable[[PickEvent, MouseEvent, 'GraphicsFunctionQuib'], List[QuibWithAssignment]]):
        GRAPHICS_REVERSE_ASSIGNERS[graphics_func_name_to_handle] = func
        return func

    return _decorator


def inverse_assign_drawing_func(drawing_func: Callable,
                                args: Iterable[Any],
                                pick_event: PickEvent,
                                mouse_event: MouseEvent):
    """
    Reverse a graphics function quib, assigning to all it's arguments values based on pick event and mouse event
    """
    from pyquibbler.quib import get_overrides_for_assignment_group
    inverse_assigner_func = GRAPHICS_REVERSE_ASSIGNERS.get(drawing_func.__qualname__)
    if inverse_assigner_func is not None:
        quibs_with_assignments = inverse_assigner_func(pick_event=pick_event, mouse_event=mouse_event, args=args)
        try:
            override_groups = get_overrides_for_assignment_group(quibs_with_assignments)
        except AssignmentCancelledByUserException:
            pass
        else:
            override_groups.apply()
