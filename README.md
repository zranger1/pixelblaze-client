# pixelblaze-client
A Python library that presents a simple, synchronous interface for communicating with and
controlling one or more Pixelblaze LED controllers. Requires Python 3 and the websocket-client
module.

## Current Version: v0.9.6
Adjusted internal timeout in GetPatternList() to allow more time for slower 
responding Pixelblazes.  

## Current Version: v0.9.5
Changed ws_recv() to take an optional packetType parameter so that it can recieve
arbitrary binary packets.  This will allow callers to read data from things like
the Pixelblaze's new 1000 pixel preview frames. Fun!  Thanks, @pixie!

## Current Version: v0.9.4
Behavior changes around writes to flash, pattern caching, a few new commands...

- Documented getPixelCount/setPixelCount(), which lets you get and set the number of LEDs attached to your Pixelblaze.
- added the pause() and unpause() commands. 
- getPatternList() is now cached, for greatly improved performance. The cache timeout can be set by calling setCacheRefreshTime(seconds). The default is 600 seconds, or 10 minutes.
- Reduced unneccessary flash writes - setActivePattern(), setActivePatternId() and setBrightness() now take
 an optional saveFlash parameter, which is False by default, and uses the enable_flash_save() safety
 mechanism (described in the API documentation) to prevent inadvertent flash saves.


