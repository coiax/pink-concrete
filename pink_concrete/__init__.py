from __future__ import generator_stop

import sys
import time
import json
import pathlib
import typing
import multiprocessing
import random
import collections

import PIL.Image
from PIL import UnidentifiedImageError
from PIL.PngImagePlugin import PngInfo
import anvil
from tqdm import tqdm

from . import styling, stitch
from .mtime import max_mtime_from_region

# Version of metadata stored in PNG images, increment
# when non-compatible changes are made
VERSION = 3

def get_chunk_stacks(
    chunk: 'Chunk'
)-> typing.Dict[typing.Tuple[int, int], typing.Iterator['Block']]:
    """For a given chunk generate a dict of translucent and the
    top opaque blocks for each of the internal x,z pairs"""
    # Default dict that lets us skip completed block stacks
    top_found = collections.defaultdict(int)
    complete_set = set()
    chunk_stacks = collections.defaultdict(list)

    y = 255
    for section_index in reversed(range(16)):
        section: typing.Optional['nbt.TAG_Compound']
        try:
            section = chunk.get_section(section_index)
        except KeyError as error:
            if error.args[0] == "Tag Sections does not exist":
                return chunk_stacks
            else:
                raise
        section_stacks = collections.defaultdict(list)

        assert y >= 15

        # The following section is to work around the early generator
        # exit in anvil/chunk.py:190
        if section is None or section.get("BlockStates") is None:
            y -= 16
            continue

        x = 0
        z = 0
        local_y = y - 16
        for block in chunk.stream_blocks(index=0, section=section):
            # As we are working from the top, only process if an opaque
            # block has not been found or is below (so in current section)
            if top_found[x, z] < local_y:
                if styling.is_opaque(block.name()):
                    top_found[x, z] = local_y
                    complete_set.add((x, z))
 
                    section_stacks[x, z].append(block)
                elif styling.is_translucent(block.name()):
                    section_stacks[x, z].append(block)

            x += 1
            if x % 16 == 0:
                x = 0
                z += 1

                if z % 16 == 0:
                    z = 0
                    local_y += 1

        # Add section to total stack
        for x,z in section_stacks:
            chunk_stacks[x, z].extend(reversed(section_stacks[x, z]))
        y -= 16
        if len(complete_set) == 256:
            return chunk_stacks
    # Return something anyway
    return chunk_stacks

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

def _skip(image_path: 'Path', mtime: int) -> bool:
    # Determine if the existing image can be reused
    try:
        existing = PIL.Image.open(image_path)
    except (FileNotFoundError, UnidentifiedImageError):
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
        version = information["version"]
        missing = information["missing"]
        stored_mtime = information["mtime"]
    except KeyError:
        return False

    if version != VERSION:
        return False

    if missing:
        return False

    if mtime > stored_mtime:
        return False

    return True


def render_region(region_path: 'Path', image_path: 'Path', mtime: int):
    # We don't want any previous missing blocks from previous renders
    # being included in this region
    styling.MISSING_STYLE.clear()

    # anvil can't cope with pathlib paths
    region = anvil.Region.from_file(str(region_path))

    image = PIL.Image.new("RGBA", (512, 512))
    pixels = image.load()


    for chunk in chunks_in_region(region):
        chunk_x = chunk.x.value
        chunk_z = chunk.z.value

        # Round the base down to the nearest multiple of 32 (which
        # includes negative multiples)
        base_x = (chunk_x >> 5) << 5
        base_z = (chunk_z >> 5) << 5

        # chunk_x - base_x will be between 0 and 32, it's the coordinates
        # of the chunk within the region
        x_offset = (chunk_x - base_x) * 16
        z_offset = (chunk_z - base_z) * 16

        stackdict = get_chunk_stacks(chunk)
        for x, z in stackdict:
            # Although PIL advises against raw pixel manipulation
            # currently the calculation of the pixel's colour is
            # 99% of the CPU time, so it really doesn't matter
            rgba = styling.block_stack_to_colour(stackdict[x,z])

            # putpixel doesn't work on cpython for some reason???
            pixels[x_offset + x, z_offset + z] = rgba

    information = {
        "version": VERSION,
        "mtime": mtime,
        "missing": sorted(styling.MISSING_STYLE),
    }

    pnginfo = PngInfo()
    pnginfo.add_text("pink_concrete", json.dumps(information))

    image.save(image_path, 'PNG', pnginfo=pnginfo)

    if styling.MISSING_STYLE:
        from pprint import pprint
        print("Missing from {region}".format(region=region_path.name))
        pprint(styling.MISSING_STYLE)


