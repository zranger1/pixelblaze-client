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

This library also ships a command that watches the wire for you.  `pb snoop`
decodes the websocket conversation with a Pixelblaze, every request and
response in both directions, one JSON object per line; `pb snoop --udp`
decodes the UDP:1889 discovery beacons instead (and `--sensor` narrows that to
the sensor board frames that ride the same port):

```sh
pb snoop                  # websocket traffic to and from the resolved device
pb snoop --udp            # discovery beacons on UDP:1889
pb snoop --dry-run        # print the pipeline it would run, and exit
```

Under the hood it is the same two tools you would reach for by hand:
[tshark](https://tshark.dev/) (comes with [Wireshark](https://www.wireshark.org/),
both available with brew install) captures and dissects, and
[jq](https://jqlang.org/) filters and renders, so the output composes with the
rest of your shell.  Nothing is decoded in Python; `pb snoop`'s job is to build
a correct pipeline and then get out of the way.  See
[Snooping the wire](snooping.md) for installation, capture permissions, what a
switched network does and does not let you observe, and the full option list.

To drive the two directly, `--dry-run` prints the exact pipeline for whatever
you asked for.  The short hand-rolled version, for a single device, looks like
this (`en0` is often your computer's WiFi interface):

```sh
sudo tshark -i en0 -ql -d tcp.port==81,http \
    -T fields -e websocket.payload.text \
    -Y "(ip.dst == 192.168.4.1 or ip.src == 192.168.4.1) and websocket" \
    | jq --unbuffered -c .
```

Two things to know about that command: it decodes only if the websocket
handshake happens *after* tshark starts, since that is what primes the
dissector (`pb snoop --midstream` is the way to attach to a connection that is
already open); and when one TCP packet carries several websocket frames,
`-T fields` joins them with a comma into something that is no longer valid
JSON and jq will stop on it.  `pb snoop` uses `-T ek` for that reason.

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

Pixelblaze refers to its patterns using an alphanumeric ID code which remains constant for the lifetime of a pattern.  Patterns also have a human-readable name which is displayed in the webUI pattern list and pattern editor, but this can be changed by the user so it is not supported by the Pixelblaze API.

To find the ID of the patterns on the Pixelblaze, use the `getPatternList()` method which returns a dictionary where the key is the patternId and the value is the patternName:

```
    # Get the pattern list.
    patterns = pb.getPatternList()

    # Select first element of the first tuple in the list.
    patternId = patterns[0].key

    # Or search for a pattern by name.
    patternId = dict((value, key) for key, value in patterns.items()).get("patternName")
```

And finally, pass the patternId to the `setActivePattern()` method:
```
    # Ask the Pixelblaze to display this pattern.
    pb.setActivePattern(patternId)
```

## How to change the parameters of the pattern that is currently playing?

Pixelblaze patterns can, if so designed, be modified at runtime in two ways.

Patterns can contain user interface elements such as sliders, color pickers or input numbers that allow a user of the Pixelblaze webUI to adjust the pattern.  The values of the UI controls for the pattern currently playing can be read with the `getActiveControls()` method (which returns a dictionary containing all the controls); then new values for one or all of the controls can be modified and sent back to the Pixelblaze with the `setActiveControls()` method.

Patterns can also export variables that can be accessed and modified by external clients. The values of the variables for the pattern currently playing can be read with the `getActiveVariables()` method (which returns a dictionary containing all the variables); then new values for one or all of the variables can be modified and sent back to the Pixelblaze with the `setActiveVariables()` method.
