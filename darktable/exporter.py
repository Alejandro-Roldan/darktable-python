import os
import re
import subprocess
import tempfile
from io import TextIOWrapper
from os import PathLike, path
from pathlib import Path, PurePosixPath
from typing import Callable
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import exif
from PIL import Image

from darktable import darktable, formats
from darktable.args_hash import args_hash
from darktable.util import Cache, filehash, fullname

# TODO: move into .cache (and os dependant)
MODULE_DIR = path.abspath(path.dirname(__file__))
CACHE_FILENAME = os.path.splitext(__file__)[0] + ".cache.pkl"


class Export:
    def __init__(self, photo: darktable.Photo, filepath: str):
        self.photo: darktable.Photo = photo
        self.filepath: str = filepath

    @property
    def filepath(self):
        return self._filepath

    @filepath.setter
    def filepath(self, value):
        self._filepath = value
        self._width = None
        self._height = None

    @property
    def width(self):
        if self._width is None:
            self._read_export_attributes()
        return self._width

    @property
    def height(self):
        if self._height is None:
            self._read_export_attributes()
        return self._height

    @property
    def aspect_ratio(self):
        return float(self.width) / self.height

    def _read_export_attributes(self):
        with Image.open(self.filepath) as image:
            self._width, self._height = image.size

    def __repr__(self):
        return f"Export({self.filepath}, {self.photo})"


class ExportCache:
    def __init__(self, cache_key):
        # Create caches
        self.cache = Cache(
            path.join(MODULE_DIR, CACHE_FILENAME), prefix=f"{cache_key}:main:"
        )
        # I think this are only for this session
        self.cache_xmp_hashes = Cache(
            path.join(MODULE_DIR, CACHE_FILENAME), prefix=f"{cache_key}:xmp:"
        )
        self.cache_exported = Cache(
            path.join(MODULE_DIR, CACHE_FILENAME), prefix=f"{cache_key}:export:"
        )

        self._sess_exported = set()

    def sync(self, directory):
        """Removes all files in the given directory, except:
        - Files that have been exported during this session and
        - Files that would have been exported but already existed.
        The current session starts at object creation
        and is reset (cleared) whenever sync() is called.
        """
        for filepath_obj in Path(directory).glob("**/*"):
            filepath = str(filepath_obj)
            if filepath_obj.is_file() and filepath not in self._sess_exported:
                if not is_raw_photo_ext(path.splitext(filepath)[1]):
                    # Remove all data associated with the photo from the cache
                    # and delete the exported photo from the directory.
                    for cache_key in self.cache_exported.keys(has_value=filepath):
                        print(f"Removed from portfolio: {cache_key}")
                        self.cache_exported.delete(cache_key)
                        self.cache_xmp_hashes.delete(cache_key)
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass

        self._sess_exported.clear()


def export_with_cache(
    cache_: ExportCache,
    # Same arguments as export()
    photo: str | os.PathLike | darktable.Photo,
    out_dir: str | os.PathLike,
    cli_bin: str | PathLike,
    config_dir: str | PathLike,
    filename_format: str,
    format_options: formats._ImgFormat,
    width: int = 0,
    height: int = 0,
    hq_resampling: bool = True,
    upscale: bool = False,
    style: str = "",
    style_overwrite: bool = False,
    apply_custom_presets: bool = True,
    icc_type: formats.OutputColorProfile = formats.OutputColorProfile.NONE,
    icc_file: str | PathLike = "",
    icc_intent: formats.RenderingIntent = formats.RenderingIntent.IMAGE_SETTINGS,
    debug: bool = False,
    exif_artist: str = None,
    exif_copyright: str = None,
    xmp_changes: list = [],
) -> Export:
    """Exports a photo to a directory through Darktable's CLI interface,
    but only if there are changes to the XMP or it hasn't been exported yet.

    Same arguments as export() adding cache_ (a ExportCache instance)

    Returns a copy of the photo instance where export_filepath is set.
    """
    # Create id hash from arguments
    args_hash_ = args_hash(
        cli_bin=str(cli_bin),
        config_dir=str(config_dir),
        filename_format=str(filename_format),
        out_ext=str(format_options.ext),
        format_options=str(format_options),
        hq_resampling=str(hq_resampling),
        width=str(width),
        height=str(height),
        xmp_changes=str([fullname(func) for func in xmp_changes]),
    )
    # I think this part needs to be removed or kinda reworked
    if args_hash_ != cache_.cache.load("args_hash"):
        cache_.cache_xmp_hashes.prune()
        cache_.cache_exported.prune()
    cache_.cache.save("args_hash", args_hash_)

    # TODO hash the class instead and return this identifier
    cache_key = f"{photo.filepath}:{photo.version}"

    xmp_hash = filehash(photo.xmp_path)
    export_filepath = cache_.cache_exported.load(cache_key)
    if export_filepath is not None and path.exists(export_filepath):
        cache_._sess_exported.add(export_filepath)
        if xmp_hash == cache_.cache_xmp_hashes.load(cache_key):
            return Export(photo, filepath=export_filepath)

    exported = export(
        photo,
        out_dir,
        cli_bin,
        config_dir,
        filename_format,
        format_options,
        width,
        height,
        hq_resampling,
        upscale,
        style,
        style_overwrite,
        apply_custom_presets,
        icc_type,
        icc_file,
        icc_intent,
        debug,
        exif_artist,
        exif_copyright,
        xmp_changes,
    )
    cache_._sess_exported.add(export_filepath)

    cache_.cache_xmp_hashes.save(cache_key, xmp_hash)
    cache_.cache_exported.save(cache_key, exported.filepath)

    return exported


