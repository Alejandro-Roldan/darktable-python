import datetime
import re
import sqlite3
import string
import tempfile
from collections import defaultdict
from enum import Enum
from os import close, path, unlink
from typing import Any, Callable

import dateutil.parser
import exif
import xmltodict
from PIL import Image

from darktable.util import readonly_sqlite_connection

Position = int


class TagDoesntExistError(Exception):
    pass


class HasId:
    id: int

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        return self.id == other.id


class FilmRoll(HasId):
    def __init__(self, id, directory):
        self.id = id
        self.directory = directory

    def __repr__(self):
        return f"{self.__class__.__name__}({self.id}, {self.directory})"


class Tag(HasId):
    def __init__(self, id, name):
        self.id = id
        self.name = name

    def __repr__(self):
        return f"{self.__class__.__name__}({self.id}, {self.name})"


class ColorLabel(Enum):
    """
    https://github.com/darktable-org/darktable/blob/7b86507f/src/common/colorlabels.h#L29
    """

    RED = 0
    YELLOW = 1
    GREEN = 2
    BLUE = 3
    PURPLE = 4


class Photo(HasId):
    # TODO: add missing fields
    def __init__(
        self,
        id,
        filepath,
        version,
        datetime_taken: datetime.datetime,
        flags: int,
        film_roll: FilmRoll,
        position: Position,
        tags: dict[Tag, Position],
        color_labels: set[ColorLabel],
        output_width: int,
        output_height: int,
        aspect_ratio: float,
    ):
        self.id: int = id
        self.filepath: str = path.normpath(filepath)
        self.version: int = version
        self.datetime_taken: datetime.datetime = datetime_taken
        flags: int = flags
        self.film_roll: FilmRoll = film_roll
        self.position: Position = position
        self.tags: dict[Tag, Position] = tags
        self.color_labels: set[ColorLabel] = color_labels
        self.output_width: int = output_width
        self.output_height: int = output_height
        self.aspect_ratio: float = aspect_ratio

        # extracting ratings from image flags with mask 0x7:
        # https://github.com/darktable-org/darktable/blob/0f5bd178/src/common/ratings.c#L52
        # https://github.com/darktable-org/darktable/blob/0f5bd178/src/common/ratings.h#L26
        self.rating: int = flags & 0x7
        # And all the rest of flag values are defined in
        # https://github.com/darktable-org/darktable/blob/master/src/common/image.h#L53
        self.rejected: bool = bool(flags & 0x8)
        self.monochrome: bool = bool(flags & (1 << 15 | 1 << 19 | 1 << 20))
        self.color: bool = not self.monochrome

        self._xmp_path = None
        self._tmp_xmp_name = None
        self._xmp_parsed = None
        self._history = None

    @property
    def xmp_path(self):
        if self._xmp_path is None:
            filename = path.basename(self.filepath)
            filename, ext = path.splitext(filename)
            if self.version > 0:
                filename += "_" + f"{self.version:02}"
            xmp_path = filename + ext + "." + "xmp"

            self._xmp_path = path.join(path.dirname(self.filepath), xmp_path)

        return self._xmp_path

    @property
    def tmp_xmp_name(self):
        if self._tmp_xmp_name is None:
            fd, self._tmp_xmp_name = tempfile.mkstemp(suffix=".xmp")
            close(fd)

        return self._tmp_xmp_name

    @property
    def xmp_parsed(self):
        if self._xmp_parsed is None:
            try:
                with open(self.xmp_path, "rb") as xmp:
                    self._xmp_parsed = xmltodict.parse(xmp)
            except FileNotFoundError:
                self._xmp_parsed = {}

        return self._xmp_parsed

    def xmp_unparsed(self, modified_xmp):
        """Overwrite tmp xmp with new xmp"""
        with open(self.tmp_xmp_name, "wb") as file:
            file.seek(0)
            file.truncate()
            file.write(xmltodict.unparse(modified_xmp, pretty=True).encode())
            file.flush()

    @property
    def history(self):
        if self._history is None:
            try:
                self._history = self.xmp_parsed["x:xmpmeta"]["rdf:RDF"][
                    "rdf:Description"
                ]["darktable:history"]["rdf:Seq"]["rdf:li"]
            # KeyError: no xmp for this file
            # TypeError: no history in xmp file
            except (KeyError, TypeError):
                self._history = {}

        return self._history

    def module_instance_enabled(self, operation: str, multi_name: str = "") -> bool:
        """
        Check whether a module "operation" with name "multi_name" is enabled in xmp
        history

        multi_name is optional. Defaults to empty str

        Returns None if the operation/multi_name combination doesnt exist
        Bool otherwise
        """
        for hist_step in reversed(self.history):
            if (
                hist_step["@darktable:operation"] == operation
                and hist_step["@darktable:multi_name"] == multi_name
            ):
                return True if hist_step["@darktable:enabled"] == "1" else False

    def module_enabled(self, operation: str) -> set:
        """
        Check if instances of module "operation" exist and are enabled

        Return a set containing their multi_names
        """
        return_ = set()
        for hist_step in self.history:
            # For each matching operation
            if hist_step["@darktable:operation"] == operation:
                # Add multi_name to set if enabled
                if hist_step["@darktable:enabled"] == "1":
                    return_.add(hist_step["@darktable:multi_name"])
                # And remove if disabled
                else:
                    return_.discard(hist_step["@darktable:multi_name"])

        return return_

    def has_tag(self, str_, ignore_case=True, ignore_dt_tags=False):
        """Check if a photo has a tag

        Arguments:
            ignore_case: case insensitive matching. Default: True
            ignore_dt_tags: ignore daktable default tags. Default: False

        Returns:
            Bool value
        """
        # Replace "|" in str_ with "\|" so regex correctly interprets as literal "|"
        str_ = str_.replace("|", "\\|")
        flags = re.IGNORECASE if ignore_case else re.NOFLAG

        # Loop through tags to regex match the str_ tag
        for tag in self.tags:
            # if ignore_dt_tags and re.match("darktable", tag.name) is not None:
            if ignore_dt_tags and tag.name.startswith("darktable|"):
                continue
            if re.search(rf"(?:^|\|)({str_})(?:$|\|)", tag.name, flags=flags):
                return True

        return False

    def __repr__(self):
        return (
            self.__class__.__name__
            + "("
            + ", ".join(
                [
                    repr(self.id),
                    repr(self.filepath),
                    repr(self.version),
                    repr(self.datetime_taken),
                    repr(self.tags),
                    repr(self.film_roll),
                    repr(self.position),
                ]
            )
            + ")"
        )

    def __del__(self):
        try:
            if self._tmp_xmp_name is not None:
                unlink(self._tmp_xmp_name)
        except FileNotFoundError:
            pass


