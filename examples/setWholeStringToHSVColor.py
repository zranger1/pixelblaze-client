#!/usr/bin/env python3
import argparse
from pixelblaze import *

if __name__ == "__main__":

    # Create the top-level parser.
    parser = argparse.ArgumentParser(prog='pbbTool')
    parser.add_argument("--ipAddress", required=True, help="The IP address of the Pixelblaze")
    parser.add_argument("--hue", required=True, help="The Hue value to be sent to the Pixelblaze")
    parser.add_argument("--saturation", required=True, help="The Saturation value to be sent to the Pixelblaze")
    parser.add_argument("--value", required=True, help="The Value (a/k/a Brightness) value to be sent to the Pixelblaze")
    # Parse the command line.
    args = parser.parse_args()

    # Connect to the Pixelblaze and download the bytecode of a pattern 
    # ("var h, s, v; export function hsvPickerHSV(_h, _s, _v) { h = _h; s = _s; v = _v; } export function render() { hsv(h, s, v); }")
    # that sets all the LEDs on the string to a single HSV color.
    # The bytecode was extracted from a Pixelblaze Binary Pattern, 
    # downloaded and exploded into its constituent parts using the PBP class.
    patternBytecode = bytes(bytearray.fromhex('780000001C00000000000000170105001701040017010100290100001800000017010200290100002E000000170103002901000001000000090000030D00FDFF17010100290100000D00FEFF17010400290100000D00FFFF170105002901000005000000090000000B0001000B0004000B0005007D0300002901000005000000020000006873765069636B6572485356000300000072656E64657200'))
    with Pixelblaze(args.ipAddress) as pb:
        # Send the pattern and set the color picker to the (Hue, Saturation, Value) specified.
        pb.sendPatternToRenderer(patternBytecode, {"hsvPickerHSV": [args.hue, args.saturation, args.value]})
