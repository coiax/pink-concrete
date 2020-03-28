import typing
import json
import functools
import pathlib
import random
import collections

def _get_styling():
    module_path = pathlib.Path(__file__)
    styling_json_path = module_path.parent / 'styling.json'

    with open(styling_json_path, 'r') as f:
        styling_json = json.load(f)

    for key in list(styling_json):
        value = styling_json[key]
        if isinstance(value, str) and value.startswith('#'):
            r = int(value[1:3], 16)
            g = int(value[3:5], 16)
            b = int(value[5:7], 16)

            rgba = (r, g, b, 255)
            styling_json[key] = rgba

    clean = False
    sanity = 1000
    while not clean and sanity > 0:
        sanity -= 1
        clean = True
        for key in list(styling_json):
            value = styling_json[key]
            if isinstance(value, str):
                styling_json[key] = styling_json[value]
                clean = False

    if sanity == 0:
        raise Exception("Cleaning while-loop never finished, loop?")

    for key in list(styling_json):
        value = styling_json[key]

        cleaned = tuple(value)
        while len(cleaned) < 4:
            cleaned += (255,)

        styling_json[key] = value

    return styling_json


RGBA = typing.Tuple[int, int, int, int]
FractionalRGBA = typing.Tuple[float, float, float, float]

STYLEMAP: typing.Mapping[str, RGBA] = _get_styling()

MISSING_STYLE = set()


@functools.lru_cache(maxsize=255)
def is_opaque(block_name) -> bool:
    try:
        style = STYLEMAP[block_name]
    except KeyError:
        MISSING_STYLE.add(block_name)
        return True
    else:
        return style[3] == 255




def _scale_255_to_1(rgba: RGBA) -> FractionalRGBA:
    return (
        rgba[0] / 255,
        rgba[1] / 255,
        rgba[2] / 255,
        rgba[3] / 255,
    )


def _scale_1_to_255(fractional_rgba: FractionalRGBA) -> RGBA:
    return (
        int(fractional_rgba[0] * 255),
        int(fractional_rgba[1] * 255),
        int(fractional_rgba[2] * 255),
        int(fractional_rgba[3] * 255),
    )

def _mix(background: RGBA, foreground: RGBA) -> RGBA:
    bg = _scale_255_to_1(background)
    fg = _scale_255_to_1(foreground)

    a = 1 - (1 - fg[3]) * (1 - bg[3])
    r = fg[0] * fg[3] / a + bg[0] * bg[3] * (1 - fg[3]) / a
    g = fg[1] * fg[3] / a + bg[1] * bg[3] * (1 - fg[3]) / a
    b = fg[2] * fg[3] / a + bg[2] * bg[3] * (1 - fg[3]) / a

    return _scale_1_to_255((r,g,b,a))


def block_stack_to_colour(stack: typing.Iterable['Block']) -> RGBA:
    colour: typing.Optional[RGBA] = None
    for block in stack:
        rgba = style_of_block(block.name())
        if rgba[3] == 0:
            continue

        if colour is None:
            colour = rgba
        else:
            colour = _mix(rgba, colour)

    if colour is None:
        # Transparent white
        return (255, 255, 255, 0)
    else:
        return colour

@functools.lru_cache(maxsize=255)
def style_of_block(
    block_name,
    default: typing.Any = (127, 127, 127, 255)
) -> RGBA:
    try:
        return STYLEMAP[block_name]
    except KeyError:
        MISSING_STYLE.add(block_name)

        return default

