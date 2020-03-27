import typing

import PIL.Image

XZ = typing.Tuple[int, int]


def stitch(mapmap: typing.Mapping[XZ, typing.Any]):
    max_x = max(xz[0] for xz in mapmap)
    max_z = max(xz[1] for xz in mapmap)
    min_x = min(xz[0] for xz in mapmap)
    min_z = min(xz[1] for xz in mapmap)

    x_width = (max_x - min_x + 1) * 512
    z_width = (max_z - min_z + 1) * 512

    atlas = PIL.Image.new("RGBA", (x_width, z_width))
    for z in range(min_z, max_z + 1):
        for x in range(min_x, max_x + 1):
            try:
                piece = mapmap[x,z]
            except KeyError:
                continue
            x_offset = x - min_x
            z_offset = z - min_z

            atlas.paste(piece, (x_offset * 512, z_offset * 512))

    bbox = atlas.getbbox()

    cropped = atlas.crop(bbox)
    cropped.save("atlas.png")
