#!/usr/bin/env python3
from pixelblaze import *

# ------------------------------------------------

# Main routine for invoking directly.
if __name__ == "__main__":
    print("Finding Pixelblazes...")
    # Enumerate the available Pixelblazes on the network.
    for ipAddress in Pixelblaze.EnumerateAddresses(timeout=1500):
        with Pixelblaze(ipAddress) as pixelblaze:
            print(f"    at {ipAddress} found '{pixelblaze.getConfigSettings()}'")
