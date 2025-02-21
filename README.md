# Darktable Python Library
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

The aim of this project is the following:

- Provide a Python library
  that allows programmatic access to your Darktable library
- Provide a way to programmatically export photos from your Darktable library
- Form the foundation for creating a web API
  to access and export Darktable images
- ...

## Setup

```sh
git clone https://github.com/ungive/darktable-python && cd darktable-python
python -m pip install .
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
