"""
 pixelblaze.py

 A library that presents a simple, synchronous interface for communicating with and
 controlling a Pixelblaze LED controller.  Requires Python 3 and the websocket-client
 module.

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
 v0.0.1   11/20/2020   JEM(ZRanger1)    Created
 v0.0.2   12/1/2020    JEM(ZRanger1)    Name change + color control methods
"""
import websocket
import socket
import json

class Pixelblaze:
    ws = None
    connected = False
    flash_save_enabled = False
    default_recv_timeout = 1
    ipAddr = None
    
    def __init__(self, addr):
        """
        Create and open Pixelblaze object. Takes the Pixelblaze's IPv4 address in the
        usual 12 digit numeric form (for example, 192.168.1.xxx) 
        """
        self.open(addr)

    def open(self, addr):
        """
        Open websocket connection to given ip address.  Called automatically
        when a Pixelblaze object is created - it is not necessary to
        explicitly call open to connect unless the websocket has been closed by the
        user or by the Pixelblaze.
        """
        if (self.connected is False):
            uri = "ws://"+addr+":81"
            self.ws = websocket.create_connection(uri,sockopt=((socket.SOL_SOCKET, socket.SO_REUSEADDR,1),
                                                               (socket.IPPROTO_TCP, socket.TCP_NODELAY,1),))
            self.ws.settimeout(self.default_recv_timeout)
            self.ipAddr = addr
            self.connected = True

    def close(self):
        """Close websocket connection"""
        if (self.connected is True):
            self.ws.close()
            self.connected = False
            
    def __boolean_to_json_string(self, val):
        """Utility method: Converts Python True/False to JSON true/false"""
        return ',"save":true' if (val is True) else ""
    
    def __get_save_string(self, val):
        """
        Utilty method: Returns a string that can be used by methods which
        can optionally save data to flash memory.  Always returns "false" if
        _enable_flash_save() has not been called on the Pixelblaze object. Otherwise
        returns a string reflecting the value of the boolean <val> argument.
        """
        val = val if (self.flash_save_enabled is True) else False
        return self.__boolean_to_json_string(val)
            
    def _enable_flash_save(self):
        """
        IMPORTANT SAFETY TIP:
           To preserve your Pixelblaze's flash memory, which can wear out after a number of
           cycles, you must call this method before using setControls() with the
           saveFlash parameter set to True.
           If this method is not called, setControls() will ignore the saveFlash parameter
           and will not save settings to flash memory.
        """
        self.flash_save_enabled = True
        
    def ws_flush(self):
        """
        Utility method: drain websocket receive buffers. Called to clear out unexpected
        packets before sending requests for data w/send_string(). We do not call it
        before simply sending commands because it has a small performance cost.
        
        This is one of the treacherously "clever" things done to make pyblaze
        work as a synchronous API when the Pixelblaze may be sending out unexpected
        packets or talking to multiple devices.  We do some extra work to make sure
        we're only receiving the packets we want.
        """
        
        self.ws.settimeout(0.1)  # set very short timeout
        
        try:
            while (True):
                self.ws.recv()
        except websocket._exceptions.WebSocketTimeoutException:
            self.ws.settimeout(self.default_recv_timeout)  # restore normal timeout
            return   # if we get a timeout, there are no more pending packets

    def ws_recv(self, wantBinary = False):
        """
        Utility method: Blocking websocket receive that waits for a packet of a given type
        and gracefully handles errors and stray extra packets. 
        """
        result = None
        try:
            while (True):  # loop until we hit timeout or have the packet we want
                result = self.ws.recv()
                if ((wantBinary is False) and (type(result) is str)):  # JSON string
                    break
                elif ((wantBinary is True) and (result[0] == 0x07)):  # binary pattern list packet
                    break
                else:
                    result = None          # unhandled binary - ignore
                    
        except websocket._exceptions.WebSocketTimeoutException:
            return None                # timeout -- we can just ignore this
            
        except websocket._exceptions.WebSocketConnectionClosedException:
            self.connected = False
            raise                      
        
        return result            
   
    def send_string(self, cmd):
        """Utility method: Send string-ized JSON to the pixelblaze"""    
        self.ws.send(cmd.encode("utf-8"))
        
    def waitForEmptyQueue(self,timeout_ms=1000):
        """
        Wait until the Pixelblaze's websocket message queue is empty, or until
        timeout_ms milliseconds have elapsed.  Returns True if an empty queue
        acknowldgement was received, False if timeout or error occurs.
        """
        self.ws_flush()
        self.ws.settimeout(timeout_ms / 1000)
        self.send_string('{"ping": true}')
        result = self.ws.recv()        
        self.ws.settimeout(self.default_recv_timeout)
        
        return True if ((result is not None) and (result.startswith('{"ack"'))) else False                
        
    def getVars(self):
        """Returns JSON object containing all vars exported from the active pattern"""
        self.ws_flush()  # make sure there are no pending packets    
        self.send_string('{"getVars": true}')
        return json.loads(self.ws.recv()).get('vars')
    
    def setVars(self, json_vars):
        """
        Sets pattern variables contained in the json_vars (JSON object) argument.
        Does not check to see if the variables are exported by the current active pattern.
        """
        jstr = json.dumps(json_vars)
        self.send_string('{"setVars" : '+jstr+"}")
        
    def setVariable(self, var_name, value):
        """
        Sets a single variable to the specified value. Does not check to see if the
        variable is actually exported by the current active pattern.
        """
        val = {var_name : value }
        self.setVars(val)
        
    def variableExists(self, var_name):
        """
        Returns True if the specified variable exists in the active pattern,
        False otherwise.
        """
        val = self.getVars()
        if (val is None):
            return False
        
        return True if var_name in val else False
               
    def _id_from_name(self, patterns, name):
        """Utility Method: Given the list of patterns and text name of a pattern, returns that pattern's ID"""
        for key, value in patterns.items(): 
            if name == value: 
                return key 
        return None
       
    # takes either name or id, returns valid id    
    def _get_pattern_id(self, pid):
        """Utility Method: Returns a pattern ID if passed either a valid ID or a text name"""
        patterns = self.getPatternList()
        
        if (patterns.get(pid) is None):
            pid = self._id_from_name(patterns, pid)
        
        return pid
    
    def setActivePatternId(self,pid):
        """
        Sets the active pattern by pattern ID, without the name lookup option
        supported by setActivePattern().  This method is faster and more
        network efficient than SetActivePattern() if you already know a
        pattern's ID.
        
        It does not validate the input id, or determine if the pattern is
        available on the Pixelblaze.
        """
        self.send_string('{"activeProgramId" : "%s"}'%pid)
        
        
    def setActivePattern(self, pid):
        """Sets the currently running pattern, using either an ID or a text name"""
        p = self._get_pattern_id(pid)
            
        if (p is not None):
            self.setActivePatternId(p)
            
    def getActivePattern(self):
        """
        Returns the ID the pattern currently running on
        the Pixelblaze if available.  Otherwise returns an empty dictionary
        object
        """
        hw = self.getHardwareConfig()      
        try:
            return hw['activeProgram']['activeProgramId']
        except:
            return {}
         
    def setBrightness(self, n):
        """Set the Pixelblaze's global brightness.  Valid range is 0-1"""
        n = max(0, min(n, 1))  # clamp to proper 0-1 range
        self.send_string('{"brightness" : %f}'%n)
                                
    def setSequenceTimer(self, n):
        """
        Sets number of milliseconds the Pixelblaze's sequencer will run each pattern
        before switching to the next.
        """
        self.send_string('{"sequenceTimer" : %d}'%n)
        
    def startSequencer(self):
        """Enable and start the Pixelblaze's internal sequencer"""
        self.send_string('{"sequencerEnable": true, "runSequencer" : true }')
        
    def stopSequencer(self):
        """Stop and disable the Pixelblaze's internal sequencer"""
        self.send_string('{"sequencerEnable": false, "runSequencer" : false }')
        
    def getHardwareConfig(self):
        """Returns a JSON object containing all the available hardware configuration data"""
        self.ws_flush()  # make sure there are no pending packets    
        self.send_string('{"getConfig": true}')
        hw = dict()
        
        p1 = self.ws_recv()
        while (p1 is not None):
            p2 = json.loads(p1)
            hw = {**hw, **p2}
            p1 = self.ws_recv()                        
        
        return hw
    
    def _get_current_controls(self):
        """
        Utility Method: Returns controls for currently running pattern if
        available, None otherwise
        """
        ctl = self.getHardwareConfig()  
        if ctl is None:
            return None
        
