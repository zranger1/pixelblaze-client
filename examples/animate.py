#!/usr/bin/env python3
import argparse
from PIL import Image, ImageSequence
from pixelblaze import *

if __name__ == "__main__":

    # Create the top-level parser.
    parser = argparse.ArgumentParser(prog='animate')
    parser.add_argument("--ipAddress", required=True, help="The IP address of the Pixelblaze")
    parser.add_argument("--fileName", required=True, help="The animated GIF/PNG file to be sent to the Pixelblaze")
    # Parse the command line.
    args = parser.parse_args()

    # Open the image file and analyze it.
    with Image.open(args.fileName, mode='r') as im:
        print(f"Image is {im.width}x{im.height} pixels, with {im.n_frames} frames.")

        # Connect to the Pixelblaze.
        with Pixelblaze(args.ipAddress) as pb:
            # Query the pixelcount of the Pixelblaze.
            pixelCount = pb.getPixelCount()
            frameSize = int(math.sqrt(pixelCount))
            print(f"Pixelblaze has {pixelCount} pixels; assuming a square matrix of {frameSize}x{frameSize} pixels.")

            # Download the bytecode of a listener pattern that receives and displays the frames:
            #
            #    //  A buffer to contain the received pixels.
            #    export var pixels = array(pixelCount);
            #    export var frameNumber = -1;
            #
            #    //  Working storage to split out the frame components.
            #    var _r = array(pixelCount), _g = array(pixelCount), _b = array(pixelCount);
            #
            #    // A render function to display the received pixels.
            #    var currentFrame = -1;
            #    export function beforeRender(delta) {
            #        //  Wait until it's time to display the next frame.
            #        if (currentFrame == frameNumber) return;
            #        currentFrame = frameNumber;
            #        //  Break apart the frame buffer into its RGB components.
            #        pixels.forEach((v, i, a) => { 
            #            _r[i] = (v >> 8) & 0xff; _g[i] = v & 0xff;  _b[i] = (v << 8) & 0xff; 
            #        });
            #    }
            #
            #    var matrixWidth = sqrt(pixelCount);
            #    export function render2D(index, x, y) {
            #        var offset = trunc((trunc(y * matrixWidth) + x) * matrixWidth);
            #        rgb(_r[offset] / 255, _g[offset] / 255, _b[offset] / 255);
            #    }
            #
            # The bytecode was extracted from a Pixelblaze Binary Pattern, downloaded 
            # and exploded into its constituent parts using the PBP class.
            patternBytecode = bytes(bytearray.fromhex('A0010000390000000B0000002B01000017010100290100000000FFFF17010200290100000B0000002B01000017010300290100000B0000002B01000017010400290100000B0000002B01000017010500290100000000FFFF17010600290100007800000017010700290100000B00000071010000170108002901000094000000170109002901000001000000090000030D00FDFF00000800470200000000FF003F0200000B0003000D00FEFF55030000290100000D00FDFF0000FF003F0200000B0004000D00FEFF55030000290100000D00FDFF00000800450200000000FF003F0200000B0005000D00FEFF550300002901000005000000090000010B0006000B000200510200001B014200050000000B00020017010600290100000B000100420000008D0200002901000005000000090001030D00FFFF0B00080039020000890100000D00FEFF350200000B000800390200008901000019010200290100000B0003000D000200330200000000FF003B0200000B0004000D000200330200000000FF003B0200000B0005000D000200330200000000FF003B0200007D030900290100000500000001000000706978656C7300020000006672616D654E756D62657200070000006265666F726552656E646572000900000072656E646572324400'))
            print("Downloading pixel proxy pattern.")
            pb.sendPatternToRenderer(patternBytecode, {})

            # Set an exception handler to catch [Ctrl-C].
            try:
                print("Rendering frames...press [Ctrl]-[C] to exit.")
                # Loop through the image frames.
                while True:
                    frameNumber = 0
                    for frame in ImageSequence.Iterator(im):
                        frameNumber = frameNumber + 1
                        # Convert the image into an RGB sequence (i.e. remove the GIF palette).
                        convertedFrame = frame.convert(mode='RGB')
                        # Rescale this frame to match the Pixelblaze's dimensions.
                        resizedFrame = convertedFrame.resize((frameSize, frameSize), resample=Image.Resampling.NEAREST)
                        # Pack the RGB tuples into longwords.
                        packed = []
                        tupNum = 0
                        for tup in list(resizedFrame.getdata()):
                            r = tup[0]
                            g = tup[1]
                            b = tup[2]
                            longWord = ((r << 24) | (g << 16) | (b << 8)) / 65536
                            if longWord > 32767: longWord -= 65536
                            packed.append(longWord)
                            tupNum += 1
                        # Set the pattern variables to the (R, G, B) values specified.
                        pb.setActiveVariables({"frameNumber": frameNumber, "pixels": packed})
                        time.sleep(0.04)
            except KeyboardInterrupt:
                # Clear the frame and exit.
                clearFrame = []
                for pixel in range(pixelCount): clearFrame.append(0)
                pb.setActiveVariables({"frameNumber": -1, "pixels": clearFrame})
                print("")
