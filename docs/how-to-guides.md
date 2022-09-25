# How-To Guides

This part of the project documentation focuses on a **problem-oriented** approach. You'll tackle common
tasks that you might have, with the help of the code provided in this project.

## How to get started?

The easiest way to use this library is to install it from PyPi:

```pip install pixelblaze-client```

and within your script import the classes from the `pixelblaze` module:

```
    # your_script.py
    from pixelblaze import *
```

After you've imported the class, you can follow along with any of the recipes below.

### Alternative installation method

If for some reason you can't use PyPi, you can download the code from this GitHub repository and place the `pixeblaze-client/` folder in the same directory as your Python script:

    your_project/
    │
    ├── pixelblaze-client/
    │   ├── __init__.py
    │   └── pixelblaze.py
    │
    └── your_script.py

Inside of `your_script.py` you can now import the classes from the `pixelblaze` module:

```
    # your_script.py
    from pixelblaze import *
```

After you've imported the class, you can follow along with any of the recipes below.

## How to find your Pixelblazes?

The `EnumerateAddresses` or `EnumerateDevices` iterators can help you here.

The `EnumerateAddresses` iterator returns the IP address of each Pixelblaze it finds, which gives the quickest response because it detects the Pixelblazes but does not actually communicate with them.

```
    print("Finding Pixelblazes...")
    for ipAddress in Pixelblaze.EnumerateAddresses(timeout=1500):
        print(f"  found a Pixelblaze at {ipAddress}")
```

The `EnumerateDevices` iterator detects Pixelblazes and returns an initialized Pixelblaze object for each one:

```
    print("Finding Pixelblazes...")
    for pixelblaze in Pixelblaze.EnumerateDevices(timeout=1500):
            print(f"  at {pixelblaze.ipAddress} found '{pixelblaze.getDeviceName()}'")
```

If you are looking for a specific Pixelblaze, use the `EnumerateAddresses` iterator; if you want to do something with *all* Pixelblazes, the `EnumerateDevices` iterator saves a few lines of code.

## How to connect to a Pixelblaze?

The `Pixelblaze` class is used to communicate with and control a Pixelblaze.  To create a Pixelblaze object, create an instance of the class specifying its IP address as a string in the usual dotted-quad notation, i.e. "192.168.4.1".  

```
    pb = Pixelblaze("192.168.4.1")
```

If you need or want to use a proxy server (for debugging it can be very useful to observe the protocol traffic by routing it through the [Fiddler Web Debugger](https://www.telerik.com/fiddler/)), you can specify the proxy type ("socks" or "http") and address using the `proxyUrl` argument:

```
    pb = Pixelblaze("192.168.4.1", proxyUrl="http://192.168.8.8:8888")
```

### Advanced topic: lifecycle management

The `Pixelblaze` class can be used in a `with` statement, which will automatically close the connection and dispose of the object when the `with` statement completes:

```
    with Pixelblaze("192.168.4.1") as pb:
        # Do something with the pb object.
        # Do something else with the pb object.
        pass

    # At this point, the pb object will be deleted.
```

Otherwise the connection will remain open until the Pixelblaze object goes out of scope and is garbage-collected.

## How to set which pattern is playing?

Pixelblaze refers to its patterns using an alphanumeric ID code which remains constant for the lifetime of a pattern.  Patterns also have a human-readable name which is displayed in the webUI pattern list and pattern editor, but it can be changed by the user so is not supported by this or the Pixelblaze API.

To find the ID of a pattern, use the `getPatternList()` method which returns a list of `(patternId, patternName)` tuples:

```
    # Get the pattern list.
    list = pb.getPatternList()

    # Select first element of the first tuple in the list.
    patternId = list[0][0]
```

Some patterns have UI controls which can be used to adjust the appearance of the patterns.  To retrieve the UI controls, use the `getPatternControls()` method:

```
    # Fetch any UI controls for this pattern.
    controls = pb.getPatternControls(patternId)
```

And finally, pass the patternId and the controls (which may be `None` if there were no controls) to the `setActivePattern()` method:
```
    # Ask the Pixelblaze to display this pattern.
    pb.setActivePattern(patternId, controls)
```

## How to change the parameters of the pattern that is currently playing?

Pixelblaze patterns can, if so designed, be modified at runtime in two ways.

Some patterns contain user interface elements such as sliders, color pickers or input numbers that can be used in the Pixelblaze webUI to adjust the pattern.  For these patterns, the values of the UI controls for the pattern currently playing can be read and modified with the `getActiveControls()` method (which returns a dictionary containing all the controls); then new values for one or all of the controls can be modified and sent back to the Pixelblaze with the `setActiveControls()` method.