def export(
    photo: str | os.PathLike | darktable.Photo,
    out_dir: str | os.PathLike,
    cli_bin: str | PathLike,
    config_dir: str | PathLike,
    filename_format: str,
    format_options: formats._ImgFormat,
    width: int = 0,
    height: int = 0,
    hq_resampling: bool = True,
    upscale: bool = False,
    style: str = "",
    style_overwrite: bool = False,
    apply_custom_presets: bool = True,
    icc_type: formats.OutputColorProfile = formats.OutputColorProfile.NONE,
    icc_file: str | PathLike = "",
    icc_intent: formats.RenderingIntent = formats.RenderingIntent.IMAGE_SETTINGS,
    debug: bool = False,
    exif_artist: str = None,
    exif_copyright: str = None,
    xmp_changes: list = [],
) -> Export:
    """Exports a photo to a directory through Darktable's CLI interface.
    Returns a copy of the photo instance where export_filepath is set.

    *Neccesary arguments:
        photo: str | os.PathLike | darktable.Photo  Path or Photo object to the image
                                                    to export

        out_dir: str | os.PathLike          Path to the output directory

        cli_bin: str | os.PathLike          Path to darktable-cli program

        config_dir: str | os.PathLike       Path to darktable's config dir to use

        filename_format: str                Filename format to use. Darktable variables
                                            supported

        format_options: formats._ImgFormat  Format options to use. Defined with a
                                            formats._ImgFormat derived class

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
    """

    def _generate_input_filelist():
        # TODO convert any path to pure posix paths (since that's required here)
        if isinstance(photo, darktable.Photo):
            xmp_path = photo.xmp_path
            # Apply changes to xmp if needed
            if xmp_changes:
                # TODO: move tmp file into own class
                fd, tmp_xmp_name = tempfile.mkstemp(suffix=".xmp")
                # with open(self.tmp_xmp_name, "wb") as tmp_xmp_file:
                with os.fdopen(fd, "wb") as tmp_xmp_file:
                    modify_xmp(xmp_path, tmp_xmp_file, changes=xmp_changes)
                xmp_path = tmp_xmp_name

            return photo.filepath, xmp_path

        return photo, ""

    def _generate_command():
        command = [
            cli_bin,
            photo_filepath,
            xmp_path,
            out_path,
            "--width",
            str(width),
            "--height",
            str(height),
            "--hq",
            str(hq_resampling),
            "--upscale",
            str(upscale),
            "--style" if style else "",
            str(style),
            "--style-overwrite" if style_overwrite else "",
            "--apply-custom-presets",
            str(apply_custom_presets),
            "--out-ext",
            str(format_options.ext),
            "--icc-type",
            str(icc_type.name),
            "--icc-file" if os.path.exists(icc_file) else "",
            str(icc_file) if os.path.exists(icc_file) else "",
            "--icc-intent" if icc_intent.name != "IMAGE_SETTINGS" else "",
            str(icc_intent.name) if icc_intent.name != "IMAGE_SETTINGS" else "",
            "--verbose" if debug else "",
            # Everything after this are darktable core parameters
            "--core",
            "--configdir",
            str(config_dir),
        ]
        # Add format options to the command
        command += format_options.configuration_listed()
        # Remove empty strs from the command (NEEDED)
        return [x for x in command if x]

    out_path = str(PurePosixPath(out_dir, filename_format))

    photo_filepath, xmp_path = _generate_input_filelist()
    command = _generate_command()

    if debug:
        if isinstance(photo, darktable.Photo):
            print("xmp:", photo.xmp_path)
        print(" ".join([f"'{word}'" for word in command]))

    result = subprocess.run(command, capture_output=True, text=True)
    if debug:
        print(result.stdout.rstrip())
        print(result.stderr.rstrip())

    # extract the exported filename
    match = re.search(r"exported to `([^\']+)\'", result.stdout)
    if not match:
        raise RuntimeError("expected darktable-cli output to contain filename")

    export_filepath = match.groups()[0]

    # Rewrite EXIF? python_exif only has support for JPG & PNG
    if not exif_artist or not exif_copyright:
        modify_metadata(export_filepath, exif_artist, exif_copyright)

    # TODO
    # os.unlink(tmp_xmp_name)
    return Export(photo, filepath=export_filepath)


