# pixelblaze-client
A Python library that presents a simple, synchronous interface for communicating with and
controlling one or more Pixelblaze LED controllers. 

## Requirements
- Python 3.9 or newer
- websocket-client (installable via `pip install websocket-client`, or from https://github.com/websocket-client/websocket-client)
- requests (installable via `pip install requests`, or from https://github.com/psf/requests)
- pytz (installable via `pip install pytz`, or from https://github.com/stub42/pytz)
- py-mini-racer (installable via `pip install py-mini-racer`, or from https://github.com/sqreen/PyMiniRacer)

## Installation
Install pixelblaze-client with all required packages using pip:

```pip install pixelblaze-client```

Or, if you prefer, drop a copy of [pixelblaze.py](pixelblaze/pixelblaze.py) into your project directory and reference it within your project:

```from pixelblaze import *```

## <a name="documentation"></a>Documentation

API and other documention is available in [Markdown](docs/index.md) and [HTML](https://zranger1.github.io/pixelblaze-client/).

Sample code illustrating usage is provided in the [examples directory](examples/).

**Please note that version 1.0.0 was a major refactoring and enhancement of the library, with many new features and significant changes.** The API surface is completely new. See the the [API documentation](#documentation) for details.  

## Current Version [**v1.1.5**] - 2025-2-23

#### Fixed
* Added socket timeout to lightweight enumerator
* Various small fixes, improvements and code cleanup

### Older Versions

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## Known Issues
- Check our github repo; if you find something, [let us know](/../../issues/new/choose)!
