#!/usr/bin/env python3
"""
 example.py

 Example/Testbed for pyblaze - a library that presents a simple, synchronous interface
 for communicating with and controlling Pixelblaze LED controllers.
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

 Version  Date         Author Comment
 v0.0.1   11/23/2020   JEM(ZRanger1)    Created
 v0.0.2   12/01/2020   "                Updated for name change
 v0.0.3   12/02/2020   "                added support for multiple color controls per pattern
 v0.9.0   12/06/2020   "                simple tests for PixelblazeEnumerator class
 v0.9.1   12/07/2020   "                fixes to time synchronization API
"""
from pixelblaze import *

if __name__ == "__main__":
    # When testing, change these pattern, variable and control names as necessary for
    # your Pixelblaze.
    pixelblazeIP = "192.168.1.15"     # insert your own IP address here
    basicPatternName = "KITT"         # everybody has KITT!
    vartestPatternName = "Bouncer3D"  # a pattern with exported variables
    controlPatternName1 = "Bouncer3D" # a pattern with UI controls
    testControlName = "sliderSpeed"   # name of control in controlPatternName    
    controlPatternName2 = "Many Controls"  # a pattern with color pickers
    
    # create a PixelblazeEnumerator object, listen for a couple of seconds, then
    # list the Pixelblazes we found.
    pbList = PixelblazeEnumerator()
    print("Testing: PixelblazeEnumerator object created -- listening for Pixelblazes")
    time.sleep(2)
    print("Available Pixelblazes: ", pbList.getPixelblazeList())        
    
    # create a Pixelblaze object.
    pb = Pixelblaze(pixelblazeIP)   # use your own IP address here
    pb.stopSequencer()              # make sure the sequencer isn't running    
    print("Testing: Pixelblaze object created,connected,ready!")
      
    # Run through various calls to make sure we have basic functionality     
    print("Testing: getPatternList")
    result = pb.getPatternList()
    for key, value in result.items():
        print(key, ' : ', value)
    time.sleep(1)
    
    print("Testing: setActivePattern")
    pb.setActivePattern("*OBVIOUSLY BOGUS PATTERN*")  # just to make sure nothing bad happens
    pb.setActivePattern(basicPatternName)
    pb.waitForEmptyQueue(1000)
    time.sleep(1)
    
    print("Testing: getVars")
    pb.setActivePattern(vartestPatternName) 
    pb.waitForEmptyQueue(1000)       
    print("Variables: ",pb.getVars())
    time.sleep(1)    
           
    print("Testing: setBrightness")
    pb.setActivePattern(basicPatternName)
    pb.waitForEmptyQueue(1000)    
    time.sleep(0.2)
    for i in range(4):
        print('.', end='')
        pb.setBrightness(0)
        time.sleep(1)
        print('.', end='')        
        pb.setBrightness(1)
        time.sleep(1)
    print("")        
         
    print("Testing: Internal Sequencer Control")
    print("Should change patterns every two seconds")
    pb.setSequenceTimer(2)
    pb.startSequencer()
    for i in range(6):
        print('.', end='')    
        time.sleep(1)
    print("")
    pb.stopSequencer()
    time.sleep(1) 
    
    print("Testing: getHardwareConfig")
    result = pb.getHardwareConfig()
    for key, value in result.items():
        print(key, ' : ', value)
    time.sleep(1)
    
    print("Testing: getControls")
    pb.setActivePattern(controlPatternName1)   
    pb.waitForEmptyQueue(1000)    
    result = pb.getControls(controlPatternName1) 
    val = result[testControlName]    
    print("Controls: ",result)
    
    
    print("Testing Color Picker Methods")
    time.sleep(1)
    pb.setActivePattern(controlPatternName2)    
    print("Empty Control List: ", pb.getColorControlNames("KITT"))
    print("Control Name List: ",pb.getColorControlNames())
    print("First Color Control: ",pb.getColorControlName()) 
    time.sleep(1)      

# we don't test persistence, so you have to look at the pattern to see the result
    print("Testing: setControls")
                
    pb.setActivePattern(controlPatternName1)  # switch to control test pattern 
    time.sleep(2)                             # display with original control setting
    pb.setControl(testControlName,1,False)    # set control value to max
    for i in range(5):                        # display this way for a while
        print('.', end='')    
        time.sleep(1)
    print("")
    pb.setControl(testControlName,val,False); # restore previous setting
    time.sleep(2)
    
    pb.setActivePattern(basicPatternName) # Set pattern back to something reasonable
    
    # and fetch list of Pixelblazes one last time!
    print("Testing: Available Pixelblazes: ", pbList.getPixelblazeList())            

    pb.close()
    print("Testing: Complete!")
        
        
        
        