# TODO: seems unfinished and i dont understand the idea
class FilenameFormat:
    """Implements a Darktable format string for export filenames.
    Only supports a subset of variables as not all are used here.
    """

    class Placeholder:
        def __init__(self, values: list[str]):
            self.values = values

        def __getattr__(self, __name: str) -> Any:
            return FilenameFormat.Placeholder(self.values + [__name])

        def __repr__(self):
            return ".".join(self.values).join("{}")

        def __str__(self):
            return repr(self)

    class Default(dict):
        def __missing__(self, key):
            if not key.isupper():
                raise KeyError(str(key))
            return FilenameFormat.Placeholder([key])

    def __init__(self, format_string):
        """The format_string must be a python format string,
        where the variables from Darktable
        are transformed to python format string placeholders, e.g.:
        "$(FILE.NAME)" becomes "{FILE.NAME}".
        Not that all letters must remain uppercase.
        You can also add your own placeholders
        which will be replaced with values that are passed to render().
        """
        self.format_string = format_string

    def render(self, **kwargs):
        format_dict = FilenameFormat.Default(kwargs)
        result = string.Formatter().vformat(self.format_string, (), format_dict)
        # result = self.format_string.format_map(format_dict)
        result = re.sub(r"\{([A-Z\.]+)\}", r"$(\1)", result)
        return result