def _xz_from_string(str) -> typing.Tuple[int, int]:
    assert str.count(".") == 3
    r, x, z, extension = str.split(".")
    return int(x), int(z)


class Job(typing.NamedTuple):
    region_path: 'Path'
    image_path: 'Path'
    mtime: int


def _make_jobs(
    region_folder: 'Path',
    output_folder: 'Path',
) -> typing.List['Job']:
    jobs = []

    for region_path in region_folder.glob("*.mca"):
        image_name = region_path.name[:-4] + ".png"
        image_path = output_folder / image_name

        with open(region_path, 'rb') as f:
            # Read first 2KB header of region file
            header = f.read(8192)

        mtime = max_mtime_from_region(header)

        if _skip(image_path, mtime):
            continue

        jobs.append(Job(region_path, image_path, mtime))

    return jobs

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'folder',
        help='The minecraft "region" folder, containing .mca files.',
        type=pathlib.Path,
    )
    parser.add_argument(
        '-j',
        '--jobs',
        nargs='?',
        default=1,
        const=multiprocessing.cpu_count(),
        type=int,
        help=(
            "The number of processes to use when rendering the map. "
            "Default is 1 core, running the map renderer in a single "
            "process. If specified without a number, uses the number "
            "of CPU cores."
        ),
    )
    parser.add_argument(
        '--job-order',
        help=(
            "What order the jobs should run in, such as smallest region "
            "or closest region to the origin, or random."
        ),
        default=None,
    )
    parser.add_argument(
        '-o',
        '--output',
        help=(
            "Output folder, where to put the images. Note that existing "
            "images in the folder will be scanned, to determine if a "
            "re-render is required."
        ),
        type=pathlib.Path,
        default=".",
    )
    parser.add_argument(
        '--stitch-only',
        action='store_true',
        help=(
            "Skip the rendering step; and only perform the "
            "\"stitching\" together of the final image."
        ),
    )

    args = parser.parse_args()

    region_folder = args.folder
    output_folder = args.output

    assert region_folder.is_dir()

    try:
        output_folder.mkdir(exist_ok=True)
    except FileExistsError:
        print("Bad destination, must be folder.", file=sys.stderr)
        sys.exit(1)

    assert args.jobs >= 1

    jobs = _make_jobs(region_folder, output_folder)

    def closest_to_zero(tup):
        # Check the regions closest to 0,0 first
        region_path, image_path, mtime = tup
        x, z = _xz_from_string(str(region_path.name))
        return x**2 + z**2

    def smallest(tup):
        # Check the smallest (file-size) regions first
        region_path, image_path, mtime = tup
        return region_path.stat().st_size

    if args.job_order == 'closest_to_zero':
        jobs.sort(key=closest_to_zero)

    elif args.job_order == 'smallest':
        jobs.sort(key=smallest)

    elif args.job_order == 'random':
        random.shuffle(jobs)

    elif args.job_order is not None:
        print("Unrecognised job order: ", args.job_order, file=sys.stderr)
        sys.exit(1)

    if not args.stitch_only:
        with tqdm(total=len(jobs)) as pbar:
            if args.jobs > 1:
                with multiprocessing.Pool(args.jobs) as pool:
                    results = []
                    for arguments in jobs:
                        results.append(pool.apply_async(
                            render_region,
                            arguments,
                        ))

                    while results:
                        for result in list(results):
                            if result.ready():
                                # .get() will throw an exception if
                                # one occured.
                                result.get()
                                pbar.update()
                                results.remove(result)
                        pbar.refresh()
                        time.sleep(1)

                    pool.close()
                    pool.join()

            else:
                for arguments in jobs:
                    render_region(*arguments)
                    pbar.update()

    mapmap = {}

    # Need to cap the maximum number of regions we include
    # in the final stitching, otherwise the final image is too large
    # and OOMs my machine
    sanity_zone = 10
    for image_path in output_folder.glob("*.png"):
        if image_path.name.count(".") != 3:
            continue
        x, z = _xz_from_string(image_path.name)
        if abs(x) > sanity_zone or abs(z) > sanity_zone:
            continue
        mapmap[x, z] = image_path

    stitch.stitch(mapmap)