## Previously...
See [changelog.md](https://github.com/zranger1/pixelblaze-client/blob/main/changelog.md) for details on previous versions.

## Requirements
Python 3.4-3.10

websocket-client (installable via pip, or from https://github.com/websocket-client/websocket-client

## Known Issues
May be cranky if you have multiple programs/computers/browsers connected to your Pixelblaze. In the end, this
is due to an ESP32 limitation on simultaneous connections, but having the latest Pixelblaze firmware can help things.

I've gone to a some length to put an easy-to-program synchronous interface over what is essentially an
asynchronous communication system. At this point, it's good, but not perfect. It may behave oddly if you are 
controlling the same Pixelblaze from multiple computers or multiple programs.  Report bugs of this sort if
you see them -- it may not be fixable, but at least I can take a look.

## Installation
Install with pip, or if you prefer -- pixelblaze-client consists of a single file: [pixelblaze.py](https://github.com/zranger1/pixelblaze-client/blob/main/pixelblaze-client/pixelblaze.py) from this repository.  Drop it into your project
directory and import it into your project.  That's all.  Sample code illustrating usage
is provided in the [examples directory](https://github.com/zranger1/pixelblaze-client/blob/main/pixelblaze-client/examples) 

## Donation
If this project saves you time and effort, please consider donating to help support further development.  Every donut or cup of coffee helps!  :-)

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/donate/?hosted_button_id=YM9DKUT5V34G8)

# API Documentation
(roughly alphabetical except for object constructors)

## class PixelblazeEnumerator

#### PixelblazeEnumerator(addr)
Create an object that listens continuously for Pixelblaze time and beacon
packets, and maintains a list of visible Pixelblazes.  The PixelblazeEnumerator
object also supports synchronizing time on multiple Pixelblazes to allows
them to run patterns simultaneously.

Takes the IPv4 address of the interface to use for listening on the calling computer.
Listens on all available interfaces if addr is not specified.

#### disableTimesync()
Turns off the time synchronization -- the PixelblazeEnumerator will not
automatically synchronize Pixelblazes. 

#### enableTimesync()
Instructs the PixelblazeEnumerator object to automatically synchronize
time on all Pixelblazes. (Note that time synchronization
is off by default when a new PixelblazeEnumerator is created.)
 
#### getPixelblazeList()
Returns a list of Pixelblazes visible on the network.

#### setDeviceTimeout(ms)
Sets the interval in milliseconds which the enumerator will wait without
hearing from a Pixelblaze before removing it from the active devices list.        
The default timeout is 30000 (30 seconds).


## class Pixelblaze

#### Pixelblaze(addr)
Create and open Pixelblaze object. Takes the Pixelblaze's IPv4 address in the
usual 12 digit numeric form (for example, 192.168.1.xxx)  Returns a connected
Pixelblaze object.  To control multiple Pixelblazes, create multiple objects.

#### close()
Close websocket connection on Pixelblaze object.  The connection can be 
reopene by calling open() on the same or a different IP address.

#### controlExists(ctl_name,pattern = None)
Returns True if the specified control exists, False otherwise.
The pattern argument takes the name or ID of the pattern to check.
If pattern argument is not specified, checks the currently running pattern.
Note that getActivePattern() can return None on a freshly started
Pixelblaze until the pattern has been explicitly set.  This function
also will return False if the active pattern is not available.

#### getActivePattern()
Returns the ID and name of the pattern currently running on
the Pixelblaze if available.  Otherwise returns an empty dictionary
object

#### getColorControlName(pattern = None)
Returns the name of the specified pattern's rgbPicker or hsvPicker control
if it exists, None otherwise.  If the pattern argument is not specified,
checks in the currently running pattern.

#### getColorControlNames(pattern = None)
Returns a list of the names of the specified pattern's rgbPicker or
hsvPicker controls if any exist, None otherwise.  If the pattern
argument is not specified, check the currently running pattern

#### getControls(pid)
Returns a JSON object containing the state of all the specified
pattern's UI controls. If the pattern argument is not specified,
returns the controls for the currently active pattern if available.
Returns empty object if the pattern has no UI controls, None if
the pattern id is not valid or is not available.
(Note that getActivePattern() can return None on a freshly started
Pixelblaze until the pattern has been explicitly set.)

#### getHardwareConfig()
Returns a JSON object containing all the available hardware configuration data

#### getPatternList(refresh = False)
Returns a dictionary containing the unique ID and the text name of all
saved patterns on the Pixelblaze.   The optional 'refresh' parameter
allows you to override the pattern caching mechanism if you wish.  To
force a pattern list cache refresh, call getPatternList(True).

#### getVars()
Returns JSON object containing all vars exported from the active pattern

#### open(addr)
Open websocket connection to given ip address.  Called automatically
when a Pixelblaze object is created - it is not necessary to
explicitly call open to connect unless the websocket has been closed by the
user or by the Pixelblaze.

#### pause():
Pauses rendering. Lasts until unpause() is called or the Pixelblaze is reset.
        
#### pauseSequencer()
Temporarily pause the Pixelblaze's internal sequencer, without
losing your place in the shuffle or playlist. Call "playSequencer"
to restart.  Has no effect if the sequencer is not currently running. 
        
#### playSequencer()
Start the Pixelblaze's internal sequencer in the current mode,
at the current place in the shuffle or playlist.  Compliment to
"pauseSequencer".  Will not start the sequencer if it has not
been enabled via "startSequencer" or the Web UI.

#### setActivePattern(pid, saveFlash = False)
Sets the currently running pattern, using either an ID or a text name

The optional saveFlash parameter controls whether or not the
new brightness value is saved. By default, saveFlash is False, so
brightness values set with this method will not persist
through reboots.

To reduce wear on the Pixelblaze's flash memory, the saveFlash parameter is ignored
by default.  See documentation for _enable_flash_save() for
more information.   

#### setActivePatternId(pid, saveFlash = False):
Sets the active pattern by pattern ID, without the name lookup option
supported by setActivePattern(). This method is faster and more network efficient than SetActivePattern()
if you already know a pattern's ID. It does not validate the input id, or determine if the pattern is
 available on the Pixelblaze.
 
The optional saveFlash parameter controls whether or not the
new brightness value is saved. By default, saveFlash is False, so
brightness values set with this method will not persist
through reboots.

To reduce wear on the Pixelblaze's flash memory, the saveFlash parameter is ignored
by default.  See documentation for _enable_flash_save() for
more information.    

#### setBrightness(n, saveFlash = False)
Set the Pixelblaze's global brightness.  Valid range is 0-1

The optional saveFlash parameter controls whether or not the
new brightness value is saved. By default, saveFlash is False, so
brightness values set with this method will not persist
through reboots.

To reduce wear on the Pixelblaze's flash memory, the saveFlash parameter is ignored
by default.  See documentation for _enable_flash_save() for
more information.   

#### setCacheRefreshTime(seconds)
Set the interval, in seconds, at which the pattern cache is cleared and
a new pattern list is loaded from the Pixelblaze.  Default is 600 seconds (10 minutes).

#### setColorControl(ctl_name, color, saveFlash = False)
Sets the 3-element color of the specified HSV or RGB color picker.
The color argument should contain an RGB or HSV color with all values
in the range 0-1. To reduce wear on Pixelblaze's flash memory, the saveFlash parameter
is ignored by default.  See documentation for _enable_flash_save() for
more information.
        
Based on testing w/Pixelblaze, no run-time length or range validation is performed
on color. Pixelblaze ignores extra elements, sets unspecified elements to zero,
takes only the fractional part of elements outside the range 0-1, and
does something like (1-(n % 1)) for any negative elements.

#### setControl(ctl_name, value, saveFlash = False)
Sets the value of a single UI controls in the active pattern.
to values contained in the argument json_ctl. To reduce wear on Pixelblaze's flash memory, the saveFlash parameter is ignored
by default.  See documentation for _enable_flash_save() for
more information.

#### setControls(json_ctl, saveFlash = False)
Sets UI controls in the active pattern to values contained in
the JSON object in argument json_ctl. To reduce wear on
Pixelblaze's flash memory, the saveFlash parameter is ignored
by default.  See documentation for _enable_flash_save() for
more information.

#### setDataspeed(speed, saveFlash = False)
Sets custom bit timing for WS2812-type LEDs.
**CAUTION:** For advanced users only.  If you don't know
exactly why you want to do this, DON'T DO IT.

See discussion in this thread on the Pixelblaze forum:
https://forum.electromage.com/t/timing-of-a-cheap-strand/739

Note that you must call _enable_flash_save() in order to use
the saveFlash parameter to make your new timing (semi) permanent.

#### setPixelCount(nPixels):
Sets the number of LEDs attached to the Pixelblaze. Does not alter the
current pixel map, which may then be incorrect after pixelCount has 
changed.

CAUTION: This always causes a flash write, and should be used
only if you have a specific need to change the LED count
dynamically. For normal uses the "Settings" page of Pixelblaze
Web UI is the recommended way to configure this value.

#### setSequenceTimer(n)
Sets number of milliseconds the Pixelblaze's sequencer will run each pattern
before switching to the next.

#### startSequencer(mode = 1)
Enable and start the Pixelblaze's internal sequencer. The optional mode parameter
can be 1 - shuffle all patterns, or 2 - playlist mode.  The playlist
must be configured through the Pixelblaze's web UI.

#### stopSequencer()
Stop and disable the Pixelblaze's internal sequencer

#### setVariable(var_name, value)
Sets a single variable to the specified value. Does not check to see if the
variable is actually exported by the current active pattern.

#### setVars(json_vars)
Sets pattern variables contained in the json_vars (JSON object) argument.
Does not check to see if the variables are exported by the current active pattern.

#### unpause():
Resume rendering if halted by pause(). No effect otherwise.

#### variableExists(var_name)
Returns True if the specified variable exists in the active pattern, False otherwise.

#### waitForEmptyQueue(timeout_ms=1000):
Wait until the Pixelblaze's websocket message queue is empty, or until
timeout_ms milliseconds have elapsed.  Returns True if an empty queue
acknowldgement was received, False if timeout or error occurs.

## Utility methods
#### _enable_flash_save()
**IMPORTANT SAFETY TIP:**
To preserve your Pixelblaze's flash memory, which can wear out after a number of
cycles, you must call this method before using setControls() with the
saveFlash parameter set to True.
If this method is not called, setControls() will ignore the saveFlash parameter
and will not save settings to flash memory.

#### _id_from_name(patterns, name)
Utility method: Given the list of patterns and text name of a pattern, returns that pattern's ID

#### _get_pattern_id(pid)
Returns a pattern ID if passed either a valid ID or a text name