def parse_darktable_datetime(datetime_taken: int):
    # the timestamp is in microseconds
    # additionally, it uses an origin different than epoch time
    # https://github.com/darktable-org/darktable/blob/0f5bd178/src/common/datetime.c#L22C29-L22C52
    origin = dateutil.parser.isoparse("0001-01-01 00:00:00.000Z")
    epoch = dateutil.parser.isoparse("1970-01-01 00:00:00.000Z")
    epoch_delta = epoch - origin
    value = datetime_taken / 1000 / 1000
    value = max(value, epoch_delta.total_seconds())
    value_corrected = value - epoch_delta.total_seconds()

    return datetime.datetime.fromtimestamp(value_corrected, datetime.timezone.utc)


class AttachedDatabase:
    def __init__(self, cursor: sqlite3.Cursor, name, db_path):
        self.cursor = cursor
        self.name = name
        self.db_path = db_path
        self.cursor.execute(
            """--sql
            ATTACH DATABASE ? AS ?;
            """,
            (self.db_path, self.name),
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.execute(
            """--sql
            DETACH ?;
            """,
            (self.name,),
        )


class DarktableLibrary:
    DATA_DB = "data.db"
    LIBRARY_DB = "library.db"

    def __init__(self, config_dir, library_dbpath=None, data_dbpath=None):
        self.config_dir = config_dir
        if library_dbpath:
            if not path.exists(library_dbpath):
                raise IOError("library path doesn't exist")
            self.library_dbpath = library_dbpath
        else:
            self.library_dbpath = path.join(config_dir, self.LIBRARY_DB)
        if data_dbpath:
            if not path.exists(data_dbpath):
                raise IOError("data path doesn't exist")
            self.data_dbpath = data_dbpath
        else:
            self.data_dbpath = path.join(config_dir, self.DATA_DB)
        self.data_conn = readonly_sqlite_connection(self.data_dbpath)
        self.library_conn = readonly_sqlite_connection(self.library_dbpath)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        self.data_conn.close()
        self.library_conn.close()

    def _row_to_photo(self, row: sqlite3.Row, separator: str) -> Photo:
        # TODO: add missing fields
        return Photo(
            id=int(row["id"]),
            filepath=row["filepath"],
            version=int(row["version"]),
            datetime_taken=parse_darktable_datetime(
                row["datetime_taken"] if isinstance(row["datetime_taken"], int) else 0
            ),
            flags=row["flags"],
            film_roll=FilmRoll(int(row["film_id"]), row["film_directory"]),
            position=int(row["film_position"]),
            tags={
                Tag(int(tag_id), tag_name): int(tag_position)
                for tag_id, tag_name, tag_position in zip(
                    row["tag_ids"].split(separator),
                    row["tag_names"].split(separator),
                    row["tag_positions"].split(separator),
                )
            },
            color_labels=(
                set(
                    ColorLabel(int(color_label))
                    for color_label in row["color_label"].split(separator)
                )
                if row["color_label"] is not None
                else set()
            ),
            output_width=row["output_width"],
            output_height=row["output_height"],
            aspect_ratio=row["aspect_ratio"],
        )

    def _select_photos(
        self, where_clause: str = "", args: tuple = (), limit: int = None
    ) -> list[Photo]:
        cur = self.library_conn.cursor()
        separator = "#~~~#"
        with AttachedDatabase(cur, "data", self.data_dbpath):
            cur.execute(
                f"""--sql
                SELECT
                    images.*,
                    rtrim(film_rolls.folder, '/') || '/' || images.filename AS filepath,
                    film_rolls.id AS film_id,
                    film_rolls.folder AS film_directory,
                    images.position AS film_position,
                    GROUP_CONCAT(_tagged_images_2.tagid, ?) AS tag_ids,
                    GROUP_CONCAT(data.tags.name, ?) AS tag_names,
                    GROUP_CONCAT(_tagged_images_2.position, ?) AS tag_positions,
                    GROUP_CONCAT(color_labels.color, ?) as color_label
                FROM tagged_images
                INNER JOIN images ON tagged_images.imgid = images.id
                INNER JOIN film_rolls ON film_rolls.id = images.film_id
                INNER JOIN tagged_images _tagged_images_2 ON images.id = _tagged_images_2.imgid
                INNER JOIN data.tags ON _tagged_images_2.tagid = data.tags.id
                LEFT JOIN color_labels ON images.id = color_labels.imgid
                {where_clause}
                GROUP BY images.id
                {f'LIMIT {limit}' if limit is not None and limit >= 0 else ''}
                """,
                (separator, separator, separator, separator) + args,
            )
            result = cur.fetchall()

        return [self._row_to_photo(row, separator=separator) for row in result]

    def get_photos(self) -> list[Photo]:
        return self._select_photos()

    def get_photo_by_id_and_tag(self, id: int, tag: Tag) -> Photo:
        photos = self._select_photos(
            """--sql
            WHERE images.id = ? AND tagged_images.tagid=?
            """,
            (id, tag.id),
            limit=1,
        )

        return photos[0] if len(photos) > 0 else None

    def get_tag(self, tag_name) -> Tag:
        cur = self.data_conn.cursor()
        cur.execute(
            """--sql
            SELECT id, name
            FROM tags
            WHERE name=?
            LIMIT 1
            """,
            (tag_name,),
        )
        try:
            id, name = cur.fetchone()
        # No matching tag
        except TypeError:
            raise TagDoesntExistError

        return Tag(int(id), name)

    def get_tagged_photos(self, tag: Tag, include_dt_tags: bool = False) -> list[Photo]:
        # Whether to include search in darktable default tags
        include_dt_tags = (
            "AND LOWER(data.tags.name) NOT LIKE 'darktable%'"
            if not include_dt_tags
            else ""
        )
        return self._select_photos(
            (f"""--sql
                WHERE tagged_images.tagid=? {include_dt_tags}
                """),
            (tag.id,),
        )

    def get_subtags(self, tag_name, including_tag=False) -> list[Tag]:
        """Returns all tag names and their tag ID
        that are underneath the given tag name in the hierarchy.
        E.g. tag_name="foo" yields "bar" for "foo|bar",
        but not "foo" if a tag is named "foo" only.
        """

        cur = self.data_conn.cursor()
        cur.execute(
            f"""--sql
            SELECT id, name
            FROM tags
            WHERE name LIKE ? || '|_%' {'OR name = ?' if including_tag else ''}
            """,
            (tag_name,) + ((tag_name,) if including_tag else ()),
        )
        return [Tag(int(id), name) for id, name in cur.fetchall()]

    def get_photos_under_tag(self, tag_name) -> dict[Tag, list[Photo]]:
        """Returns a dictionary of photos that are under the given tag
        in the hierarchy. The key is the subtag's name and the value
        is a tuple of the full path to the photo and its version number.
        e.g. tag_name="foo" yields "bar"->("/img.raw", 0)
        if that photo is tagged "foo|bar" in Darktable.
        """

        result = defaultdict(list)
        for tag in self.get_subtags(tag_name):
            for photo in self.get_tagged_photos(tag):
                result[tag].append(photo)
        return result

    def get_photos_color_labeled(self, color: ColorLabel) -> list[Photo]:
        """Get photos marked with "color" color label"""

        return self._select_photos(
            """--sql
            WHERE color_labels.color == ?
            """,
            (str(color.value),),
        )


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


def modify_xmp(in_parsed_xmp, changes: list[Callable[[dict], None]]):
    in_parsed_xmp = in_parsed_xmp.copy()
    for func in changes:
        func(in_parsed_xmp)

    return in_parsed_xmp


def xmp_disable_operation(in_parsed_xmp, operation: str, multi_name: str = None):
    """
    Disable an operation in the xmp if present.

    Optionally provide a multi_name to only affect that instance
    """

    for step in in_parsed_xmp["x:xmpmeta"]["rdf:RDF"]["rdf:Description"][
        "darktable:history"
    ]["rdf:Seq"]["rdf:li"]:
        # When "multi_name" is None we only care to match "operation"
        if step["@darktable:operation"] == operation and (
            step["@darktable:multi_name"] == multi_name or multi_name is None
        ):
            step["@darktable:enabled"] = "0"


def xmp_remove_borders(in_parsed_xmp):
    xmp_disable_operation(in_parsed_xmp, "borders", None)


def sanitize_xmp(in_parsed_xmp):
    return modify_xmp(in_parsed_xmp, changes=[xmp_remove_borders])


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
