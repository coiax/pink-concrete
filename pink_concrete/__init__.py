from __future__ import generator_stop

import json
import pathlib
import typing
import multiprocessing
import random

import PIL.Image
from PIL.PngImagePlugin import PngInfo
import anvil

from . import styling, stitch

VERSION = 1

def top_down_until(chunk: 'Chunk', x: int, z: int) -> typing.Iterator['Block']:
    """Return an iterator of blocks until the returned block is
    opaque. If no blocks are opaque, return all of them."""

    assert 0 <= x <= 15
    assert 0 <= z <= 15

    y = 255
    while y > 0:
        try:
            block = chunk.get_block(x, y, z)
        except KeyError as error:
            if error.args[0] == 'Tag Sections does not exist':
                continue
            else:
                raise
        yield block
        if styling.is_opaque(block):
            break
        y -= 1

def top_downs_in_chunk(
    chunk: 'Chunk'
)-> typing.Iterator[typing.Tuple[int, int, typing.Iterator['Block']]]:
    """For a given chunk, return the first non-air block (from top to bottom)
    for each of the internal x,z pairs."""
    for x in range(16):
        for z in range(16):
            yield x, z, top_down_until(chunk, x, z)


def chunks_in_region(region: 'Region') -> typing.Iterator['Chunk']:
    for z in range(32):
        for x in range(32):
            try:
                yield region.get_chunk(x, z)
            except Exception as error:
                if error.args[0] == 'Unexistent chunk':
                    pass
                else:
                    raise

def _skip(image_filename: str, mtime: int) -> bool:
    try:
        existing = PIL.Image.open(image_filename)
    except FileNotFoundError:
        return False

    try:
        value = existing.text["pink_concrete"]
    except KeyError:
        return False

    try:
        information = json.loads(value)
    except json.JSONDecodeError:
        return False

    try:
        version = information['version']
        stored_mtime = information['mtime']
    except KeyError:
        return False

    if version != VERSION:
        return False

    if mtime != stored_mtime:
        return False

    return True


def render_region(region_path, image_filename: str, mtime: int):
    if _skip(image_filename, mtime):
        return
    # Determine if the existing image

    region = anvil.Region.from_file(str(region_path))

    image = PIL.Image.new("RGBA", (512, 512))
    pixels = image.load()


    for chunk in chunks_in_region(region):
        chunk_x = chunk.x.value
        chunk_z = chunk.z.value

        base_x = (chunk_x >> 5) << 5
        base_z = (chunk_z >> 5) << 5

        x_offset = (chunk_x - base_x) * 16
        z_offset = (chunk_z - base_z) * 16

        for x, z, block_stack in top_downs_in_chunk(chunk):
            rgba = styling.block_stack_to_colour(block_stack)
            pixels.putpixel((x_offset + x, z_offset + z), rgba)

    information = {
        "version": VERSION,
        "mtime": mtime,
    }

    pnginfo = PngInfo()
    pnginfo.add_text("pink_concrete", json.dumps(information))

    image.save(image_filename, 'PNG', pnginfo=pnginfo)

    from pprint import pprint
    pprint(styling.MISSING_STYLE)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'folder',
        help='The minecraft "region" folder, containing .mca files.'
    )
    parser.add_argument(
        '-j',
        '--jobs',
        default=multiprocessing.cpu_count(),
        type=int,
    )
    parser.add_argument(
        '--stitch-only',
        action='store_true',
    )

    args = parser.parse_args()

    folder = pathlib.Path(args.folder)
    assert folder.is_dir()
    assert args.jobs >= 1

    region_files = []

    for path in folder.glob("*.mca"):
        mtime = int(path.stat().st_mtime)
        region_files.append((mtime, path))

    regions = []

    jobs = []

    for mtime, region_path in region_files:
        image_name = region_path.name.replace(".mca", ".png")

        jobs.append((region_path, image_name, mtime))

    random.shuffle(jobs)

    if not args.stitch_only:
        if args.jobs > 1:
            pool = multiprocessing.Pool(args.jobs)

            pool.starmap(render_region, jobs)
        else:
            for arguments in jobs:
                render_region(*arguments)

    mapmap = {}

    for filename in image_files:
        r, x, z, png = filename.split(".")
        mapmap[int(x),int(z)] = PIL.Image.open(filename)

    stitch.stitch(mapmap)
