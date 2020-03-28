import pathlib
import tempfile

import pink_concrete

with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
    region_path = pathlib.Path("r.0.0.mca")
    image_path = pathlib.Path(tmp.name)
    mtime = 0

    pink_concrete.render_region(region_path, image_path, mtime)
    print(image_path)
