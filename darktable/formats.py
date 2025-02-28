from enum import Enum


class OutputColorProfile(Enum):
    """https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/output-color-profile/

    The CLI err output for this option lists a lot more profiles than the docu
    """

    NONE = 0
    FILE = 1
    SRGB = 2
    ADOBERGB = 3
    LIN_REC709 = 4
    LIN_REC2020 = 5
    XYZ = 6
    LAB = 7
    INFRARED = 8
    DISPLAY = 9
    EMBEDDED_ICC = 10
    EMBEDDED_MATRIX = 11
    STANDARD_MATRIX = 12
    ENHANCED_MATRIX = 13
    VENDOR_MATRIX = 14
    ALTERNATE_MATRIX = 15
    BRG = 16
    EXPORT = 17
    SOFTPROOF = 18
    WORK = 19
    DISPLAY2 = 20
    REC709 = 21
    PROPHOTO_RGB = 22
    PQ_REC2020 = 23
    HLG_REC2020 = 24
    PQ_P3 = 25
    HLG_P3 = 26
    DISPLAY_P3 = 27


class RenderingIntent(Enum):
    """https://docs.darktable.org/usermanual/development/en/special-topics/color-management/rendering-intent/

    This only takes place if rendering with LittleCMS2, which has to be defined via the
    darktable configuration options
    """

    IMAGE_SETTINGS = 0
    PERCEPTUAL = 1
    RELATIVE_COLORIMETRIC = 2
    SATURATION = 3
    ABSOLUTE_COLORIMETRIC = 4


