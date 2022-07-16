# pixelblaze-client Change Log

## v0.9.3
Minor update - fixed endian-ness related bug in the enumerator, and changed Pixelblaze.waitforEmptyQueue() to actually do what
it says in the documentation.  (It was throwing an exception on timeouts, rather than returning False
as described.  Thanks to [Nick_W](https://github.com/NickWaterton) for finding the bug and suggesting a fix!)

## Current Version: v0.9.2
Support for Pixelblaze's updated internal pattern sequencer.

Added support for starting the sequencer in either playlist or shuffle mode,
and pausing and unpausing.   See API docs for startSequencer(), pauseSequencer() and
playSequencer below.

#### v0.9.1
Support for pypi.

You can now install pixelblaze-client with pip.  Once installed, simply 
"import pixelblaze" in your python programs!

#### v0.9.0
**PixelblazeEnumerator class** has been added.  It listens continuously for Pixelblaze beacon
packets, maintains a list of visible Pixelblazes and supports synchronizing time
on multiple Pixelblazes to allow them to run patterns simultaneously. 

#### v0.0.3
- Added the ability to handle patterns with multiple color controls. 
- added getColorControlNames() - returns a complete list of all rgb and hsv color controls associated
with a pattern
- getColorControlName() - now explicitly returns the name of the pattern's first color control. (It always
did this, but now it's officially defined that way.)

#### v0.0.2
- controlExists(ctl_name, pattern) - returns True if specified control exists in the specified pattern, False otherwise
- getColorControlName() - returns name of rgb or hsv color picker if the pattern has one, None otherwise
- setColorControl(name,color) - allows you to set a color picker control to a 3 element array of color values
- variableExists(var_name) - returns True if specified variable is exported by the current pattern
- If you omit the pattern name argument from getControls() or controlExists(), control data is retrieved
for the current pattern if available.

#### v0.0.1
Initial release