def modify_metadata(filepath, exif_artist, exif_copyright):
    """Save personal details in exif"""
    with open(filepath, "rb") as image_file:
        original_exif_image = exif.Image(image_file)

    # remove exif data
    image = Image.open(filepath)
    data = list(image.getdata())
    image_noexif = Image.new(image.mode, image.size)
    image_noexif.putdata(data)
    image_noexif.save(filepath)
    image_noexif.close()

    # save personal details in exif
    with open(filepath, "rb") as image_file:
        exif_image = exif.Image(image_file)
    if exif_artist is not None:
        exif_image.set("artist", exif_artist)
    if exif_copyright is not None:
        exif_image.set("copyright", exif_copyright)
    exif_image.set("datetime_original", original_exif_image.get("datetime_original"))
    with open(filepath, "wb") as image_file:
        image_file.write(exif_image.get_file())


def modify_xmp(
    in_filename, out_fd: TextIOWrapper, changes: list[Callable[[Element, dict], None]]
):
    # register all namespaces
    namespaces = dict(
        [node for _, node in ElementTree.iterparse(in_filename, events=["start-ns"])]
    )
    for name, uri in namespaces.items():
        ElementTree.register_namespace(name, uri)
    # parse xmp file
    tree = ElementTree.parse(in_filename)
    root = tree.getroot()
    # go through all "changers" which modify the xmp
    for func in changes:
        func(root, namespaces)
    # write output
    xmp_data = ElementTree.tostring(root, encoding="unicode")
    out_fd.seek(0)
    out_fd.truncate()
    out_fd.write(xmp_data.encode())
    out_fd.flush()


def xmp_remove_borders(xmp_root, namespaces):
    for parent in xmp_root.findall(".//darktable:history//rdf:Seq", namespaces):
        for element in parent.findall(
            'rdf:li[@darktable:operation="borders"]', namespaces
        ):
            key = f'{{{namespaces["darktable"]}}}enabled'
            if key in element.attrib:
                element.attrib[key] = "0"


def sanitize_xmp(in_filename, out_fd: TextIOWrapper):
    modify_xmp(in_filename, out_fd, changes=[xmp_remove_borders])


def is_raw_photo_ext(ext: str) -> bool:
    # all raw image file extensions
    # (excluding darktable export extensions, namely tif)
    # https://en.wikipedia.org/wiki/Raw_image_format
    # https://docs.darktable.org/usermanual/4.0/en/special-topics/program-invocation/darktable-cli/
    return ext.strip().lstrip(".").lower() in set(
        [
            "3fr",
            "ari",
            "arw",
            "bay",
            "braw",
            "crw",
            "cr2",
            "cr3",
            "cap",
            "data",
            "dcs",
            "dcr",
            "dng",
            "drf",
            "eip",
            "erf",
            "fff",
            "gpr",
            "iiq",
            "k25",
            "kdc",
            "mdc",
            "mef",
            "mos",
            "mrw",
            "nef",
            "nrw",
            "obm",
            "orf",
            "pef",
            "ptx",
            "pxn",
            "r3d",
            "raf",
            "raw",
            "rwl",
            "rw2",
            "rwz",
            "sr2",
            "srf",
            "srw",
            "tif",
            "x3f",
        ]
    ) - set(["tif"])
