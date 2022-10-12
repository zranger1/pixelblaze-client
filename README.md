# pixelblaze-client
A Python library that presents a simple, synchronous interface for communicating with and
controlling one or more Pixelblaze LED controllers. 

## Requirements
- Python 3.9-3.10
- websocket-client (installable via pip, or from https://github.com/websocket-client/websocket-client)
- requests (installable via pip, or from https://github.com/psf/requests)

## Installation
Install with pip:

```pip install pixelblaze-client```

Or, if you prefer, drop a copy of [pixelblaze.py](https://github.com/zranger1/pixelblaze-client/blob/main/pixelblaze-client/pixelblaze.py) into your project directory and reference it within your project:

```from pixelblaze import *```

## Documentation

API and other documention is available [here](https://github.com/zranger1/pixelblaze-client/blob/main/docs/index.md).

Sample code illustrating usage is provided in the [examples directory](https://github.com/zranger1/pixelblaze-client/blob/main/pixelblaze-client/examples).

## Version history

### Current Version [**v1.0.0**] - 2022-10-01

This is a major refactoring and enhancement of the **pixelblaze-client** library with many significant changes. 

The API surface is completely new, so users of previous versions are urged to review the [API documentation](https://github.com/zranger1/pixelblaze-client/blob/main/docs/index.md).

#### Added

* new PBB class for reading, writing and manipulating Pixelblaze Binary Backups for backup/restore of Pixelblaze configurations and patterns.

* new PBP class for reading, writing and manipulating Pixelblaze Binary Patterns as stored within Pixelblaze Binary Backups.

* new EPE class for reading, writing and manipulating Encapsulated Pattern Expressions as imported/exported from the Pixelblaze pattern editor.

* new methods to provide access to all of the features exposed by the Pixelblaze webUI. See the [API documentation](https://github.com/zranger1/pixelblaze-client/blob/main/docs/index.md) for more details.

* new example programs to demonstrate the new API.

#### Changed

* Many existing methods renamed to give common names to related functions.  See the [API documentation](https://github.com/zranger1/pixelblaze-client/blob/main/docs/index.md) for more details.

#### Deprecated

* Some existing methods deprecated.  See the [API documentation](https://github.com/zranger1/pixelblaze-client/blob/main/docs/index.md) for more details.

#### Removed

* Some existing methods removed.  

* Internal methods (names beginning with "_") were removed where no longer required.

### Previous Versions

See [changelog.md](https://github.com/zranger1/pixelblaze-client/blob/main/changelog.md) for details on previous versions.

## Known Issues
- None at the moment; if you find something, [let us know](https://github.com/zranger1/pixelblaze-client/issues/new/choose)!