# retrieve control settings for active pattern from hardware config        
        ctl = ctl.get('activeProgram').get('controls') 
        return ctl

    
    def getControls(self, pattern = None):      
        """
        Returns a JSON object containing the state of all the specified
        pattern's UI controls. If the pattern argument is not specified,
        returns the controls for the currently active pattern if available.
        Returns empty object if the pattern has no UI controls, None if
        the pattern id is not valid or is not available.
        (Note that getActivePattern() can return None on a freshly started
        Pixelblaze until the pattern has been explicitly set.)
        """
        # if pattern is not specified, attempt to get controls for active pattern
        # from hardware config
        if pattern is None:
            return self._get_current_controls()
            
        # if pattern name or id was specified, attempt to validate against pattern list
        # and get stored values for that program
        else:
            pattern = self._get_pattern_id(pattern)           
            if (pattern is None):
                return None
        
            self.send_string('{"getControls": "%s"}'%pattern)
            ctl = json.loads(self.ws.recv())
                
        # extract controls and their values
        if (len(ctl.get('controls')) > 0):
            x = next(iter(ctl['controls']))
            return ctl['controls'][x]
        else:
            return {}
    
    def setControls(self, json_ctl, saveFlash = False):
        """
        Sets UI controls in the active pattern to values contained in
        the JSON object in argument json_ctl. To reduce wear on
        Pixelblaze's flash memory, the saveFlash parameter is ignored
        by default.  See documentation for _enable_flash_save() for
        more information.
        """
        saveStr = self.__get_save_string(saveFlash)
        jstr = json.dumps(json_ctl)
        self.send_string('{"setControls": %s %s}'%(jstr,saveStr))
        
    def setControl(self, ctl_name, value, saveFlash = False):
        """
        Sets the value of a single UI controls in the active pattern.
        to values contained in in argument json_ctl. To reduce wear on
        Pixelblaze's flash memory, the saveFlash parameter is ignored
        by default.  See documentation for _enable_flash_save() for
        more information.
        """       
        val = {ctl_name : max(0, min(value, 1))}  # clamp value to proper 0-1 range 
        self.setControls(val,saveFlash)
        
    def setColorControl(self, ctl_name, color, saveFlash = False):
        """
        Sets the 3-element color of the specified HSV or RGB color picker.
        The color argument should contain an RGB or HSV color with all values
        in the range 0-1. To reduce wear on Pixelblaze's flash memory, the saveFlash parameter
        is ignored by default.  See documentation for _enable_flash_save() for
        more information.
        """
        
        # based on testing w/Pixelblaze, no run-time length or range validation is performed
        # on color. Pixelblaze ignores extra elements, sets unspecified elements to zero,
        # takes only the fractional part of elements outside the range 0-1, and
        # does something (1-(n % 1)) for negative elements.
        val = {ctl_name : color}
        self.setControls(val,saveFlash)
        
    def controlExists(self,ctl_name,pattern = None):
        """
        Returns True if the specified control exists, False otherwise.
        The pattern argument takes the name or ID of the pattern to check.
        If pattern argument is not specified, checks the currently running pattern.
        Note that getActivePattern() can return None on a freshly started
        Pixelblaze until the pattern has been explicitly set.  This function
        also will return False if the active pattern is not available.
        """            
        result = self.getControls(pattern)
        return True if ctl_name in result else False
    
    def getColorControlName(self, pattern = None):
        """
        Returns the name of the specified pattern's rgbPicker or hsvPicker control
        if it exists, None otherwise.  If the pattern argument is not specified,
        checks in the currently running pattern
        """
        controls = self.getControls(pattern)
        if (controls is None):
            return None
        
        # check for hsvPicker        
        result = dict(filter(lambda ctl: "hsvPicker" in ctl[0], controls.items()))
        
        # check for rgbPicker if we didn't find an hsvPicker
        if (len(result) == 0):
            result = dict(filter(lambda ctl: "rgbPicker" in ctl[0], controls.items()))
            
        return list(result.keys())[0] if (len(result) > 0) else None        
        
    def setDataspeed(self, speed, saveFlash = False):
        """
        Sets custom bit timing for WS2812-type LEDs.
        CAUTION: For advanced users only.  If you don't know
        exactly why you want to do this, DON'T DO IT.
        
        See discussion in this thread on the Pixelblaze forum:
        https://forum.electromage.com/t/timing-of-a-cheap-strand/739
        
        Note that you must call _enable_flash_save() in order to use
        the saveFlash parameter to make your new timing (semi) permanent.
        """
        saveStr = self.__get_save_string(saveFlash)
        self.send_string('{"dataSpeed" : %d %s}'%(speed,saveStr))       
    
    def getPatternList(self):
        """
        Returns a dictionary containing the unique ID and the text name of all
        saved patterns on the Pixelblaze
        """
        patterns = dict()
        self.ws_flush()  # make sure there are no pending packets    
        self.send_string("{ \"listPrograms\" : true }")
        
        frame = self.ws_recv(True)
        while (frame is not None):
            listFrame = frame[2:].decode("utf-8")
            listFrame = listFrame.split("\n")
            listFrame = [m.split("\t") for m in listFrame]
               
            for pat in listFrame:
                if (len(pat) == 2):
                    patterns[pat[0]] = pat[1]
               
            if (frame[1] & 0x04):
                break
            frame = self.ws_recv(True)

        return patterns
                      
