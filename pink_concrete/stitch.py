import typing

import pathlib
import PIL.Image

XZ = typing.Tuple[int, int]


def stitch(mapmap: typing.Mapping[XZ, str]):
    max_x = max(xz[0] for xz in mapmap)
    max_z = max(xz[1] for xz in mapmap)
    min_x = min(xz[0] for xz in mapmap)
    min_z = min(xz[1] for xz in mapmap)

    x_width = (max_x - min_x + 1) * 512
    z_width = (max_z - min_z + 1) * 512

    atlas = PIL.Image.new("RGBA", (x_width, z_width))
    for z in range(min_z, max_z + 1):
        for x in range(min_x, max_x + 1):
            if (x,z) not in mapmap:
                continue

            image_path = mapmap[x,z]
            x_offset = x - min_x
            z_offset = z - min_z

            try:
                with PIL.Image.open(image_path) as segment:
                    atlas.paste(segment, (x_offset * 512, z_offset * 512))
            except FileNotFoundError:
                continue

    bbox = atlas.getbbox()

    cropped = atlas.crop(bbox)
    atlas.close()

    # The original c10t maps were rotated like this, may as well
    # make this the default rotation for now.
    final = cropped.rotate(270)
    cropped.close()

    parent = image_path.parent

    atlas_path = parent / "atlas.png"

    final.save(atlas_path)
