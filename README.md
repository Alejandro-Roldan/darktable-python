# Darktable Python Library
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> This is a fork from [ungive/darktable-python](https://github.com/ungive/darktable-python)
>
> It extends the project to cover the cli arguments that were missing
>
> Extracts more info from the db of photos
>
> And I made some changes to the code structure that makes it non-backwards-compatible

The aim of this project is the following:

- Provide a Python library
  that allows programmatic access to your Darktable library
- Provide a way to programmatically export photos from your Darktable library
- Form the foundation for creating a web API
  to access and export Darktable images
- ...

## Setup

```sh
git clone https://github.com/Alejandro-Roldan/darktable-python
python -m pip install ./darktable-python
```


## Simple Example

```python
from darktable import darktable, exporter, formats

CLI_BIN = "/usr/bin/darktable-cli"
CONFIG_DIR = "$HOME/.config/darktable/"
OUT_DIR = "$HOME/Pictures/"

CM_INCH = 0.394

# A bit extra
dpi = 300
max_width_cm = 15
max_height_cm = 15
max_width = max_width_cm * dpi * CM_INCH
max_height = max_height_cm * dpi * CM_INCH

jxl_format = formats.JXL(
    bpp=16, pixel_type=False, quality=100, original=False, effort=7, tier=0
)
cache_ = exporter.ExportCache("example")
# An example splicitly defining all possible options
jxl_exporter_options = {
    "cli_bin": CLI_BIN,
    "config_dir": CONFIG_DIR,
    "filename_format": "$(FILE.NAME)",
    "format_options": jxl_format,
    # Optinal arguments
    "width": max_width,
    "height": max_height,
    "hq_resampling": 0,
    "upscale": False,
    # The name of a style that exists in your darktable
    "style": "example",
    "style_overwrite": False,
    "apply_custom_presets": True,
    "icc_type": formats.OutputColorProfile.ADOBERGB,
    "icc_file": "",
    "icc_intent": formats.RenderingIntent.PERCEPTUAL,
    "debug": True,
    # Defining this will only work for jpgs or pngs
    "exif_artist": None,
    "exif_copyright": None,
    "xmp_changes": [remove_exposure],
}

# Open darktable library
with darktable.DarktableLibrary(CONFIG_DIR) as library:
    # And search for images labeled in purple
    for_print_photo_list = [
        photo
        for photo in library.get_photos()
        if darktable.ColorLabel.PURPLE in photo.color_labels
    ]

# Loop and export
for photo in for_print_photo_list:
    exporter.export_with_cache(cache_, photo, OUT_DIR, **jxl_exporter_options)

def remove_exposure(in_parsed_xmp):
    # Disables all instances of exposure module
    darktable.xmp_disable_operation(in_parsed_xmp, "exposure", None)
```


## Check for XMP inconsistencies

```
python database_inconsistencies.py /path/to/your/darktable/config
```

The first argument must be the path to your Darktable config directory
that contains `library.db` and `data.db`.
The script opens these database files in read-only mode
with the SQLite URL `file:{db_path}?mode=ro`,
no data is modified.
XMP files are also only opened in read-mode and never written to.

Relevant Darktable issue:
https://github.com/darktable-org/darktable/issues/15330


## Documentation

`export()`
```
Exports a photo to a directory through Darktable's CLI interface.
Returns a copy of the photo instance where export_filepath is set.

*Neccesary arguments:
    photo: str | os.PathLike | darktable.Photo  Path or Photo object to the image
                                                to export

    out_dir: str | os.PathLike          Path to the output directory

    cli_bin: str  | os.PathLike         Path to darktable-cli program

    config_dir: str  | os.PathLike      Path to darktable's config dir to use

    filename_format: str                Filename format to use. Darktable variables
                                        supported

    format_options: formats._ImgFormat  Format options to use. Defined with a
                                        formats._ImgFormat child class

*Optional Arguments
    width: int                          Max width. Defaults to 0 (image width)

    height: int                         Max height. Defaults to 0 (image height)

    hq_resampling: bool                 Use high quality resampling. Defaults to
                                        True

    upscale: bool                       Allow upscaling. Defaults to False

    style: str                          Style name to apply. If used config_dir must
                                        also be supplied. Defaults to no style

    style_overwrite: bool               Overwrite instead of append. Defaults to
                                        False

    apply_custom_presets: bool          Load data.db. Allows use of styles, but
                                        prevents multi db instance. Defaults to True

    icc_type: formats.OutputColorProfile    ICC profile. Defaults to NONE

    icc_file: str | PathLike            ICC file. Defaults to empty str

    icc_intent: formats.RenderingIntent Rendering Intent (when using LittleCMS2).
                                        Defaults to IMAGE_SETTINGS

    debug: bool                         Print debug info

    exif_artist: str                    EXIF artist data to apply

    exif_copyright: str                 EXIF copyright data to apply

    xmp_changes: list                   List of external changes to apply to the
                                        image export. Only applied if calling export
                                        with a Photo object

More info on the darktable-cli arguments:
https://docs.darktable.org/usermanual/4.0/en/special-topics/program-invocation/darktable-cli
https://docs.darktable.org/usermanual/4.0/en/special-topics/program-invocation/darktable
```

`export_with_cache()`
```
Exports a photo to a directory through Darktable's CLI interface, but only if there are
changes to the XMP or it hasn't been exported yet.

Same arguments with the added neccessary argument:
    cache_: ExportCache     the ExportCache instance to use
```

