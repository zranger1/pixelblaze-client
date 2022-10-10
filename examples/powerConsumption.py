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
    args = parser.parse_args()

    # Connect to the Pixelblaze.
    pb = Pixelblaze(args.ipAddress)

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
    theoreticalMax = cpu + (pixelCount * (powR + powG + powB))
    print(f"Theoretical max power for {pixelCount} pixels is {theoreticalMax}A.")

    # Get the local scaling factors.
    max = pb.getBrightnessLimit(config) / 100
    scale = pb.getBrightnessSlider(config)
    print(f"Max power is {int(100 * max)}% and UI slider is {int(100 * scale)}%, so the scaled max power draw should be {theoreticalMax * max * scale}A.")

    # Loop until the heat death of the universe, or until the user hits Ctrl-C.
    try:
        # Tell the Pixelblaze to send pattern previews.
        pb.setSendPreviewFrames(True)
        while True:

            # Fetch and total a row of pixels.
            totalR = totalG = totalB = 0
            line = pb.getPreviewFrame()
            if line is None:
                # If there's a timeout, re-enable pattern previews.
                pb.setSendPreviewFrames(True)
            else:
                for index in range(0, len(line), 3):
                    totalR += powR * max * scale * (line[index + 0] / 255)
                    totalG += powG * max * scale * (line[index + 1] / 255)
                    totalB += powB * max * scale * (line[index + 2] / 255)

                # Print the totals.
                print(f"Instantaneous current draw: {cpu + totalR + totalG + totalB:.3f}A (PB={cpu:.3f}, R={totalR:.3f}, G={totalG:.3f}, B={totalB:.3f})\r", end='')

    except KeyboardInterrupt:
        print()
