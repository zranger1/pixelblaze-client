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

    # Connect to the Pixelblaze and download the bytecode of a pattern 
    # ("export var r, g, b; export function render() { rgb(r, g, b); }")
    # that sets all the LEDs on the string to a single RGB color.
    # The bytecode was extracted from a Pixelblaze Binary Pattern, 
    # downloaded and exploded into its constituent parts using the PBP class.
    patternBytecode = bytes(bytearray.fromhex('2C0000001D00000008000000170104002901000001000000090000000B0001000B0002000B0003007D03090029010000050000000100000072000200000067000300000062000400000072656E64657200'))
    with Pixelblaze(args.ipAddress) as pb:
        pb.sendPatternToRenderer(patternBytecode, {})
        # Set the pattern variables to the (R, G, B) values specified.
        pb.setActiveVariables({"r": args.r, "g": args.g, "b": args.b})
