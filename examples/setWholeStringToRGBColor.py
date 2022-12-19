#!/usr/bin/env python3
import argparse
from pixelblaze import *

if __name__ == "__main__":

    # Create the top-level parser.
    parser = argparse.ArgumentParser(prog='pbbTool')
    parser.add_argument("--ipAddress", required=True, help="The IP address of the Pixelblaze")
    parser.add_argument("--r", required=True, help="The Red value (0..1) to be sent to the Pixelblaze")
    parser.add_argument("--g", required=True, help="The Green value (0..1) to be sent to the Pixelblaze")
    parser.add_argument("--b", required=True, help="The Blue value (0..1) to be sent to the Pixelblaze")
    # Parse the command line.
    args = parser.parse_args()

    # Connect to the Pixelblaze and download a pattern that sets all the LEDs on the string to a single RGB color.
    with Pixelblaze(args.ipAddress) as pb:
        patternBytecode = pb.compilePattern("export var r, g, b; export function render() { rgb(r, g, b); }")
        pb.sendPatternToRenderer(patternBytecode, {})
        # Set the pattern variables to the (R, G, B) values specified.
        pb.setActiveVariables({"r": args.r, "g": args.g, "b": args.b})
