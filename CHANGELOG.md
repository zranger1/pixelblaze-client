# **Change Log** 📜📝

All notable changes to the "**pixelblaze-client**" library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes are categorized into the following types:
- **Added** -- for new features.
- **Changed** -- for changes in existing functionality.
- **Deprecated** -- for soon-to-be removed features.
- **Removed** -- for now removed features.
- **Fixed** -- for any bug fixes.
- **Security** -- in case of vulnerabilities.

---
## [**v1.1.4**] - 2024-8-27

#### Fixed
* Update firmware version check for remote pattern compilation
* Added ignoreOpenFailure to Pixelblaze() constructor to allow object creation without immediate connection to Pixelblaze.
* Preview frame image no longer contains unwanted header data

## [**v1.1.3**] - 2024-3-10

* New utility functions added for ledmaps
* Allow object creation if Pixelblaze can't be opened immediately.

### Added

* New method setMapCoordinates()

### Changed

* Refactored createMapData out of setMapFunction
* Call setMapData from setMapFunction and setMapCoordinates
* New argument for Pixelblaze() constructor: "ignoreOpenFailure" (default False). If True, the Pixelblaze object will 
be successfully created even if the Pixelblaze can't be opened immediately. Subsequent attempts to use the Pixelblaze
will automatically retry opening the connection.* 

## [**v1.1.1**] - 2023-2-15

Bug fix - automatic reconnect now works properly on Windows

## [**v1.1.0**] - 2022-12-25

New utility functions.

### Added

* new methods setMapFunction() and compilePattern() for compiling pixelmaps and patterns.



## [**v1.0.2**] - 2022-11-06

Minor fixes and new utility functions.

### Added

* new methods getMapCoordinates() and getMapOffsets() for retrieving spatial location of pixels.

### Fixed

* Fixed websocket parser state machine to better handle unsolicited packets.


## [**v1.0.1**] - 2022-11-04

Minor bug fixes and various adjustments to the compatibility & helper functions.

### Added

* **simple.py** example (in the /examples folder) shows basic Pixelblaze control features: how to set a pattern, change color and change brightness.

### Fixed

* **getActiveVariables** now (correctly) returns a dictionary of variables and values instead of a nested dictionary under the single key "vars"

* **setActivePatternByName** works again


## [**v1.0.0**] - 2022-10-01

This is a major refactoring and enhancement of the **pixelblaze-client** library with many significant changes. The API surface is completely new, but compatibility stubs have been provided for most existing methods to assist in transitioning to the new API.

### Added

* new PBB class for reading, writing and manipulating Pixelblaze Binary Backups for backup/restore of Pixelblaze configurations and patterns.
* new PBP class for reading, writing and manipulating Pixelblaze Binary Patterns as stored within Pixelblaze Binary Backups.
* new EPE class for reading, writing and manipulating Encapsulated Pattern Expressions as imported/exported from the Pixelblaze pattern editor.
* new methods to provide access to all of the features exposed by the Pixelblaze webUI. See the API documentation for more details.
* new example programs to demonstrate the new API.

### Changed

* Many existing methods renamed to give common names to related functions.  See the API documentation for more details.

### Deprecated

* Some existing methods deprecated.  Compatibility stubs have been provided to maintain functionality; warning messages are emitted to encourage movement to the new API.

### Removed

* Some internal methods (names beginning with "_") were removed where no longer required.


## [**v0.9.6**] - 2022-07-19

### Fixed

- Adjusted internal timeout in GetPatternList() to allow more time for slower 
responding Pixelblazes.  

## [**v0.9.5**] - 2022-07-16

### Changed

- Changed ws_recv() to take an optional packetType parameter so that it can receive
arbitrary binary packets.  This will allow callers to read data from things like
the Pixelblaze's new 1000 pixel preview frames. Fun!  Thanks, @pixie!

## [**v0.9.4**] - 2022-02-07

### Added
- Documented getPixelCount/setPixelCount(), which lets you get and set the number of LEDs attached to your Pixelblaze.
- added the pause() and unpause() commands. 

### Changed

- Behavior changes around writes to flash, pattern caching, a few new commands...
- getPatternList() is now cached, for greatly improved performance. The cache timeout can be set by calling setCacheRefreshTime(seconds). The default is 600 seconds, or 10 minutes.
- Reduced unneccessary flash writes - setActivePattern(), setActivePatternId() and setBrightness() now take an optional saveFlash parameter, which is False by default, and uses the enable_flash_save() safety mechanism (described in the API documentation) to prevent inadvertent flash saves.

## [**v0.9.3**] - 2021-06-19

### Fixed
- fixed endian-ness related bug in the enumerator, and changed Pixelblaze.waitforEmptyQueue() to actually do what
it says in the documentation.  (It was throwing an exception on timeouts, rather than returning False
as described.  Thanks to [Nick_W](https://github.com/NickWaterton) for finding the bug and suggesting a fix!)

## [**v0.9.2**] - 2021-01-16

### Added
- Added support for Pixelblaze's updated internal pattern sequencer, starting the sequencer in either playlist or shuffle mode, and pausing and unpausing. See API docs for startSequencer(), pauseSequencer() and playSequencer below.

## [**v0.9.1**] - 2020-12-17

### Added
- Added support for pypi.  You can now install pixelblaze-client with pip.  Once installed, simply `import pixelblaze` in your python programs!

## [**v0.9.0**] - 2020-12-07

### Added 
- New **PixelblazeEnumerator** class that listens continuously for Pixelblaze beacon
packets, maintains a list of visible Pixelblazes and supports synchronizing time
on multiple Pixelblazes to allow them to run patterns simultaneously. 

## [**v0.0.3**] - 2020-12-03

### Added
- Added the ability to handle patterns with multiple color controls. 
- added getColorControlNames() - returns a complete list of all rgb and hsv color controls associated with a pattern

### Changed
- getColorControlName() now explicitly returns the name of the pattern's first color control. (It always did this, but now it's officially defined that way.)

## [**v0.0.2**] - 2020-12-01

### Added
- controlExists(ctl_name, pattern) - returns True if specified control exists in the specified pattern, False otherwise
- getColorControlName() - returns name of rgb or hsv color picker if the pattern has one, None otherwise
- setColorControl(name,color) - allows you to set a color picker control to a 3 element array of color values
- variableExists(var_name) - returns True if specified variable is exported by the current pattern
- If you omit the pattern name argument from getControls() or controlExists(), control data is retrieved for the current pattern if available.

## [**v0.0.1**] - 2020-12-01
Initial release.
