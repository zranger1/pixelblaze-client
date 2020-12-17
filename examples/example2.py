#!/usr/bin/env python3
"""
 example2.py

 Example/Testbed for pyblaze's PixelblazeEnumerator class.
 Just loops and periodically displays available pixelblazes on the LAN/
 
 Requires Python 3 and the websocket-client module.
 
 Copyright 2020 JEM (ZRanger1)

 Permission is hereby granted, free of charge, to any person obtaining a copy of this
 software and associated documentation files (the "Software"), to deal in the Software
 without restriction, including without limitation the rights to use, copy, modify, merge,
 publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
 to whom the Software is furnished to do so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in all copies or
 substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
 BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
 AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
 CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
 ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 THE SOFTWARE.

 Version  Date         Author         Comment
 v0.9.0   12/06/2020   (JEM)ZRanger1  Created
"""
from pixelblaze import *
           
# stay a while, and listen...
if __name__ == "__main__":
    print("Starting PixelblazeEnumerator")
    print("...listening for 5 seconds....")
    s = PixelblazeEnumerator()   # create the enumerator object
    s.setDeviceTimeout(10000)    # shorten timeout for test purposes -- default is 30s
#    s.enableTimesync()           #uncomment to test time synchronization
    
    # loop forever, print out the list of Pixelblazes on the net every 5 seconds
    try:
        while True:
            for i in range(5):                     
                print('.', end='')    
                time.sleep(1)
            print("")    
            print(time.strftime("%H:%M:%S",time.localtime()),"- Pixelblazes",s.getPixelblazeList())                        
                    
    except KeyboardInterrupt:
        s.stop()
        print("--AAAAAAAH!   Time to Stop--")
        
    except Exception as blarf:
        s.stop()
        print(blarf)          



