from __future__ import annotations

from dataclasses import dataclass


LAPTOP_WIDTH = 1366
SMALL_LAPTOP_WIDTH = 1280


@dataclass(frozen=True)
class ShellLayoutMetrics:
    sidebar_width: int
    content_pad_x: int
    content_pad_y: int


@dataclass(frozen=True)
class CatalogFilterBarLayout:
    filter_columns: int
    search_row: int
    search_column: int
    search_columnspan: int
    button_row: int
    button_column: int
    button_columnspan: int


@dataclass(frozen=True)
class PriceProposalWorkspaceLayout:
    list_weight: int
    detail_weight: int
    column_gap: int
    card_pad_x: int
    candidate_min_width: int
    id_column_chars: int
    type_column_chars: int
    price_column_chars: int
    control_gap: int
    action_gap: int
    name_wraplength: int


def shell_layout_metrics(viewport_width: int) -> ShellLayoutMetrics:
    """Keep navigation visible while giving laptop screens more content width."""
    if viewport_width <= SMALL_LAPTOP_WIDTH:
        return ShellLayoutMetrics(sidebar_width=232, content_pad_x=12, content_pad_y=12)
    if viewport_width <= LAPTOP_WIDTH:
        return ShellLayoutMetrics(sidebar_width=244, content_pad_x=16, content_pad_y=14)
    return ShellLayoutMetrics(sidebar_width=258, content_pad_x=20, content_pad_y=18)


def catalog_filter_bar_layout(available_width: int, *, keep_search_buttons_inline: bool = False) -> CatalogFilterBarLayout:
    """Return a structural layout that prevents the shared filter bar overflowing."""
    width = int(available_width or 0)
    if width <= 700:
        if keep_search_buttons_inline:
            return CatalogFilterBarLayout(
                filter_columns=2,
                search_row=2,
                search_column=0,
                search_columnspan=1,
                button_row=2,
                button_column=1,
                button_columnspan=1,
            )
        return CatalogFilterBarLayout(
            filter_columns=2,
            search_row=2,
            search_column=0,
            search_columnspan=2,
            button_row=3,
            button_column=0,
            button_columnspan=2,
        )
    if width <= 980:
        return CatalogFilterBarLayout(
            filter_columns=4,
            search_row=1,
            search_column=0,
            search_columnspan=3,
            button_row=1,
            button_column=3,
            button_columnspan=1,
        )
    return CatalogFilterBarLayout(
        filter_columns=4,
        search_row=0,
        search_column=4,
        search_columnspan=1,
        button_row=0,
        button_column=5,
        button_columnspan=1,
    )


def price_proposal_workspace_layout(viewport_width: int) -> PriceProposalWorkspaceLayout:
    """Give the item picker priority on small screens without hiding actions."""
    width = int(viewport_width or 0)
    if width <= 1100:
        return PriceProposalWorkspaceLayout(
            list_weight=6,
            detail_weight=2,
            column_gap=8,
            card_pad_x=10,
            candidate_min_width=480,
            id_column_chars=10,
            type_column_chars=9,
            price_column_chars=9,
            control_gap=6,
            action_gap=4,
            name_wraplength=260,
        )
    if width <= LAPTOP_WIDTH:
        return PriceProposalWorkspaceLayout(
            list_weight=5,
            detail_weight=2,
            column_gap=10,
            card_pad_x=12,
            candidate_min_width=560,
            id_column_chars=12,
            type_column_chars=10,
            price_column_chars=10,
            control_gap=8,
            action_gap=5,
            name_wraplength=360,
        )
    return PriceProposalWorkspaceLayout(
        list_weight=5,
        detail_weight=2,
        column_gap=14,
        card_pad_x=16,
        candidate_min_width=720,
        id_column_chars=14,
        type_column_chars=12,
        price_column_chars=11,
        control_gap=10,
        action_gap=6,
        name_wraplength=520,
    )


def modal_dimensions_for_viewport(
    screen_width: int,
    screen_height: int,
    requested_width: int,
    requested_height: int,
    *,
    min_width: int = 640,
    min_height: int = 420,
    margin: int = 40,
) -> tuple[int, int, int, int]:
    """Constrain modal size and minimums to the actual viewport."""
    usable_width = max(1, int(screen_width) - (margin * 2))
    usable_height = max(1, int(screen_height) - (margin * 2))
    width = min(int(requested_width), usable_width)
    height = min(int(requested_height), usable_height)
    return width, height, min(min_width, width), min(min_height, height)


def widget_screen_size(widget: object, *, default_width: int = 1366, default_height: int = 768) -> tuple[int, int]:
    try:
        width = int(getattr(widget, "winfo_screenwidth")())
        height = int(getattr(widget, "winfo_screenheight")())
        if width > 0 and height > 0:
            return width, height
    except Exception:
        pass
    return default_width, default_height


def center_window_safely(window: object, width: int, height: int) -> None:
    """Center real Tk windows and keep test doubles on a compatible geometry path."""
    try:
        from futonhub.ui.windowing import center_window

        center_window(window, width, height)
        return
    except Exception:
        pass
    try:
        getattr(window, "geometry")(f"{int(width)}x{int(height)}")
    except Exception:
        return


def set_minsize_safely(window: object, width: int, height: int) -> None:
    try:
        getattr(window, "minsize")(int(width), int(height))
    except Exception:
        return
