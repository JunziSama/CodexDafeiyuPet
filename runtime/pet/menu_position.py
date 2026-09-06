from __future__ import annotations


def above_pet(
    pet: tuple[int, int, int, int],
    menu: tuple[int, int],
    screen: tuple[int, int, int, int],
    gap: int = 8,
) -> tuple[int, int]:
    """Center a menu above the pet, clamped to the available screen."""
    pet_x, pet_y, pet_w, pet_h = pet
    menu_w, menu_h = menu
    screen_x, screen_y, screen_w, screen_h = screen
    max_x = max(screen_x, screen_x + screen_w - menu_w)
    max_y = max(screen_y, screen_y + screen_h - menu_h)
    x = pet_x + (pet_w - menu_w) // 2
    y = pet_y - menu_h - gap
    if y < screen_y:
        y = pet_y + pet_h + gap
    return min(max(x, screen_x), max_x), min(max(y, screen_y), max_y)

