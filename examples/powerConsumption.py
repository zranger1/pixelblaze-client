#!/usr/bin/env python3
import argparse
from ast import Pass
# Pixelblaze client library
from pixelblaze import *

# ------------------------------------------------

# Main routine for invoking directly.
if __name__ == "__main__":

    # Create the top-level parser.
    parser = argparse.ArgumentParser(prog='powerConsumption')
    parser.add_argument("--ipAddress", required=True, help="The IP address of the Pixelblaze to monitor")
    parser.add_argument("--proxyUrl", default=None, help="Redirect Pixelblaze traffic through a proxy at 'protocol://address:port'")
    args = parser.parse_args()

    # Connect to the Pixelblaze.
    pb = Pixelblaze(args.ipAddress, proxyUrl=args.proxyUrl)

    # Make some assumptions based the configuration...Or don't; this is only an example.
    config = pb.getConfigSettings()

    # CPU power consumption -- slight difference between v2 and v3?
    cpu = 0.080

    # The different LED types have different power consumption.
    ledType = pb.getLedType(config)
    powR = powG = powB = 0.020
    print(f"Assuming {cpu:.3f}A for the Pixelblaze itself, and {powR:.3f}A for Red, {powG:.3f}A for Green and {powB:.3f}A for Blue LEDs.")
    pixelCount = pb.getPixelCount(config)

    # The above determine the maximum power draw, which is subject to local settings.
    print(f"Theoretical max power for {pixelCount} pixels is {cpu + (pixelCount * (powR + powG + powB))}A.")

    # Get the local scaling factors.
    max = pb.getBrightnessLimit(config) / 100
    scale = pb.getBrightnessSlider(config)
    print(f"Max power is {int(100 * max)}%; UI slider is {int(100 * scale)}%.")

    # Loop until the heat death of the universe, or until the user hits Ctrl-C.
    try:
<<<<<<< HEAD
        # Tell the Pixelblaze to send pattern previews.
        pb.setSendPreviewFrames(True)
=======
>>>>>>> 13b86e61fc8deef29d4564f9eeee414a2a5d57de
        while True:

            # Fetch and total a row of pixels.
            totalR = totalG = totalB = 0
            line = pb.getPreviewFrame()
            if line is None:
<<<<<<< HEAD
                # If there's a timeout, re-enable pattern previews.
=======
>>>>>>> 13b86e61fc8deef29d4564f9eeee414a2a5d57de
                pb.setSendPreviewFrames(True)
            else:
                for index in range(0, len(line), 3):
                    totalR += powR * max * scale * (line[index + 0] / 255)
                    totalG += powG * max * scale * (line[index + 1] / 255)
                    totalB += powB * max * scale * (line[index + 2] / 255)

                # Print the totals.
                print(f"Instantaneous current draw: {cpu + totalR + totalG + totalB:.3f}A (PB={cpu:.3f}, R={totalR:.3f}, G={totalG:.3f}, B={totalB:.3f})\r", end='')
    
    except KeyboardInterrupt:
<<<<<<< HEAD
        print()
=======
        print()
>>>>>>> 13b86e61fc8deef29d4564f9eeee414a2a5d57de