class _ImgFormat:
    def __init__(self):
        self.options = {}

    def configuration_listed(self):
        """Generate the proper list with the configuration options properly formatted"""
        conf = []
        for option, value in self.options.items():
            conf.append("--conf")
            conf.append(f"plugins/imageio/format/{self.ext}/{option}={value}")

        return conf

    class FormatError(Exception):
        pass


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#jpeg
class JPEG(_ImgFormat):
    """jpeg

    quality: int 5-100
    """

    def __init__(self, quality: int = 92):
        super().__init__()
        self.ext = "jpg"

        if 5 <= quality <= 100:
            self.options["quality"] = quality
        else:
            raise self.FormatError


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#j2k-jpg2000
class J2K(_ImgFormat):
    """jpg2000

    format_: bool
        0: J2K
        1: jp2
    quality: int 5-100
    preset: int 0-2
        0: Cinema2K, 24 FPS
        1: Cinema2K, 48 FPS
        2: Cinema4K, 24 FPS
    """

    def __init__(
        self,
        format_: bool = False,
        quality: int = 92,
        preset: int = 0,
    ):
        super().__init__()
        self.ext = "j2k"

        self.options["format"] = format_

        if 5 <= quality <= 100:
            self.options["quality"] = quality
        else:
            raise self.FormatError("Quality outside range 5-100")

        if 0 <= tier <= 2:
            self.options["preset"] = preset
        else:

            raise self.FormatError("Preset outside range 0-2")


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#exr-openexr
class EXR(_ImgFormat):
    """OpenEXR

    bpp: int 16 or 32
    compression: int 0-8
        0: uncoompressed
        1: RLE
        2: ZIPS
        3:ZIP
        4: PIZ
        5: PXR24
        6: B44
        7: DWAA
        8: DWAB
    """

    def __init__(
        self,
        bpp: int = 16,
        compression: int = 0,
    ):
        super().__init__()
        self.ext = "exr"

        if bpp in (16, 32):
            self.options["bpp"] = bpp
        else:
            raise self.FormatError("Bitdepth bpp outside posible values {16, 32}")

        if 0 <= tier <= 8:
            self.options["compression"] = compression
        else:
            raise self.FormatError("Compression outside range 0-8")


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#pdf
class PDF(_ImgFormat):
    """pdf

    title: str
    size: int 0-3
        0: a4
        1: a3
        2: letter
        3: legal
    orientation: bool
        0: portrait
        1: landscape
    border: str
        (a number) + unit; examples: 10 mm, 1 inch
    dpi: int 1-5000
    rotate: bool
    icc: bool
    bpp: int 8 or 16
    compression: bool
    mode: int 0-2
        0: normal: just put the images into the pdf
        1: draft: images are replaced with boxes
        2: debug: only show the outlines and bounding boxen
    """

    size_opts = {"a4", "a3", "letter", "legal"}

    def __init__(
        self,
        title: str,
        size: int = 0,
        orientation: bool = False,
        border: str = "0 mm",
        dpi: int = 300,
        rotate: bool = False,
        icc: bool = False,
        bpp: int = 8,
        compression: bool = True,
        mode: int = 0,
    ):
        super().__init__()
        self.ext = "pdf"

        self.options["title"] = title
        if 0 <= size <= 3:
            self.options["size"] = size_opts[size]
        else:
            raise self.FormatError("Size outside range 0-3")

        self.options["border"] = border

        if 1 <= dpi <= 5000:
            self.options["dpi"] = dpi
        else:
            raise self.FormatError("DPi outside range 1-5000")

        self.options["rotate"] = rotate
        self.options["icc"] = icc

        if bpp in (8, 16):
            self.options["bpp"] = bpp
        else:
            raise self.FormatError("Bitdepth bpp outside posible values {8, 16}")
        self.options["compression"] = compression

        if 0 <= mode <= 2:
            self.options["mode"] = mode
        else:
            raise self.FormatError("Mode outside range 0-2")


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#pfm
class PFM(_ImgFormat):
    """pfm

    No options
    """

    def __init__(self):
        super().__init__()
        self.ext = "pfm"


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#png
class PNG(_ImgFormat):
    """png

    bpp: int 8 or 16
    compression: int 0-9
    """

    def __init__(
        self,
        bpp: int = 8,
        compression: int = 92,
    ):
        super().__init__()
        self.ext = "png"

        if bpp in (8, 16):
            self.options["bpp"] = bpp
        else:
            raise self.FormatError("Bitdepth bpp outside posible values {8, 16}")

        if 0 <= compression <= 9:
            self.options["compression"] = compression
        else:
            raise self.FormatError("Compression outside range 0-9")


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#ppm
class PPM(_ImgFormat):
    """ppm (16 bit)

    No options
    """

    def __init__(self):
        super().__init__()
        self.ext = "ppm"


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#tiff
class TIFF(_ImgFormat):
    """tiff

    bpp: int 8, 16, or 32
    compress: int 0-2
        0: uncompressed
        1: deflate
        2: deflate with predictor
    compresslevel: int 0-9
    shortfile: bool
        0: rgb
        1: grayscale
    """

    def __init__(
        self,
        bpp: int = 8,
        compress: int = 2,
        compresslevel: int = 6,
        shortfile: bool = False,
    ):
        super().__init__()
        self.ext = "tif"

        if bpp in (8, 16, 32):
            self.options["bpp"] = bpp
        else:
            raise self.FormatError("Bitdepth bpp outside posible values {8, 16, 32}")

        if 0 <= compress <= 2:
            self.options["compress"] = compress
        else:
            raise self.FormatError("Compress outside range 0-2")

        if 0 <= compresslevel <= 9:
            self.options["compresslevel"] = compresslevel
        else:
            raise self.FormatError("Compresslevel outside range 0-9")

        self.options["shortfile"] = shortfile


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#webp
class WEBP(_ImgFormat):
    """webp

    comp_type: bool
        0: lossy
        1: lossless
    quality: int 5-100
    hint: int 0-3
        0: default
        1: picture
        2: photo
        3: graphic
    """

    def __init__(
        self,
        comp_type: bool = False,
        quality: int = 95,
        hint: int = 0,
    ):
        super().__init__()
        self.ext = "webp"

        self.options["comp_type"] = comp_type

        if 5 <= quality <= 100:
            self.options["quality"] = quality
        else:
            raise self.FormatError("Quality outside range 5-100")

        if 0 <= hint <= 3:
            self.options["hint"] = hint
        else:
            raise self.FormatError("hint outside range 0-3")


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#copy
class COPY(_ImgFormat):
    """Copy file

    No options
    """


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#xcf
class XCF(_ImgFormat):
    """xcf

    bpp: int 8, 16 or 32
    """

    def __init__(
        self,
        bpp: int = 8,
    ):
        super().__init__()
        self.ext = "xcf"

        if bpp in (8, 16, 32):
            self.options["bpp"] = bpp
        else:
            raise self.FormatError("Bitdepth bpp outside posible values {8, 16, 32}")


# https://docs.darktable.org/usermanual/development/en/special-topics/program-invocation/darktable-cli/#jxl
class JXL(_ImgFormat):
    """jxl

    bpp: int 8, 10, 12, 16 or 32
    pixel_type
        0: unsigned integer
        1: floating point
    quality: int 4-100
    original: bool
    effort: int 1-9
    tier: int 0-4
    """

    def __init__(
        self,
        bpp: int = 8,
        pixel_type: bool = False,
        quality: int = 92,
        original: bool = False,
        effort: int = 7,
        tier: int = 0,
    ):
        super().__init__()
        self.ext = "jxl"

        if bpp in (8, 10, 12, 16, 32):
            self.options["bpp"] = bpp
        else:
            raise self.FormatError(
                "Bitdepth bpp outside posible values {8, 10, 12, 16, 32}"
            )

        self.options["pixel_type"] = pixel_type

        if 4 <= quality <= 100:
            self.options["quality"] = quality
        else:
            raise self.FormatError("Quality outside range 5-100")

        self.options["original"] = original

        if 1 <= effort <= 9:
            self.options["effort"] = effort
        else:
            raise self.FormatError("Effort outside range 1-9")

        if 0 <= tier <= 4:
            self.options["tier"] = tier
        else:
            raise self.FormatError("Tier outside range 0-4")
