<!-- markdownlint-disable -->

<a href="../pixelblaze/pixelblaze.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `pixelblaze`
A library that provides a simple, synchronous interface for communicating with and controlling Pixelblaze LED controllers. 

This module contains the following classes: 


- [`Pixelblaze`](#class-pixelblaze): an object for controlling Pixelblazes. 


- [`PBB`](#class-pbb): an object for creating and manipulating Pixelblaze Binary Backups. 


- [`PBP`](#class-pbp): an object for creating and manipulating Pixelblaze Binary Patterns. 


- [`EPE`](#class-epe): an object for creating and manipulating Electromage Pattern Exports. 



---

<a href="../pixelblaze/pixelblaze.py#L99"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Pixelblaze`
The Pixelblaze class presents a simple synchronous interface to a single Pixelblaze's websocket API.  

The constructor takes the Pixelblaze's IPv4 address in the usual 12 digit numeric form (for example, "192.168.4.1"). To control multiple Pixelblazes, create multiple objects. 

The objective is to provide 99% coverage of the functionality of the Pixelblaze webUI, and so the supported methods are named and grouped according to the tabs of the webUI: 

**CREATION** 


- [`__init__()`](#method-init) 
- [`EnumerateAddresses()`](#method-enumerateaddresses) 
- [`EnumerateDevices()`](#method-enumeratedevices) 

**PATTERNS tab** 

*SEQUENCER section* 


- [`getSequencerMode`](#method-getSequencerMode)/[`setSequencerMode`](#method-setSequencerMode) 
- [`getSequencerState`](#method-getSequencerState)/[`setSequencerState`](#method-setSequencerState) 
- [`getSequencerShuffleTime`](#method-getSequencerShuffleTime)/[`setSequencerShuffleTime`](#method-setSequencerShuffleTime) 
- [`getSequencerPlaylist`](#method-getSequencerPlaylist)/[`addToSequencerPlaylist`](#method-addToSequencerPlaylist)/[`setSequencerPlaylist`](#method-setSequencerPlaylist) 

*SAVED PATTERNS section* 


- [`getPatternList`](#method-getPatternList) 
- [`getActivePattern`](#method-getActivePattern)/[`setActivePattern`](#method-setActivePattern) 
- [`getActiveVariables`](#method-getActiveVariables)/[`setActiveVariables`](#method-setActiveVariables) 
- [`getActiveControls`](#method-getActiveControls)/[`setActiveControls`](#method-setActiveControls) 
- [`deletePattern`](#method-deletePattern) 
- [`getPatternAsEpe`](#method-getPatternAsEpe) 

**EDIT tab** 


- [`getPatternControls`](#method-getPatternControls) 
- [`getPatternSourceCode`](#method-getPatternSourceCode) 
- [`sendPatternToRenderer`](#method-sendPatternToRenderer) 
- [`savePattern`](#method-savePattern) 

**MAPPER tab** 


- [`getMapFunction`](#method-getMapFunction)/[`setMapFunction`](#method-setMapFunction) 
- [`getMapData`](#method-getMapData)/[`setMapData`](#method-setMapData) 

**SETTINGS tab** 


- [`getConfigSettings`](#method-getConfigSettings) 
- [`getConfigSequencer`](#method-getConfigSequencer) 
- [`getConfigExpander`](#method-getConfigExpander) 

***NAME section*** 


- [`getDeviceName`](#method-getDeviceName)/[`setDeviceName`](#method-setDeviceName) 
- [`getDiscovery`](#method-getDiscovery)/[`setDiscovery`](#method-setDiscovery) 
- [`getTimezone`](#method-getTimezone)/[`setTimezone`](#method-setTimezone) 
- [`getAutoOffEnable`](#method-getAutoOffEnable)/[`setAutoOffEnable`](#method-setAutoOffEnable) 
- [`getAutoOffStart`](#method-getAutoOffStart)/[`setAutoOffStart`](#method-setAutoOffStart) 
- [`getAutoOffEnd`](#method-getAutoOffEnd)/[`setAutoOffEnd`](#method-setAutoOffEnd) 

***LED section*** 


- [`getBrightnessLimit`](#method-getBrightnessLimit)/[`setBrightnessLimit`](#method-setBrightnessLimit) 
- [`getLedType`](#method-getLedType)/[`setLedType`](#method-setLedType) 
- [`getPixelCount`](#method-getPixelCount)/[`setPixelCount`](#method-setPixelCount) 
- [`getDataSpeed`](#method-getDataSpeed)/[`setDataSpeed`](#method-setDataSpeed) 
- [`getColorOrder`](#method-getColorOrder)/[`setColorOrder`](#method-setColorOrder) 
- [`getCpuSpeed`](#method-getCpuSpeed)/[`setCpuSpeed`](#method-setCpuSpeed) 
- [`getNetworkPowerSave`](#method-getNetworkPowerSave)/[`setNetworkPowerSave`](#method-setNetworkPowerSave) 

***UPDATES section*** 


- [`getUpdateState`](#method-getUpdateState)/[`installUpdate`](#method-installUpdate) 
- [`getVersion`](#method-getVersion)/[`getVersionMajor`](#method-getVersionMajor)/[`getVersionMinor`](#method-getVersionMinor)/ 

***BACKUPS section*** 


- [`saveBackup`](#method-saveBackup)/[`restoreFromBackup`](#method-restoreFromBackup) 
- [`reboot`](#method-reboot) 

**ADVANCED tab** 


- [`getBrandName`](#method-getBrandName)/[`setBrandName`](#method-setBrandName) 
- [`getSimpleUiMode`](#method-getSimpleUiMode)/[`setSimpleUiMode`](#method-setSimpleUiMode) 
- [`getLearningUiMode`](#method-getLearningUiMode)/[`setLearningUiMode`](#method-setLearningUiMode) 

**GLOBAL CONTROLS** 


- [`getBrightnessSlider`](#method-getBrightnessSlider)/[`setBrightnessSlider`](#method-setBrightnessSlider) 

**LOW-LEVEL SEND/RECEIVE** 


- [`wsReceive`](#method-wsreceive) 
- [`wsSendJson`](#method-wssendjson) 
- [`wsSendBinary`](#method-wssendbinary) 

**FILESYSTEM** 


- [`getFileList`](#method-getfilelist) 
- [`getFile`](#method-getfile)/[`putFile`](#method-putfile)/[`deleteFile`](#method-deletefile) 

**STATISTICS** 


- [`getStatistics`](#method-getStatistics) 
- [`getFPS`](#method-getFPS) 
- [`getUptime`](#method-getUptime) 
- [`getStorageSize`](#method-getStorageSize) 
- [`getStorageUsed`](#method-getStorageUsed) 

<a href="../pixelblaze/pixelblaze.py#L232"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(ipAddress: str, proxyUrl: str = None)
```

Initializes an object for communicating with and controlling a Pixelblaze. 



**Args:**
 
 - <b>`ipAddress`</b> (str):  The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1"). 
 - <b>`proxyUrl`</b> (str, optional):  The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None. 




---

<a href="../pixelblaze/pixelblaze.py#L352"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `EnumerateAddresses`

```python
EnumerateAddresses(
    timeout: int = 1500,
    proxyUrl: str = None,
    hostIP: str = '0.0.0.0'
) → LightweightEnumerator
```

Returns an enumerator that will iterate through all the Pixelblazes on the local network, until {timeout} milliseconds have passed with no new devices appearing. 



**Args:**
 
 - <b>`hostIP`</b> (str, optional):  The network interface on which to listen for Pixelblazes. Defaults to "0.0.0.0" meaning all available interfaces. 
 - <b>`timeout`</b> (int, optional):  The amount of time in milliseconds to listen for a new Pixelblaze to announce itself (They announce themselves once per second). Defaults to 1500. 
 - <b>`proxyUrl`</b> (str, optional):  The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None. 



**Returns:**
 
 - <b>`LightweightEnumerator`</b>:  A subclassed Python enumerator object that returns (as a string) the IPv4 address of a Pixelblaze, in the usual dotted-quads numeric format. 

---

<a href="../pixelblaze/pixelblaze.py#L366"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `EnumerateDevices`

```python
EnumerateDevices(
    timeout: int = 1500,
    proxyUrl: str = None,
    hostIP: str = '0.0.0.0'
) → LightweightEnumerator
```

Returns an enumerator that will iterate through all the Pixelblazes on the local network, until {timeout} milliseconds have passed with no new devices appearing. 



**Args:**
 
 - <b>`hostIP`</b> (str, optional):  The network interface on which to listen for Pixelblazes. Defaults to "0.0.0.0" meaning all available interfaces. 
 - <b>`timeout`</b> (int, optional):  The amount of time in milliseconds to listen for a new Pixelblaze to announce itself (They announce themselves once per second). Defaults to 1500. 
 - <b>`proxyUrl`</b> (str, optional):  The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None. 



**Returns:**
 
 - <b>`LightweightEnumerator`</b>:  A subclassed Python enumerator object that returns a Pixelblaze object for controlling a discovered Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L1048"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `addToSequencerPlaylist`

```python
addToSequencerPlaylist(
    playlistContents: dict,
    patternId: str,
    duration: int
) → dict
```

Appends a new entry to the specified playlist. 



**Args:**
 
 - <b>`patternId`</b> (str):  The patternId of the pattern to be played. 
 - <b>`duration`</b> (int):  The number of milliseconds to play the pattern. 
 - <b>`playlistContents`</b> (dict):  The results of a previous call to `getSequencerPlaylist`. 



**Returns:**
 
 - <b>`dict`</b>:  The updated playlist, which can then be sent back to the Pixelblaze with `setSequencerPlaylist`. 

---

<a href="../pixelblaze/pixelblaze.py#L1227"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `compilePattern`

```python
compilePattern(patternCode: str) → bytes
```

Compiles pattern sourcecode into a bytecode blob. 



**Args:**
 
 - <b>`patternCode`</b> (str):  The PBscript sourcecode of the pattern. 



**Returns:**
 
 - <b>`bytes`</b>:  a compiled blob of bytecode, ready to send to the Pixelblaze using `sendPatternToRenderer()`. 

---

<a href="../pixelblaze/pixelblaze.py#L2210"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `controlExists`

```python
controlExists(controlName: str, patternId: str = None) → bool
```

Tests whether the named control exists in the specified pattern. If no pattern is specified, the currently active pattern is assumed. 

Note that the active pattern can be undefined on a freshly started Pixelblaze until the pattern has been explicitly set.  This function also will return False if the active pattern is not available. 



**Args:**
 
 - <b>`controlName`</b> (str):  The name of the control. 
 - <b>`patternId`</b> (str, optional):  The pattern in which to test for the presence of the control. Defaults to None. 



**Returns:**
 
 - <b>`bool`</b>:  True if the specified control exists, False otherwise. 

---

<a href="../pixelblaze/pixelblaze.py#L780"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `deleteFile`

```python
deleteFile(fileName: str) → bool
```

Deletes a file from this Pixelblaze using the HTTP API. 



**Args:**
 
 - <b>`fileName`</b> (str):  The pathname (as returned from `getFileList`) of the file to be deleted. 



**Returns:**
 
 - <b>`bool`</b>:  True if the file was successfully stored; False otherwise. 

---

<a href="../pixelblaze/pixelblaze.py#L1121"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `deletePattern`

```python
deletePattern(patternId: str)
```

Delete a pattern saved on the Pixelblaze. 



**Args:**
 
 - <b>`patternId`</b> (str):  The patternId of the desired pattern. 

---

<a href="../pixelblaze/pixelblaze.py#L1185"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getActiveControls`

```python
getActiveControls(configSequencer: dict = None) → dict
```

Returns the collection of controls for the pattern currently running on the Pixelblaze. 

If there are no controls or no pattern has been set, returns an empty dictionary. 



**Args:**
 
 - <b>`configSequencer`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`dict`</b>:  A dictionary containing the control names and values, with controlName as the key and controlValue as the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1173"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getActivePattern`

```python
getActivePattern(configSequencer: dict = None) → str
```

Returns the ID of the pattern currently running on the Pixelblaze. 



**Args:**
 
 - <b>`configSequencer`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`str`</b>:  The patternId of the current pattern, if any; otherwise an empty string. 

---

<a href="../pixelblaze/pixelblaze.py#L1140"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getActiveVariables`

```python
getActiveVariables() → dict
```

Gets the names and values of all variables exported by the current pattern. 



**Returns:**
 
 - <b>`dict`</b>:  A dictionary containing all the variables exported by the active pattern, with variableName as the key and variableValue as the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1718"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getAutoOffEnable`

```python
getAutoOffEnable(configSettings: dict = None) → bool
```

Returns whether the auto-Off timer is enabled. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`bool`</b>:  A boolean indicating whether the auto-Off timer is enabled. 

---

<a href="../pixelblaze/pixelblaze.py#L1742"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getAutoOffEnd`

```python
getAutoOffEnd(configSettings: dict = None) → str
```

Returns the time, if any, at which the Pixelblaze will turn on the pattern when the auto-Off timer is enabled. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`str`</b>:  A Unix time string in "HH:MM" format. 

---

<a href="../pixelblaze/pixelblaze.py#L1730"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getAutoOffStart`

```python
getAutoOffStart(configSettings: dict = None) → str
```

Returns the time, if any, at which the Pixelblaze will turn off the pattern when the auto-Off timer is enabled. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`str`</b>:  A Unix time string in "HH:MM" format. 

---

<a href="../pixelblaze/pixelblaze.py#L2107"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getBrandName`

```python
getBrandName(configSettings: dict = None) → str
```

Returns the brand name, if any, of this Pixelblaze (blank unless rebadged by a reseller). 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`str`</b>:  The brand name. 

---

<a href="../pixelblaze/pixelblaze.py#L1854"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getBrightnessLimit`

```python
getBrightnessLimit(configSettings: dict = None) → int
```

Returns the maximum brightness for the Pixelblaze. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The maximum brightness, expressed as a percent value between 0 and 100 (yes, it's inconsistent with the 'brightness' settings). 

---

<a href="../pixelblaze/pixelblaze.py#L902"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getBrightnessSlider`

```python
getBrightnessSlider(configSettings: dict = None) → float
```

Get the value of the UI brightness slider. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`float`</b>:  A floating-point value between 0.0 and 1.0. 

---

<a href="../pixelblaze/pixelblaze.py#L2248"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getColorControlName`

```python
getColorControlName(patternId: str = None) → str
```

Returns the name of the specified pattern's first rgbPicker or hsvPicker control if one exists, or None otherwise. 



**Args:**
 
 - <b>`patternId`</b> (str, optional):  The pattern to search for color controls; or the currently active pattern if not specified. Defaults to None. 



**Returns:**
 
 - <b>`str`</b>:  The name of the specified pattern's first rgbPicker or hsvPicker control if one exists, or None otherwise. 

---

<a href="../pixelblaze/pixelblaze.py#L2228"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getColorControlNames`

```python
getColorControlNames(patternId: str = None) → list
```

Returns a list of names of the specified pattern's rgbPicker or hsvPicker controls if any exist, None otherwise.  If the pattern argument is not specified, check the currently running pattern 

---

<a href="../pixelblaze/pixelblaze.py#L1895"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getColorOrder`

```python
getColorOrder(configSettings: dict = None) → <enum 'colorOrders'>
```

Returns the color order of the LEDs connected to the Pixelblaze. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`colorOrders`</b>:  The ordering for the color data sent to the LEDs. 

---

<a href="../pixelblaze/pixelblaze.py#L1548"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getConfigExpander`

```python
getConfigExpander() → dict
```

Retrieves the OutputExpander configuration. 



**Returns:**
 
 - <b>`dict`</b>:  The OutputExpander configuration as a dictionary, with settingName as the key and settingValue as the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1536"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getConfigSequencer`

```python
getConfigSequencer() → dict
```

Retrieves the Sequencer state. 



**Returns:**
 
 - <b>`dict`</b>:  The sequencer configuration as a dictionary, with settingName as the key and settingValue as the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1503"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getConfigSettings`

```python
getConfigSettings() → dict
```

Returns the configuration as defined on the Settings tab of the Pixelblaze. 



**Returns:**
 
 - <b>`dict`</b>:  A dictionary containing the configuration settings, with settingName as the key and settingValue as the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1943"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getCpuSpeed`

```python
getCpuSpeed(configSettings: dict = None) → <enum 'cpuSpeeds'>
```

Returns the CPU speed of the Pixelblaze. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`cpuSpeeds`</b>:  An enumeration representing the CPU speed. 

---

<a href="../pixelblaze/pixelblaze.py#L1883"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getDataSpeed`

```python
getDataSpeed(configSettings: dict = None) → int
```

Returns the data speed of the LEDs connected to the Pixelblaze. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The data speed for communicating with the LEDs. 

---

<a href="../pixelblaze/pixelblaze.py#L1681"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getDeviceName`

```python
getDeviceName(configSettings: dict = None) → str
```

Returns the user-friendly name of the Pixelblaze. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`str`</b>:  The user-friendly name of the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L1693"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getDiscovery`

```python
getDiscovery(configSettings: dict = None) → bool
```

Returns a boolean signifying whether the Pixelblaze announces itself to the Electromage Discovery Service. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`bool`</b>:  A boolean signifying whether the Pixelblaze announces itself to the Electromage Discovery Service. 

---

<a href="../pixelblaze/pixelblaze.py#L837"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getFPS`

```python
getFPS(savedStatistics: dict = None) → float
```

Return the speed (in Frames per Second) of the pattern rendering. 



**Args:**
 
 - <b>`savedStatistics`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The pattern speed in FPS, as reported in a Pixelblaze statistics message. 

---

<a href="../pixelblaze/pixelblaze.py#L748"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getFile`

```python
getFile(fileName: str) → bytes
```

Downloads a file from the Pixelblaze using the HTTP API. 



**Args:**
 
 - <b>`fileName`</b> (str):  The pathname (as returned from `getFileList`) of the file to be downloaded. 



**Returns:**
 
 - <b>`bytes`</b>:  The contents of the file. 

---

<a href="../pixelblaze/pixelblaze.py#L683"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getFileList`

```python
getFileList(fileTypes: fileTypes = <fileTypes.fileAll: 63>) → list[str]
```

Returns a list of all the files of a particular type stored on the Pixelblaze's filesystem. 

For Pixelblazes running firmware versions lower than 2.29/3.24 (the point at which  the necessary API was introduced), the list includes the names of optional configuration  files that may or may not exist on a particular Pixelblaze, depending on its setup. 



**Args:**
 
 - <b>`fileTypes`</b> (fileTypes, optional):  A bitmasked enumeration of the fileTypes to be listed. Defaults to fileTypes.fileAll. 



**Returns:**
 
 - <b>`list[str]`</b>:  A list of filenames of the requested fileType. 

---

<a href="../pixelblaze/pixelblaze.py#L2131"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getLearningUiMode`

```python
getLearningUiMode(configSettings: dict = None) → bool
```

Returns whether "Learning UI Mode" is enabled. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`bool`</b>:  A boolean indicating whether "Learning UI Mode" is enabled. 

---

<a href="../pixelblaze/pixelblaze.py#L1866"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getLedType`

```python
getLedType(configSettings: dict = None) → <enum 'ledTypes'>
```

Returns the type of LEDs connected to the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L1420"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getMapCoordinates`

```python
getMapCoordinates(mapData: bytes = None) → list
```

Gets a unit-normalized representation of the pixelMap as an array (1D/2D/3D) of arrays. 



**Args:**
 
 - <b>`mapData`</b> (bytes, optional):  A blob of mapData as returned from getMapData(); if omitted, the mapData will be fetched from the Pixelblaze anew. 



**Returns:**
 
 - <b>`list`</b>:  A list containing one to three lists of floats, representing the X, Y and Z world coordinates (range 0..1) for each pixel. 

---

<a href="../pixelblaze/pixelblaze.py#L1400"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getMapData`

```python
getMapData() → bytes
```

Gets the binary representation of the pixelMap entered on the 'Mapper' tab. 



**Returns:**
 
 - <b>`bytes`</b>:  The binary mapData as generated by the Mapper tab of the Pixelblaze webUI. 

---

<a href="../pixelblaze/pixelblaze.py#L1352"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getMapFunction`

```python
getMapFunction() → str
```

Returns the mapFunction text used to populate the Mapper tab in the Pixelblaze UI. 



**Returns:**
 
 - <b>`str`</b>:  The text of the mapFunction. 

---

<a href="../pixelblaze/pixelblaze.py#L1464"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getMapOffsets`

```python
getMapOffsets(mapCoordinates: list = None) → list
```

Gets an integer-based representation of the pixelMap as an array (1D/2D/3D) of arrays. 



**Args:**
 
 - <b>`mapCoordinates`</b> (list, optional):  A list of mapCoordinates as returned from getMapCoordinates(); if omitted, the mapCoordinates will be fetched from the Pixelblaze anew. 



**Returns:**
 
 - <b>`list`</b>:  A list containing one to three lists of integers, representing the X, Y and Z indices (range 0..pixelCount) for each pixel. 

---

<a href="../pixelblaze/pixelblaze.py#L1956"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getNetworkPowerSave`

```python
getNetworkPowerSave(configSettings: dict = None) → bool
```

Returns whether the "Network Power Saving" mode is enabled (and WiFi is disabled). 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`bool`</b>:  Whether the "Network Power Saving" mode is enabled. 

---

<a href="../pixelblaze/pixelblaze.py#L1103"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPatternAsEpe`

```python
getPatternAsEpe(patternId: str) → str
```

Convert a stored pattern into an exportable, portable JSON format (which then needs to be saved by the caller). 



**Args:**
 
 - <b>`patternId`</b> (str):  The patternId of the desired pattern. 



**Returns:**
 
 - <b>`str`</b>:  The exported pattern as a JSON dictionary. 

---

<a href="../pixelblaze/pixelblaze.py#L1201"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPatternControls`

```python
getPatternControls(patternId: str) → dict
```

Returns the name and value of any UI controls exported by the specified pattern. 



**Args:**
 
 - <b>`patternId`</b> (str):  The patternId of the pattern. 



**Returns:**
 
 - <b>`dict`</b>:  A dictionary containing the control names and values, with controlName as the key and controlValue as the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1064"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPatternList`

```python
getPatternList(forceRefresh: bool = False) → dict
```

Returns a list of all the patterns saved on the Pixelblaze. 

Normally reads from the cached pattern list, which is refreshed every 10 minutes by default. To change the cache refresh interval, call setCacheRefreshTime(seconds). 



**Args:**
 
 - <b>`forceRefresh`</b> (bool, optional):  Forces a refresh of the cached patternList. Defaults to False. 



**Returns:**
 
 - <b>`dict`</b>:  A dictionary of the patterns stored on the Pixelblaze, where the patternId is the key and the patternName is the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1214"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPatternSourceCode`

```python
getPatternSourceCode(patternId: str) → str
```

Gets the sourceCode of a saved pattern from the Pixelblaze. 



**Args:**
 
 - <b>`patternId`</b> (str):  The patternId of the desired pattern. 



**Returns:**
 
 - <b>`str`</b>:  A string representation of a JSON dictionary containing the pattern source code. 

---

<a href="../pixelblaze/pixelblaze.py#L651"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPeers`

```python
getPeers()
```

A new command, added to the API but not yet implemented as of v2.29/v3.24, that will return a list of all the Pixelblazes visible on the local network segment. 



**Returns:**
 
 - <b>`TBD`</b>:  To be defined once @wizard implements the function. 

---

<a href="../pixelblaze/pixelblaze.py#L1871"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPixelCount`

```python
getPixelCount(configSettings: dict = None) → int
```

Returns the number of LEDs connected to the Pixelblaze. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The number of LEDs connected to the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L819"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPreviewFrame`

```python
getPreviewFrame() → bytes
```

Grab one of the preview frames that Pixelblaze sends after every render cycle. 



**Returns:**
 
 - <b>`bytes`</b>:  a collection of bytes representing `pixelCount` tuples containing the (R, G, B) values for each pixel in the pattern preview. 

---

<a href="../pixelblaze/pixelblaze.py#L1129"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPreviewImage`

```python
getPreviewImage(patternId: str) → bytes
```

Gets the preview image (a JPEG with 150 iterations of the pattern) saved within a pattern. 



**Args:**
 
 - <b>`patternId`</b> (str):  The patternId of the desired pattern. 



**Returns:**
 
 - <b>`bytes`</b>:  A JPEG image in which each column represents a particular LED and each row represents an iteration of the pattern. 

---

<a href="../pixelblaze/pixelblaze.py#L945"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getSequencerMode`

```python
getSequencerMode(configSequencer: dict = None) → <enum 'sequencerModes'>
```

Gets the current sequencer mode. 



**Args:**
 
 - <b>`configSequencer`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`sequencerModes`</b>:  The sequencerMode. 

---

<a href="../pixelblaze/pixelblaze.py#L1027"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getSequencerPlaylist`

```python
getSequencerPlaylist(playlistId: str = '_defaultplaylist_')
```

Fetches the specified playlist.  At the moment, only the default playlist is supported by the Pixelblaze. 



**Args:**
 
 - <b>`playlistId`</b> (str, optional):  The name of the playlist (for future enhancement; currently only '_defaultplaylist_' is supported). Defaults to "_defaultplaylist_". 



**Returns:**
 
 - <b>`dict`</b>:  The contents of the playlist. 

---

<a href="../pixelblaze/pixelblaze.py#L1013"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getSequencerShuffleTime`

```python
getSequencerShuffleTime(configSequencer: dict = None) → int
```

Gets the time the Pixelblaze's sequencer will run each pattern before switching to the next. 



**Args:**
 
 - <b>`configSequencer`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The number of milliseconds to play each pattern. 

---

<a href="../pixelblaze/pixelblaze.py#L957"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getSequencerState`

```python
getSequencerState(configSequencer: dict = None) → bool
```

Gets the current sequencer run state. 



**Args:**
 
 - <b>`configSequencer`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`bool`</b>:  True if the sequencer is running; False otherwise. 

---

<a href="../pixelblaze/pixelblaze.py#L2119"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getSimpleUiMode`

```python
getSimpleUiMode(configSettings: dict = None) → bool
```

Returns whether "Simple UI Mode" is enabled. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`bool`</b>:  A boolean indicating whether "Simple UI Mode" is enabled. 

---

<a href="../pixelblaze/pixelblaze.py#L797"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getStatistics`

```python
getStatistics() → dict
```

Grab one of the statistical packets that Pixelblaze sends every second. 



**Returns:**
 
 - <b>`dict`</b>:  the JSON message received from the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L873"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getStorageSize`

```python
getStorageSize(savedStatistics: dict = None) → int
```

Return the available Flash storage on the Pixelblaze. 



**Args:**
 
 - <b>`savedStatistics`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The available storage in bytes, as reported in a Pixelblaze statistics message. 

---

<a href="../pixelblaze/pixelblaze.py#L861"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getStorageUsed`

```python
getStorageUsed(savedStatistics: dict = None) → int
```

Return the amount of Flash storage used on the Pixelblaze. 



**Args:**
 
 - <b>`savedStatistics`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The used storage in bytes, as reported in a Pixelblaze statistics message. 

---

<a href="../pixelblaze/pixelblaze.py#L1706"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getTimezone`

```python
getTimezone(configSettings: dict = None) → str
```

Returns the timezone, if any, for the Pixelblaze. 



**Args:**
 
 - <b>`configSettings`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None. 



**Returns:**
 
 - <b>`str`</b>:  A standard Unix tzstring. 

---

<a href="../pixelblaze/pixelblaze.py#L1980"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getUpdateState`

```python
getUpdateState() → <enum 'updateStates'>
```

Returns the updateState of the Pixelblaze. 



**Returns:**
 
 - <b>`updateStates`</b>:  An enumeration describing the updateState of the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L849"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getUptime`

```python
getUptime(savedStatistics: dict = None) → int
```

Return the uptime (in seconds) of the Pixelblaze. 



**Args:**
 
 - <b>`savedStatistics`</b> (dict, optional):  If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None. 



**Returns:**
 
 - <b>`int`</b>:  The uptime in seconds, as reported in a Pixelblaze statistics message. 

---

<a href="../pixelblaze/pixelblaze.py#L662"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getUrl`

```python
getUrl(endpoint: str = None) → str
```

Build the URL to communicate with the Pixelblaze using an HTTP endpoint. 



**Args:**
 
 - <b>`endpoint`</b> (str, optional):  The HTTP endpoint. Defaults to None, which returns the URL of the Pixelblaze webUI. 



**Returns:**
 
 - <b>`str`</b>:  The URL of the HTTP endpoint on the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L2021"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getVersion`

```python
getVersion() → float
```

Returns the firmware version of the Pixelblaze. 



**Returns:**
 
 - <b>`float`</b>:  The firmware version, in major.minor format. 

---

<a href="../pixelblaze/pixelblaze.py#L2031"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getVersionMajor`

```python
getVersionMajor() → int
```

Returns the major version number.  



**Returns:**
 
 - <b>`int`</b>:  A positive integer representing the integer portion of the version number (eg. for v3.24, returns 3). 

---

<a href="../pixelblaze/pixelblaze.py#L2039"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getVersionMinor`

```python
getVersionMinor() → int
```

Returns the minor version number.  



**Returns:**
 
 - <b>`int`</b>:  A positive integer representing the fractional portion of the version number (eg. for v3.24, returns 24). 

---

<a href="../pixelblaze/pixelblaze.py#L2000"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `installUpdate`

```python
installUpdate() → <enum 'updateStates'>
```

Installs new Pixelblaze firmware, if the current updateState indicates that an update is available. 



**Returns:**
 
 - <b>`updateStates`</b>:  An enumeration describing the new updateState of the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L990"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `nextSequencer`

```python
nextSequencer(saveToFlash: bool = False)
```

Mimics the 'Next' button in the UI.  If the sequencerMode is ShuffleAll or Playlist, advances the pattern sequencer to the next pattern. 



**Args:**
 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L2187"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `pauseRenderer`

```python
pauseRenderer(doPause: bool)
```

Pause rendering. Lasts until unpause() is called or the Pixelblaze is reset. 

CAUTION: For advanced users only.  Only used to stop the render engine before sending new bytecode.   

If you don't know exactly why you want to do this, DON'T DO IT. 



**Args:**
 
 - <b>`doPause`</b> (bool):  If True, pause the render engine; if False, resume it. 

---

<a href="../pixelblaze/pixelblaze.py#L980"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `pauseSequencer`

```python
pauseSequencer(saveToFlash: bool = False)
```

Mimics the 'Pause' button in the UI.  Pauses the pattern sequencer,  without changing the current position in the shuffle or playlist.  Has no effect if the sequencer is not currently running. 



**Args:**
 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L971"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `playSequencer`

```python
playSequencer(saveToFlash: bool = False)
```

Mimics the 'Play' button in the UI. Starts the pattern sequencer, the consequences of which will vary depending upon the sequencerMode. 



**Args:**
 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L763"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `putFile`

```python
putFile(fileName: str, fileContents: bytes) → bool
```

Uploads a file to the Pixelblaze using the HTTP API. 



**Args:**
 
 - <b>`fileName`</b> (str):  The pathname at which to store the file. 
 - <b>`fileContents`</b> (bytes):  The data to store in the file. 



**Returns:**
 
 - <b>`bool`</b>:  True if the file was successfully stored; False otherwise. 

---

<a href="../pixelblaze/pixelblaze.py#L2066"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `reboot`

```python
reboot()
```

Reboots the Pixelblaze. 

This is occasionally necessary, eg. to force the Pixelblaze to recognize changes to configuration files. 

---

<a href="../pixelblaze/pixelblaze.py#L2058"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `restoreFromBackup`

```python
restoreFromBackup(fileName: str)
```

Restores the contents of this Pixelblaze from a Pixelblaze Binary Backup file. 



**Args:**
 
 - <b>`fileName`</b> (str):  The desired filename for the Pixelblaze Binary Backup. 

---

<a href="../pixelblaze/pixelblaze.py#L2050"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `saveBackup`

```python
saveBackup(fileName: str)
```

Saves the contents of this Pixelblaze into a Pixelblaze Binary Backup file. 



**Args:**
 
 - <b>`fileName`</b> (str):  The desired filename for the Pixelblaze Binary Backup. 

---

<a href="../pixelblaze/pixelblaze.py#L1336"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `savePattern`

```python
savePattern(previewImage: bytes, sourceCode: str, byteCode: bytes)
```

Saves a new pattern to the Pixelblaze filesystem.  Mimics the effects of the 'Save' button.   

If you don't know how to generate the previewImage and byteCode components, you don't want to do this. 



**Args:**
 
 - <b>`previewImage`</b> (bytes):  A JPEG image in which each column represents a particular LED and each row represents an iteration of the pattern. 
 - <b>`sourceCode`</b> (str):  A string representation of a JSON dictionary containing the pattern source code. 
 - <b>`byteCode`</b> (bytes):  A valid blob of bytecode as generated by the Editor tab in the Pixelblaze webUI. 

---

<a href="../pixelblaze/pixelblaze.py#L1324"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `sendPatternToRenderer`

```python
sendPatternToRenderer(bytecode: bytes, controls: dict = {})
```

Sends a blob of bytecode and a JSON dictionary of UI controls to the Renderer. Mimics the actions of the webUI code editor. 



**Args:**
 
 - <b>`bytecode`</b> (bytes):  A valid blob of bytecode as generated by the Editor tab in the Pixelblaze webUI. 
 - <b>`controls`</b> (dict, optional):  a dictionary of UI controls exported by the pattern, with controlName as the key and controlValue as the value. Defaults to {}. 

---

<a href="../pixelblaze/pixelblaze.py#L520"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `sendPing`

```python
sendPing() → Optional[str]
```

Send a Ping message to the Pixelblaze and wait for the Acknowledgement response. 



**Returns:**
 
 - <b>`Union[str, None]`</b>:  The acknowledgement message received from the Pixelblaze, or None if a timeout occurred. 

---

<a href="../pixelblaze/pixelblaze.py#L1158"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setActiveControls`

```python
setActiveControls(dictControls: dict, saveToFlash: bool = False)
```

Sets the value of one or more UI controls exported from the active pattern. 



**Args:**
 
 - <b>`dictControls`</b> (dict):  A dictionary containing the values to be set, with controlName as the key and controlValue as the value. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1092"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setActivePattern`

```python
setActivePattern(patternId: str, saveToFlash: bool = False)
```

Sets the active pattern. 



**Args:**
 
 - <b>`patternId`</b> (str):  The patternId of the desired pattern. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L2200"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setActivePatternByName`

```python
setActivePatternByName(patternName: str, saveToFlash: bool = False)
```

Sets the currently running pattern using a text name. 



**Args:**
 
 - <b>`patternName`</b> (str):  The name of the pattern. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1148"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setActiveVariables`

```python
setActiveVariables(dictVariables: dict)
```

Sets the values of one or more variables exported by the current pattern. 

Variables not present in the current pattern are ignored. 



**Args:**
 
 - <b>`dict`</b>:  A dictionary containing the variables to be set, with variableName as the key and variableValue as the value. 

---

<a href="../pixelblaze/pixelblaze.py#L1646"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setAutoOffEnable`

```python
setAutoOffEnable(boolValue: bool, saveToFlash: bool = False)
```

Enables or disables the Pixelblaze's auto-Off scheduler. 



**Args:**
 
 - <b>`boolValue`</b> (bool):  A boolean indicating whether the auto-Off scheduler should be used. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1665"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setAutoOffEnd`

```python
setAutoOffEnd(timeValue: str, saveToFlash: bool = False)
```

Sets the time at which the Pixelblaze will turn on the pattern. 



**Args:**
 
 - <b>`timeValue`</b> (str):  A Unix time string in "HH:MM" format. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1655"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setAutoOffStart`

```python
setAutoOffStart(timeValue: str, saveToFlash: bool = False)
```

Sets the time at which the Pixelblaze will turn off the pattern. 



**Args:**
 
 - <b>`timeValue`</b> (str):  A Unix time string in "HH:MM" format. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L2077"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setBrandName`

```python
setBrandName(brandName: str)
```

Sets the brand name of the Pixelblaze (used by VARs to change the brand name that appears on the webUI). 



**Args:**
 
 - <b>`brandName`</b> (str):  The new name. 

---

<a href="../pixelblaze/pixelblaze.py#L1756"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setBrightnessLimit`

```python
setBrightnessLimit(maxBrightness: int, saveToFlash: bool = False)
```

Sets the Pixelblaze's global brightness limit. 



**Args:**
 
 - <b>`maxBrightness`</b> (int):  The maximum brightness, expressed as a percent value between 0 and 100 (yes, it's inconsistent with the 'brightness' settings). 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L887"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setBrightnessSlider`

```python
setBrightnessSlider(brightness: float, saveToFlash: bool = False)
```

Set the value of the UI brightness slider. 



**Args:**
 
 - <b>`brightness`</b> (float):  A floating-point value between 0.0 and 1.0. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L2278"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setCacheRefreshTime`

```python
setCacheRefreshTime(seconds: int)
```

Set the interval, in seconds, after which calls to `getPatternList()` clear the pattern cache and fetch a new pattern list from the Pixelblaze.   

The Default is 600 seconds (10 minutes); the maximum allowable value is clamped to a million seconds (about 277 hours, or 11.5 days). Anything else would be excessive. 



**Args:**
 
 - <b>`seconds`</b> (int):  The maximum age of the pattern cache. 

---

<a href="../pixelblaze/pixelblaze.py#L2264"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setColorControl`

```python
setColorControl(controlName: str, color, saveToFlash: bool = False)
```

Sets the 3-element color of the specified HSV or RGB color picker. 



**Args:**
 
 - <b>`controlName`</b> (str):  The name of the color control to change. 
 - <b>`color`</b>:  RGB or HSV colors, with all values in the range 0-1.  
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1838"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setColorOrder`

```python
setColorOrder(colorOrder: colorOrders, saveToFlash: bool = False)
```

Sets the color order for the LEDs connected to the Pixelblaze. 



**Args:**
 
 - <b>`colorOrder`</b> (colorOrders):  The ordering for the color data sent to the LEDs. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1914"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setCpuSpeed`

```python
setCpuSpeed(cpuSpeed: cpuSpeeds)
```

Sets the CPU speed of the Pixelblaze. 

Note that this setting will not take effect until the Pixelblaze is rebooted (which can be done with the `reboot` function). 



**Args:**
 
 - <b>`cpuSpeed`</b> (cpuSpeeds):  The desired CPU speed. 

---

<a href="../pixelblaze/pixelblaze.py#L1814"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setDataSpeed`

```python
setDataSpeed(speed: int, saveToFlash: bool = False)
```

Sets custom data rate for communicating with the LEDs. 

CAUTION: For advanced users only.  If you don't know exactly why you want to do this, DON'T DO IT. See discussion in this thread on the Pixelblaze forum: https://forum.electromage.com/t/timing-of-a-cheap-strand/739 



**Args:**
 
 - <b>`speed`</b> (int):  The data rate for communicating with the LEDs. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1611"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setDeviceName`

```python
setDeviceName(name: str)
```

Sets the device name of the Pixelblaze. 



**Args:**
 
 - <b>`name`</b> (str):  The human-readable name of the Pixelblaze. 

---

<a href="../pixelblaze/pixelblaze.py#L1619"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setDiscovery`

```python
setDiscovery(enableDiscovery: bool, timezoneName: str = None)
```

Sets whether this Pixelblaze announces its presence to (and gets a clocktime reference from) the Electromage Discovery Service. 



**Args:**
 
 - <b>`enableDiscovery`</b> (bool):  A boolean controlling whether or not this Pixelblaze announces itself to the Electromage Discovery Service. 
 - <b>`timezoneName`</b> (str, optional):  If present, a Unix tzstring specifying how to adjust the clocktime reference received from the Electromage Discovery Service. Defaults to None. 

---

<a href="../pixelblaze/pixelblaze.py#L2093"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setLearningUiMode`

```python
setLearningUiMode(doLearningMode: bool)
```

Enables or disables "Learning UI Mode" which has additional UI help for new users. 



**Args:**
 
 - <b>`doSimpleMode`</b> (bool):  Whether to enable "Learning UI Mode". 

---

<a href="../pixelblaze/pixelblaze.py#L1782"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setLedType`

```python
setLedType(ledType: ledTypes, dataSpeed: int = None, saveToFlash: bool = False)
```

Defines the type of LEDs connected to the Pixelblaze. 



**Args:**
 
 - <b>`ledType`</b> (ledTypes):  The type of LEDs connected to the Pixelblaze. 
 - <b>`dataSpeed`</b> (int, optional):  If provided, sets a custom data speed for communication with the LEDs; otherwise the defaults from the webUI are used. Defaults to None. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1408"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setMapData`

```python
setMapData(mapData: bytes, saveToFlash: bool = True)
```

Sets the binary mapData used by the Pixelblaze. 



**Args:**
 
 - <b>`mapData`</b> (bytes):  a blob of binary mapData as generated by the Mapper tab of the Pixelblaze webUI. 
 - <b>`saveToFlash`</b> (bool, optional):  A boolean indicating whether the mapData should be saved to Flash. Defaults to True. 

---

<a href="../pixelblaze/pixelblaze.py#L1360"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setMapFunction`

```python
setMapFunction(mapFunction: str) → bool
```

Sets the mapFunction text used to populate the Mapper tab in the Pixelblaze UI. 

Note that setting the map function also compiles and updates the mapData used by the Pixelblaze. 



**Args:**
 
 - <b>`mapFunction`</b> (str):  The text of the mapFunction. 



**Returns:**
 
 - <b>`bool`</b>:  True if the function text was successfully saved; otherwise False. 

---

<a href="../pixelblaze/pixelblaze.py#L1927"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setNetworkPowerSave`

```python
setNetworkPowerSave(disableWifi: bool)
```

Enables or disables the WiFi connection on the Pixelblaze, which can significantly reduce power requirements for battery-powered installations. 

Note that this setting will not take effect until the Pixelblaze is rebooted (which can be done with the `reboot` function). 



**Args:**
 
 - <b>`disableWifi`</b> (bool):  A boolean indicating whether to disable Wifi. 

---

<a href="../pixelblaze/pixelblaze.py#L1802"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setPixelCount`

```python
setPixelCount(nPixels: int, saveToFlash: bool = False)
```

Sets the number of LEDs attached to the Pixelblaze.  

Note that changing the number of pixels does not recalculate the pixelMap. 



**Args:**
 
 - <b>`nPixels`</b> (int):  The number of pixels. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L808"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setSendPreviewFrames`

```python
setSendPreviewFrames(doUpdates: bool)
```

Set whether or not the Pixelblaze sends pattern preview frames. 



**Args:**
 
 - <b>`doUpdates`</b> (bool):  True sends preview frames, False stops. 

---

<a href="../pixelblaze/pixelblaze.py#L921"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setSequencerMode`

```python
setSequencerMode(sequencerMode: sequencerModes, saveToFlash: bool = False)
```

Sets the sequencer mode to one of the available sequencerModes (Off, ShuffleAll, or Playlist). 



**Args:**
 
 - <b>`sequencerMode`</b> (enum):  The desired sequencer mode. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L1038"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setSequencerPlaylist`

```python
setSequencerPlaylist(
    playlistContents: dict,
    playlistId: str = '_defaultplaylist_'
)
```

Replaces the entire contents of the specified playlist.  At the moment, only the default playlist is supported by the Pixelblaze. 



**Args:**
 
 - <b>`playlistContents`</b> (dict):  The new playlist contents. 
 - <b>`playlistId`</b> (str, optional):  The name of the playlist (for future enhancement; currently only '_defaultplaylist_' is supported). Defaults to "_defaultplaylist_". 

---

<a href="../pixelblaze/pixelblaze.py#L998"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setSequencerShuffleTime`

```python
setSequencerShuffleTime(nMillis: int, saveToFlash: bool = False)
```

Sets the time the Pixelblaze's sequencer will run each pattern before switching to the next. 



**Args:**
 
 - <b>`nMillis`</b> (int):  The number of milliseconds to play each pattern. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L930"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setSequencerState`

```python
setSequencerState(sequencerState: bool, saveToFlash: bool = False)
```

Set the run state of the sequencer. 



**Args:**
 
 - <b>`sequencerState`</b> (bool):  A boolean value determining whether or not the sequencer should run. 
 - <b>`saveToFlash`</b> (bool, optional):  If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L2085"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setSimpleUiMode`

```python
setSimpleUiMode(doSimpleMode: bool)
```

Enables or disables "Simple UI Mode" which makes the UI more suitable for non-technical audiences. 



**Args:**
 
 - <b>`doSimpleMode`</b> (bool):  Whether to enable "Simple UI Mode". 

---

<a href="../pixelblaze/pixelblaze.py#L1633"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setTimezone`

```python
setTimezone(timezoneName: str)
```

Sets the Pixelblaze's timezone, which specifies how to adjust the clocktime reference provided by the Electromage Discovery Service. 

To clear the timezone, pass an empty string. 



**Args:**
 
 - <b>`timezoneName`</b> (str):  A Unix tzstring specifying how to adjust the clocktime reference provided by the Electromage Discovery Service. 

---

<a href="../pixelblaze/pixelblaze.py#L442"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `wsReceive`

```python
wsReceive(binaryMessageType: messageTypes = None) → Union[str, bytes, NoneType]
```

Wait for a message of a particular type from the Pixelblaze. 



**Args:**
 
 - <b>`binaryMessageType`</b> (messageTypes, optional):  The type of binary message to wait for (if None, waits for a text message). Defaults to None. 



**Returns:**
 
 - <b>`Union[str, bytes, None]`</b>:  The message received from the Pixelblaze (of type bytes for binaryMessageTypes, otherwise of type str), or None if a timeout occurred. 

---

<a href="../pixelblaze/pixelblaze.py#L581"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `wsSendBinary`

```python
wsSendBinary(
    binaryMessageType: messageTypes,
    blob: bytes,
    expectedResponse: str = None
)
```

Send a binary command to the Pixelblaze, and optionally wait for a suitable response. 



**Args:**
 
 - <b>`binaryMessageType`</b> (messageTypes, optional):  The type of binary message to send. 
 - <b>`blob`</b> (bytes):  The message body to be sent. 
 - <b>`expectedResponse`</b> (str, optional):  If present, the initial key of the expected JSON response to the command. Defaults to None. 



**Returns:**
 
 - <b>`response`</b>:  The message received from the Pixelblaze (of type bytes for binaryMessageTypes, otherwise of type str), or None if a timeout occurred. 

---

<a href="../pixelblaze/pixelblaze.py#L528"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `wsSendJson`

```python
wsSendJson(command: dict, expectedResponse=None) → Union[str, bytes, NoneType]
```

Send a JSON-formatted command to the Pixelblaze, and optionally wait for a suitable response. 



**Args:**
 
 - <b>`command`</b> (dict):  A Python dictionary which will be sent to the Pixelblaze as a JSON command. 
 - <b>`expectedResponse`</b> (str, optional):  If present, the initial key of the expected JSON response to the command. Defaults to None. 



**Returns:**
 
 - <b>`Union[str, bytes, None]`</b>:  The message received from the Pixelblaze (of type bytes for binaryMessageTypes, otherwise of type str), or None if a timeout occurred. 


---

<a href="../pixelblaze/pixelblaze.py#L2300"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `PBB`
This class provides methods for importing, exporting, and manipulating the contents of a Pixelblaze Binary Backup, as created from the Settings menu on a Pixelblaze. 

**CREATION** 
- [`fromFile()`](method-fromfile) 
- [`fromIpAddress()`](method-fromipaddress) 
- [`fromPixelblaze()`](method-frompixelblaze) 

**PROPERTIES** 
- [`deviceName()`](method-devicename) 
- [`getFileList()`](method-getfilelist) 

**MANIPULATION** 
- [`getFile()`](method-getfile)/[`putFile()`](method-putfile)/[`deleteFile()`](method-deletefile) 

**PERSISTENCE** 
- [`toFile()`](method-tofile) 
- [`toIpAddress()`](method-toipaddress) 
- [`toPixelblaze()`](method-topixelblaze) 



**Note:**

> The constructor is not intended to be called directly; objects are created and returned from the object creation methods described above. 

<a href="../pixelblaze/pixelblaze.py#L2328"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(name: str, blob: bytes)
```

Initializes a new Pixelblaze Binary Backup (PBB) object. 



**Args:**
 
 - <b>`id`</b> (str):  The patternId of the pattern. 
 - <b>`blob`</b> (bytes):  The binary contents of the pattern. 



**Note:**

> This method is not intended to be called directly; use the static methods `fromFile()`, `fromIpAddress()` or `fromPixelblaze()` methods to create and return a Pixelblaze Binary Backup (PBB) object. 


---

#### <kbd>property</kbd> deviceName

Gets the user-friendly name of the device from which this PixelBlazeBackup was made. 



**Returns:**
 
 - <b>`str`</b>:  The user-friendly name of the device from which this PixelBlazeBackup was made. 



---

<a href="../pixelblaze/pixelblaze.py#L2481"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `deleteFile`

```python
deleteFile(fileName: str)
```

Removes a particular file from this PixelBlazeBackup. 



**Args:**
 
 - <b>`fileName`</b> (str):  The name of the file to be deleted. 

---

<a href="../pixelblaze/pixelblaze.py#L2342"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromFile`

```python
fromFile(fileName: str) → PBB
```

Creates and returns a new Pixelblaze Binary Backup whose contents are loaded from a file on disk. 



**Args:**
 
 - <b>`fileName`</b> (str):  The filename of the Pixelblaze Binary Backup. 



**Returns:**
 
 - <b>`PBB`</b>:  A new Pixelblaze Binary Backup object. 

---

<a href="../pixelblaze/pixelblaze.py#L2354"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromIpAddress`

```python
fromIpAddress(ipAddress: str, proxyUrl: str = None, verbose: bool = False) → PBB
```

Creates and returns a new Pixelblaze Binary Backup whose contents are loaded from a Pixelblaze specified by IP address. 



**Args:**
 
 - <b>`ipAddress`</b> (str):  The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1"). 
 - <b>`proxyUrl`</b> (str, optional):  The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None. 
 - <b>`verbose`</b> (bool, optional):  A boolean specifying whether to print detailed progress statements. Defaults to False. 



**Returns:**
 
 - <b>`PBB`</b>:  A new Pixelblaze Binary Backup object. 

---

<a href="../pixelblaze/pixelblaze.py#L2370"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromPixelblaze`

```python
fromPixelblaze(pb: Pixelblaze, verbose: bool = False) → PBB
```

Creates and returns a new Pixelblaze Binary Backup whose contents are loaded from an existing Pixelblaze object. 



**Args:**
 
 - <b>`pb`</b> (Pixelblaze):  A Pixelblaze object. 
 - <b>`verbose`</b> (bool, optional):  A boolean specifying whether to print detailed progress statements. Defaults to False. 



**Returns:**
 
 - <b>`PBB`</b>:  A new Pixelblaze Binary Backup object. 

---

<a href="../pixelblaze/pixelblaze.py#L2459"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getFile`

```python
getFile(fileName: str) → bytes
```

Returns the contents of a particular file contained in this PixelBlazeBackup. 



**Args:**
 
 - <b>`fileName`</b> (str):  The name of the file to be returned. 



**Returns:**
 
 - <b>`bytes`</b>:  The contents of the requested file. 

---

<a href="../pixelblaze/pixelblaze.py#L2412"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getFileList`

```python
getFileList(fileTypes: fileTypes = <fileTypes.fileAll: 63>) → list[str]
```

Returns a sorted list of the files contained in this PixelBlazeBackup. 



**Args:**
 
 - <b>`fileTypes`</b> (fileTypes, optional):  An bitwise enumeration indicating the types of files to list. Defaults to fileTypes.fileAll. 



**Returns:**
 
 - <b>`list[str]`</b>:  A list of filenames. 

---

<a href="../pixelblaze/pixelblaze.py#L2470"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `putFile`

```python
putFile(fileName: str, fileContents: bytes)
```

Inserts or replaces the contents of a particular file into this PixelBlazeBackup. 



**Args:**
 
 - <b>`fileName`</b> (str):  The name of the file to be stored. 
 - <b>`fileContents`</b> (bytes):  The contents of the file to be stored. 

---

<a href="../pixelblaze/pixelblaze.py#L2492"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toFile`

```python
toFile(fileName: str = None, explode: bool = False)
```

Writes this Pixelblaze Binary Backup to a file on disk. 



**Args:**
 
 - <b>`fileName`</b> (str, optional):  If specified, the filename of the Pixelblaze Binary Backup to be created; otherwise the originating Pixelblaze name is used. Defaults to None. 
 - <b>`explode`</b> (bool, optional):  If specified, also exports the files within the Pixelblaze Binary Backup to a subdirectory. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L2542"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toIpAddress`

```python
toIpAddress(ipAddress: str, proxyUrl: str = None, verbose: bool = False)
```

Restores the contents of this PixelBlazeBackup to a Pixelblaze identified by IP Address. 



**Args:**
 
 - <b>`ipAddress`</b> (str):  The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1").. 
 - <b>`proxyUrl`</b> (str, optional):  The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None. 
 - <b>`verbose`</b> (bool, optional):  A boolean specifying whether to print detailed progress statements. Defaults to False. 

---

<a href="../pixelblaze/pixelblaze.py#L2554"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toPixelblaze`

```python
toPixelblaze(pb: Pixelblaze, verbose: bool = False)
```

Uploads the contents of this PixelBlazeBackup to the destination Pixelblaze. 



**Args:**
 
 - <b>`pb`</b> (Pixelblaze):  A Pixelblaze object. 
 - <b>`verbose`</b> (bool, optional):  A boolean specifying whether to print detailed progress statements. Defaults to False. 


---

<a href="../pixelblaze/pixelblaze.py#L2585"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `PBP`
This class represents a Pixelblaze Binary Pattern, as stored on the Pixelblaze filesystem or contained in a Pixelblaze Binary Backup. 

**CREATION** 
- [`fromBytes()`](method-frombytes) 
- [`fromFile()`](method-fromfile) 
- [`fromIpAddress()`](method-fromipaddress) 
- [`fromPixelblaze()`](method-frompixelblaze) 

**PROPERTIES** 
- [`id()`](method-id) 
- [`name()`](method-name) 
- [`jpeg()`](method-jpeg) 
- [`byteCode()`](method-bytecode) 
- [`sourceCode()`](method-sourcecode) 

**PERSISTENCE** 
- [`toFile()`](method-tofile) 
- [`toIpAddress()`](method-toipaddress) 
- [`toPixelblaze()`](method-topixelblaze) 
- [`toEPE()`](method-toepe) 
- [`explode()`](method-explode) 





**Note:**

> The constructor is not intended to be called directly; objects are created and returned from the object creation methods described above. 

<a href="../pixelblaze/pixelblaze.py#L2623"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(id: str, blob: bytes)
```

Initializes a new Pixelblaze Binary Pattern (PBP) object. 



**Args:**
 
 - <b>`id`</b> (str):  The patternId of the pattern. 
 - <b>`blob`</b> (bytes):  The binary contents of the pattern. 



**Note:**

> This method is not intended to be called directly; use the static methods `fromBytes()`, `fromFile()`, `fromIpAddress()` or `fromPixelblaze()` methods to create and return a PBP object. 


---

#### <kbd>property</kbd> byteCode

Returns (as a collection of bytes) the bytecode of the pattern contained in this Pixelblaze Binary Pattern (PBP). 



**Returns:**
 
 - <b>`bytes`</b>:  The bytecode of the pattern contained in this Pixelblaze Binary Pattern (PBP). 

---

#### <kbd>property</kbd> id

Returns the patternId of the pattern contained in this Pixelblaze Binary Pattern (PBP). 



**Returns:**
 
 - <b>`str`</b>:  The patternId of the pattern contained in this Pixelblaze Binary Pattern (PBP). 

---

#### <kbd>property</kbd> jpeg

Returns (as a collection of bytes) the preview JPEG of the pattern contained in this Pixelblaze Binary Pattern (PBP). 



**Returns:**
 
 - <b>`bytes`</b>:  The preview JPEG of the pattern contained in this Pixelblaze Binary Pattern (PBP). 

---

#### <kbd>property</kbd> name

Returns the (human-readable) name of the pattern contained in this Pixelblaze Binary Pattern (PBP). 



**Returns:**
 
 - <b>`str`</b>:  The (human-readable) name of the pattern contained in this Pixelblaze Binary Pattern (PBP). 

---

#### <kbd>property</kbd> sourceCode

Returns the source code of the pattern in this Pixelblaze Binary Pattern (PBP). 



**Returns:**
 
 - <b>`str`</b>:  The source code of the pattern as a JSON-encoded string. 



---

<a href="../pixelblaze/pixelblaze.py#L2790"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `explode`

```python
explode(path: str = None)
```

Exports all the components of this Pixelblaze Binary Pattern (PBP) as separate files. 



**Args:**
 
 - <b>`path`</b> (str, optional):  If provided, a pathname for the folder in which to export the components; otherwise derived from the patternId. Defaults to None. 

---

<a href="../pixelblaze/pixelblaze.py#L2637"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromBytes`

```python
fromBytes(patternId: str, blob: bytes) → PBP
```

Creates and returns a new Pixelblaze Binary Pattern (PBP) whose contents are initialized from a bytes array. 



**Args:**
 
 - <b>`patternId`</b> (str):  A patternId for the Pixelblaze Binary Pattern to be created. 
 - <b>`blob`</b> (bytes):  The binary contents of the Pixelblaze Binary Pattern to be created. 



**Returns:**
 
 - <b>`PBP`</b>:  A new Pixelblaze Binary Pattern object. 

---

<a href="../pixelblaze/pixelblaze.py#L2650"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromFile`

```python
fromFile(fileName: str) → PBP
```

Creates and returns a new Pixelblaze Binary Pattern (PBP) whose contents are loaded from a file on disk. 



**Args:**
 
 - <b>`fileName`</b> (str):  The name of the file to be loaded into a Pixelblaze Binary Pattern. 



**Returns:**
 
 - <b>`PBP`</b>:  A new Pixelblaze Binary Pattern object. 

---

<a href="../pixelblaze/pixelblaze.py#L2662"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromIpAddress`

```python
fromIpAddress(ipAddress: str, patternId: str, proxyUrl: str = None) → PBP
```

Creates and returns a new pattern Pixelblaze Binary Pattern (PBP) whose contents are downloaded from a URL. 



**Args:**
 
 - <b>`ipAddress`</b> (str):  The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1"). 
 - <b>`patternId`</b> (str):  The patternId of the Pixelblaze Binary Pattern to be loaded from the Pixelblaze. 
 - <b>`proxyUrl`</b> (str, optional):  The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None. 



**Returns:**
 
 - <b>`PBP`</b>:  A new Pixelblaze Binary Pattern object. 

---

<a href="../pixelblaze/pixelblaze.py#L2678"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromPixelblaze`

```python
fromPixelblaze(pb: Pixelblaze, patternId: str) → PBP
```

Creates and returns a new pattern Pixelblaze Binary Pattern (PBP) whose contents are downloaded from an active Pixelblaze object. 



**Args:**
 
 - <b>`pb`</b> (Pixelblaze):  An active Pixelblaze object. 
 - <b>`patternId`</b> (str):  The patternId of the Pixelblaze Binary Pattern to be loaded from the Pixelblaze. 



**Returns:**
 
 - <b>`PBP`</b>:  A new Pixelblaze Binary Pattern object. 

---

<a href="../pixelblaze/pixelblaze.py#L2776"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toEPE`

```python
toEPE() → EPE
```

Creates a new Electromage Pattern Export (EPE) and initializes it from the contents of this Pixelblaze Binary Pattern (PBP). 



**Returns:**
 
 - <b>`EPE`</b>:  A new Electromage Pattern Export object. 

---

<a href="../pixelblaze/pixelblaze.py#L2746"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toFile`

```python
toFile(fileName: str = None)
```

Saves this Pixelblaze Binary Pattern (PBP) to a file on disk. 



**Args:**
 
 - <b>`fileName`</b> (str, optional):  If provided, A name for the Pixelblaze Binary Pattern file to be created; otherwise, the name is derived from the patternId. Defaults to None. 

---

<a href="../pixelblaze/pixelblaze.py#L2757"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toIpAddress`

```python
toIpAddress(ipAddress: str, proxyUrl: str = None)
```

Uploads this Pixelblaze Binary Pattern (PBP) to a Pixelblaze identified by its IP address. 



**Args:**
 
 - <b>`ipAddress`</b> (str):  The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1"). 
 - <b>`proxyUrl`</b> (str, optional):  The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None. 

---

<a href="../pixelblaze/pixelblaze.py#L2768"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toPixelblaze`

```python
toPixelblaze(pb: Pixelblaze)
```

Uploads this Pixelblaze Binary Pattern (PBP) to an active Pixelblaze object. 



**Args:**
 
 - <b>`pb`</b> (Pixelblaze):  An active Pixelblaze object. 


---

<a href="../pixelblaze/pixelblaze.py#L2831"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `EPE`
This class provides methods for importing, exporting, and manipulating the contents of an Electromage Pattern Export (EPE), as exported from the Patterns list on a Pixelblaze. 

**CREATION** 
- [`fromBytes()`](method-frombytes) 
- [`fromFile()`](method-fromfile) 

**PROPERTIES** 
- [`patternId()`](method-patternid) 
- [`patternName()`](method-patternname) 
- [`sourceCode()`](method-sourcecode) 
- [`previewImage()`](method-previewimage) 

**PERSISTENCE** 
- [`toFile()`](method-tofile) 
- [`explode()`](method-explode) 



**Note:**

> The constructor is not intended to be called directly; objects are created and returned from the object creation methods described above. 

<a href="../pixelblaze/pixelblaze.py#L2855"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(blob: bytes)
```

Initializes a new Electromage Pattern Export (EPE) object. 



**Args:**
 
 - <b>`blob`</b> (bytes):  The contents of the Electromage Pattern Export (EPE). 



**Note:**

> This method is not intended to be called directly; use the static methods `fromBytes()` or `fromFile()` to create and return an Electromage Pattern Export object. 


---

#### <kbd>property</kbd> patternId

Returns the patternId of the pattern contained in this Electromage Pattern Export (EPE). 



**Returns:**
 
 - <b>`str`</b>:  The patternId of the pattern contained in this Electromage Pattern Export (EPE). 

---

#### <kbd>property</kbd> patternName

Returns the human-readable name of the pattern in this Electromage Pattern Export (EPE). 



**Returns:**
 
 - <b>`str`</b>:  The human-readable name of the pattern contained in this Electromage Pattern Export (EPE). 

---

#### <kbd>property</kbd> previewImage

Returns (as bytes) the preview JPEG of the pattern contained in this Electromage Pattern Export (EPE). 



**Returns:**
 
 - <b>`bytes`</b>:  The preview JPEG of the pattern contained in this Electromage Pattern Export (EPE). 

---

#### <kbd>property</kbd> sourceCode

Returns the source code of the pattern contained in this Electromage Pattern Export (EPE). 



**Returns:**
 
 - <b>`str`</b>:  The sourceCode of the pattern contained in this Electromage Pattern Export (EPE). 



---

<a href="../pixelblaze/pixelblaze.py#L2942"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `explode`

```python
explode(path: str)
```

Exports the components of this Electromage Pattern Export (EPE) to separate files. 



**Args:**
 
 - <b>`path`</b> (str):  If provided, a pathname for the folder in which to export the components; otherwise derived from the patternId. Defaults to None. 

---

<a href="../pixelblaze/pixelblaze.py#L2867"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromBytes`

```python
fromBytes(blob: bytes) → EPE
```

Creates and returns a new Electromage Pattern Export (EPE) whose contents are loaded from a bytes array. 



**Args:**
 
 - <b>`blob`</b> (bytes):  The data from which to create the Electromage Pattern Export (EPE). 



**Returns:**
 
 - <b>`EPE`</b>:  A new Electromage Pattern Export (EPE) object. 

---

<a href="../pixelblaze/pixelblaze.py#L2879"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `fromFile`

```python
fromFile(fileName: str) → EPE
```

Creates and returns a new portable pattern EPE whose contents are loaded from a file on disk. 



**Args:**
 
 - <b>`fileName`</b> (str):  The name of the file from which to create the Electromage Pattern Export (EPE). 



**Returns:**
 
 - <b>`EPE`</b>:  A new Electromage Pattern Export (EPE) object. 

---

<a href="../pixelblaze/pixelblaze.py#L2931"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `toFile`

```python
toFile(fileName: str = None)
```

Saves this Electromage Pattern Export (EPE) to a file on disk. 



**Args:**
 
 - <b>`fileName`</b> (str, optional):  If provided, a name for the file to be created; otherwise derived from the patternId. Defaults to None. 


---

<a href="../pixelblaze/pixelblaze.py#L3316"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `PixelblazeEnumerator`
Listens on a network to detect available Pixelblazes, which the user can then list or open as Pixelblaze objects.  Also provides time synchronization services for running synchronized patterns on a network of Pixelblazes. 

<a href="../pixelblaze/pixelblaze.py#L3336"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(hostIP='0.0.0.0')
```

Create an object that listens continuously for Pixelblaze beacon packets, maintains a list of Pixelblazes and supports synchronizing time on multiple Pixelblazes to allows them to run patterns simultaneously. Takes the IPv4 address of the interface to use for listening on the calling computer. Listens on all available interfaces if hostIP is not specified. 




---

<a href="../pixelblaze/pixelblaze.py#L3396"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `disableTimesync`

```python
disableTimesync()
```

Turns off the time synchronization -- the PixelblazeEnumerator will not automatically synchronize Pixelblazes. 

---

<a href="../pixelblaze/pixelblaze.py#L3388"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `enableTimesync`

```python
enableTimesync()
```

Instructs the PixelblazeEnumerator object to automatically synchronize time on all Pixelblazes. (Note that time synchronization is off by default when a new PixelblazeEnumerator is created.) 

---

<a href="../pixelblaze/pixelblaze.py#L3488"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `getPixelblazeList`

```python
getPixelblazeList()
```





---

<a href="../pixelblaze/pixelblaze.py#L3379"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `setDeviceTimeout`

```python
setDeviceTimeout(ms)
```

Sets the interval in milliseconds which the enumerator will wait without hearing from a device before removing it from the active devices list. 

The default timeout is 30000 (30 seconds). 

---

<a href="../pixelblaze/pixelblaze.py#L3403"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `start`

```python
start(hostIP)
```

Open socket for listening to Pixelblaze datagram traffic, set appropriate options and bind to specified interface and start listener thread. 

---

<a href="../pixelblaze/pixelblaze.py#L3425"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `stop`

```python
stop()
```

Stop listening for datagrams, terminate listener thread and close socket. 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
