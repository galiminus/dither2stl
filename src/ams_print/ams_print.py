from PIL import Image
from typing_extensions import Annotated

from typing import Tuple
import typer

from .layer import Layer
from .threemf import ThreeMF

DEFAULT_SIZE = 70 # mm
DEFAULT_PIXEL_SIZE = 0.8 # mm
DEFAULT_GRID_DENSITY = 0.4

DEFAULT_COHESION_LAYER_HEIGHT = 1
DEFAULT_COLOR_LAYER_HEIGHT = 0.6

def ams_print(
    input: Annotated[str, "Path to the image to print"],
    output: Annotated[str, "Path to the output 3MF file"],

    size: Annotated[Tuple[int, int], typer.Option()] = (DEFAULT_SIZE, DEFAULT_SIZE),
    pixel_size: Annotated[float, "Size of the pixels in mm"] = DEFAULT_PIXEL_SIZE,

    grid_density: Annotated[float, "Density of the holes between 0 and 1"] = DEFAULT_GRID_DENSITY,

    cohesion_layer_height: Annotated[float, "Height of the cohesion layer in mm"] = DEFAULT_COHESION_LAYER_HEIGHT,
    color_layer_height: Annotated[float, "Height of the color layers in mm"] = DEFAULT_COLOR_LAYER_HEIGHT,

    layered: Annotated[bool, "Whether to use multiple layers (each color on top of the previous color)"] = False,

    dither: Annotated[bool, "Whether to dither the image"] = False,
    colors: Annotated[int, "Number of colors to use in the image quantization"] = 4,
):
    resolution = (
        int(size[0] / pixel_size),
        int(size[1] / pixel_size)
    )

    # If resolution isn't odd, we need to adjust the resolution to make it odd
    if resolution[0] % 2 == 0:
        resolution = (resolution[0] + 1, resolution[1])

    if resolution[1] % 2 == 0:
        resolution = (resolution[0], resolution[1] + 1)

    hole_count = (
        int(resolution[0] * grid_density),
        int(resolution[1] * grid_density)
    )

    scale = (
        size[0] / resolution[0],
        size[1] / resolution[1]
    )

    hole_frequency = (
        round((resolution[0] - pixel_size * scale[0] * hole_count[0]) / hole_count[0]) if hole_count[0] > 0 else 0,
        round((resolution[1] - pixel_size * scale[1] * hole_count[1]) / hole_count[1]) if hole_count[0] > 0 else 0
    )

    hole_offset = (
        int(hole_frequency[0] / 2),
        int(hole_frequency[1] / 2)
    )

    with Image.open(input) as image:
        if image.mode != "P":
            image = image.convert(
                "P",
                palette=Image.ADAPTIVE,
                colors=colors,
                dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
            )

        print(resolution)
        resized_image = image.resize((resolution[0], resolution[1]), Image.LANCZOS)
        resized_image_data = resized_image.load()

        palette = resized_image.getpalette()

        # Compute color configuration from the image palette
        color_mapping = []
        for index in range(0, len(palette), 3):
            color = tuple(palette[index:index + 3])
            color_mapping.append('#%02X%02X%02X' % color)

        cohesion_layer = Layer(size=(resized_image.size[0], resized_image.size[1]))

        color_layers = {}
        for index, color in enumerate(color_mapping):
            color_layers[color] = Layer(size=(resized_image.size[0], resized_image.size[1]))

        for x in range(resized_image.size[0]):
            for y in range(resized_image.size[1]):
                # Skip holes in the grid (ie, empty pixels) if grid is enabled
                x_hole_match = (hole_count[0] > 0 and (x + hole_offset[0]) % hole_frequency[0] == 0)
                y_hole_match = (hole_count[1] > 0 and (y + hole_offset[1]) % hole_frequency[1] == 0)

                if x_hole_match and y_hole_match:
                    continue

                # Add cohesion layer (ie, a tall pixel under each colored pixel to serve as a platform)
                cohesion_layer.plot(x=x, y=y)

                for index, color in enumerate(color_mapping):
                    # Since the image is quantized, we can compare the pixel value to the index
                    if resized_image_data[x, y] != index:
                        continue

                    color_layers[color].plot(x=x, y=y)

                    if layered:
                        # We must also add the previous color layers to sit on top of them.
                        for previous_index in range(index):
                            color_layers[color_mapping[previous_index]].plot(x=x, y=y)

        three_mf = ThreeMF()

        three_mf.add_object(
            object=cohesion_layer,
            name="cohesion layer",
            z=0,
            thickness=cohesion_layer_height,
            scale=scale
        )

        for index, (color, layer) in enumerate(color_layers.items()):
            # Start at the top of the cohesion layer
            z = cohesion_layer_height

            # Add the height of the previous color layers
            if layered:
                z += index * color_layer_height

            three_mf.add_object(
                object=layer,
                name=f"{color} layer",
                z=z,
                thickness=color_layer_height,
                scale=scale
            )

        three_mf.save(path=output)
