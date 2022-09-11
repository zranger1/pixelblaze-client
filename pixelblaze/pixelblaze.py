#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
 pixelblaze.py

 A library that presents a simple, synchronous interface for communicating with and
 controlling Pixelblaze LED controllers.  Requires Python 3 and the websocket-client
 module.

 Copyright 2020-2022 JEM (ZRanger1)

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
 v0.0.1   11/20/2020   JEM(ZRanger1)  Created
 v0.0.2   12/1/2020    "              Name change + color control methods
 v0.9.0   12/6/2020    "              Added PixelblazeEnumerator class
 v0.9.1   12/16/2020   "              Support for pypi upload
 v0.9.2   01/16/2021   "              Updated Pixelblaze sequencer support
 v0.9.3   04/13/2021   "              waitForEmptyQueue() return now agrees w/docs
 v0.9.4   02/04/2022   "              Added setPixelcount(),pause(), unpause(), pattern cache
 v0.9.5   07/16/2022   @pixie         Update ws_recv to receive long preview packets
 v0.9.6   07/17/2022   @pixie         Tweak getPatternList() to handle slower Pixelblazes
 v1.9.7   01/09/2022   @pixie         large-scale refactoring to add new features; minor loss of compatibility
"""

import websocket
import socket
import json
import base64
import time
import struct
import threading
import requests
import pytz
import math
import pathlib
from re import T
from urllib.parse import urlparse, urljoin
from enum import Enum, Flag, IntEnum

__version__ = "1.9.7"

class Pixelblaze:
    """
    Presents a synchronous interface to a Pixelblaze's websocket API. The constructor takes
    the Pixelblaze's IPv4 address in the usual 12 digit numeric form (192.168.1.xxx)
    and if successful, returns a connected Pixelblaze object.

    To control multiple Pixelblazes, create multiple objects.
    """

    # --- PRIVATE DATA
    default_recv_timeout = 1
    ws = None
    connected = False
    ipAddress = None
    proxyUrl = None
    proxyDict = None

    # Pattern cache
    cacheRefreshTime = 0
    cacheRefreshInterval = 1000 # milliseconds used internally
    patternCache = None

    # Parser state cache
    latestStats = None
    latestSequencer = None
    latestExpander = None
    latestVersion = None
    latestUpdateCheck = None

    # --- OBJECT LIFETIME MANAGEMENT (CREATION/DELETION)

    def __init__(self, addr, proxyUrl=None):
        """
        Create and open Pixelblaze object. Takes the Pixelblaze's IPv4 address in the
        usual 12 digit numeric form (for example, 192.168.1.xxx)
        """
        self.proxyUrl = proxyUrl
        if not proxyUrl is None:
            self.proxyDict = { "http": proxyUrl, "https": proxyUrl }
        self.ipAddress = addr
        self.open()
        self.setCacheRefreshTime(600)  # seconds used in public api

    def __enter__(self):
        # nothing needed, really.
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Make sure we clean up after ourselves.
        if not self is None: self.close()

    # --- STATiC METHODS
    
    # Static methods:
    @staticmethod
    def EnumerateAddresses(hostIP="0.0.0.0", timeout=5000, proxyUrl=None):
        """Returns an enumerator that will iterate through all the Pixelblazes on 
        the network, until {timeout} seconds have passed with no new devices appearing."""
        newOne = object.__new__(Pixelblaze.LightweightEnumerator)
        newOne.__init__(Pixelblaze.LightweightEnumerator.EnumeratorTypes.ipAddress, hostIP, timeout, proxyUrl)
        return newOne

    @staticmethod
    def EnumerateDevices(hostIP="0.0.0.0", timeout=5000, proxyUrl=None):
        """Returns an enumerator that will iterate through all the Pixelblazes on 
        the network, until {timeout} seconds have passed with no new devices appearing."""
        newOne = object.__new__(Pixelblaze.LightweightEnumerator)
        newOne.__init__(Pixelblaze.LightweightEnumerator.EnumeratorTypes.pixelblazeObject, hostIP, timeout, proxyUrl)
        return newOne

    # The different types of iterators:
    class LightweightEnumerator:
        """This enumerator returns each Pixelblaze found on the network."""
        # Members:
        listenSocket = None
        timeout = 0
        timeStop = 0
        seenPixelblazes = []
        enumeratorType = 0 # can't assign self.LightweightEnumerator.EnumeratorTypes.noType
        proxyUrl = None

        class EnumeratorTypes(IntEnum):
            noType = 0
            ipAddress = 1
            pixelblazeObject = 2

        # private constructor:
        def __init__(self, enumeratorType, hostIP="0.0.0.0", timeout=5000, proxyUrl=None):
            """    
            Create an interable object that listens for Pixelblaze beacon packets, returning
            a Pixelblaze object for each unique beacon seen during the timeout period.
            Listens on all available interfaces if addr is not specified.
            """
            try:
                self.enumeratorType = enumeratorType
                self.timeout = timeout
                self.proxyUrl = proxyUrl
                self.listenSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.listenSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.listenSocket.bind((hostIP, 1889))
                return True
            except socket.error as e:
                print(e)
                return False

        def __del__(self):
            """
            Stop listening for datagrams, terminate listener thread and close socket.
            """
            if self.listenSocket is not None:
                self.listenSocket.close()

        def __iter__(self):
            # Return __iter__ object.
            return self

        def __next__(self):
            """
            Return the next Pixelblaze found, until the timeout expires.
            """
            # If we receive a beacon packet from a new Pixelblaze, return an object for it.
            self.timeStop = self._time_in_millis() + self.timeout
            while self._time_in_millis() <= self.timeStop:
                data, addr = self.listenSocket.recvfrom(1024)
                pkt = struct.unpack("<LLL", data)
                if pkt[0] == 42: # beacon packet
                    if addr not in self.seenPixelblazes:
                        # Add this address to our list so we don't repeat it.
                        self.seenPixelblazes.append(addr)
                        # Return an enumerator of the appropriate type.
                        if self.enumeratorType == Pixelblaze.LightweightEnumerator.EnumeratorTypes.ipAddress:
                            return addr[0]
                        elif self.enumeratorType == Pixelblaze.LightweightEnumerator.EnumeratorTypes.pixelblazeObject:
                            newOne = object.__new__(Pixelblaze)
                            newOne.__init__(addr[0], proxyUrl=self.proxyUrl)
                            return newOne
                        else: 
                            # No such type...How did that happen?
                            raise
                
            # Exit because the timeout has expired.
            raise StopIteration

        def _time_in_millis(self):
            """
            Utility Method: Returns last 32 bits of the current time in milliseconds
            """
            return int(round(time.time() * 1000)) % 0xFFFFFFFF

    # --- CONNECTION MANAGEMENT

    def open(self):
        """
        Open websocket connection to given ip address.  Called automatically
        when a Pixelblaze object is created - it is not necessary to
        explicitly call open to connect unless the websocket has been closed by the
        user or by the Pixelblaze.
        """
        if self.connected is False:
            uri = "ws://" + self.ipAddress + ":81"
            retryCount = 0
            while True:
                try:
                    if self.proxyUrl is not None:
                        url = urlparse(self.proxyUrl)
                        self.ws = websocket.create_connection(uri, sockopt=((socket.SOL_SOCKET, socket.SO_REUSEADDR, 1), (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)), proxy_type=url.scheme, http_proxy_host=url.hostname, http_proxy_port=url.port)
                    else:
                        self.ws = websocket.create_connection(uri, sockopt=((socket.SOL_SOCKET, socket.SO_REUSEADDR, 1), (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),))
                    break
                except websocket._exceptions.WebSocketConnectionClosedException:
                    retryCount += 1
                    if retryCount >= 5:
                        raise
            self.ws.settimeout(self.default_recv_timeout)
            self.connected = True

    def close(self):
        """Close websocket connection"""
        if self.connected is True:
            self.ws.close()
            self.connected = False

    # --- LOW-LEVEL SEND/RECEIVE

    class messageTypes(IntEnum):
        """The first byte of a binary frame contains the packet type."""
        putSourceCode = 1       # from client to PB
        putByteCode = 3         # from client to PB
        previewImage = 4        # from client to PB
        previewFrame = 5        # from PB to client
        getSourceCode = 6       # from PB to client
        getProgramList = 7      # from client to PB
        putPixelMap = 8         # from client to PB
        ExpanderConfig = 9      # from client to PB *and* PB to client

    class frameTypes(Flag):
        """The second byte of a binary frames tells whether this packet is part of a set."""
        frameNone = 0
        frameFirst = 1
        frameMiddle = 2
        frameLast = 4

    def wsReceive(self, binaryMessageType=None):
        """
        Utility method: Blocking websocket receive that waits for a packet of a given type
        and gracefully handles errors and stray extra packets.
        """
        message = None
        startTime = self._time_in_millis()
        # loop until we have all the packets we want or we hit timeout.
        while True:
            try:
                frame = self.ws.recv()
                if type(frame) is str:
                    # Some frames are sent unrequested and often interrupt the conversation; we'll just
                    # just save the most recent one and retrieve it later when we want it.
                    if frame.startswith('{"fps":'):
                        self.latestStats = frame
                    elif frame.startswith('{"activeProgram":'):
                        self.latestSequencer = frame
                    # We wanted a text frame, we got a text frame.
                    elif binaryMessageType is None: 
                        return frame
                else:
                    frameType = frame[0]
                    if frameType == self.messageTypes.previewFrame.value: 
                        # This packet type doesn't have frameType flags.
                        if binaryMessageType == self.messageTypes.previewFrame: 
                            return frame[1:] 
                        else:
                            continue
                    # Check the flags to see if we need to read more packets.
                    frameFlags = frame[1]
                    if message is None and not (frameFlags & self.frameTypes.frameFirst.value): raise # The first frame must be a start frame
                    if message is not None and (frameFlags & self.frameTypes.frameFirst.value): raise # We shouldn't get a start frame after we've started
                    if message is None: message = frame[2:]
                    else: message += frame[2:]
                    # If we've received all the packets, deal with the message.
                    if (frameFlags & self.frameTypes.frameLast.value):
                        # Expander config frames are ONLY sent during a config request, but they sometimes arrive
                        # out of order so we'll save them and retrieve them separately.
                        if frameType == self.messageTypes.ExpanderConfig:
                            self.latestExpander = self.__decodeExpanderData(frame[2:])
                            continue
                        if frameType != binaryMessageType:
                            print(f"got unwanted binary frame type {frameType} (wanted {binaryMessageType})")
                            continue # skip this unwanted binary frame (which shouldn't really happen anyway)
                        return message

            except websocket._exceptions.WebSocketTimeoutException: # timeout -- we can just ignore this
                endTime = self._time_in_millis()
                if (endTime - startTime) > (1000 * self.default_recv_timeout):
                    return None

            except websocket._exceptions.WebSocketConnectionClosedException: # try reopening
                #print("wsReceive reconnection")
                self.close()
                self.open()

            except Exception as e:
                print(f"wsReceive: unknown exception: {e}")
                raise

    def sendPing(self):
        return self.wsSendJson({"ping": True}, expectedResponse='{"ack":')

    def wsSendJson(self, command, expectedResponse=None):
        while True:
            try:
                self.open() # make sure it's open, even if it closed while we were doing other things.
                self.ws.send(json.dumps(command, indent=None, separators=(',', ':')).encode("utf-8"))
                if expectedResponse is None: 
                    return None

                # Wait for the expected response.
                while True:
                    # Loop until we get the right text response.
                    if type(expectedResponse) is str:
                        response = self.wsReceive(binaryMessageType=None)
                        if response is None: break
                        if response.startswith(expectedResponse): break
                    # Or the right binary response.
                    elif type(expectedResponse) is self.messageTypes:
                        response = self.wsReceive(binaryMessageType=expectedResponse)
                        break
                # Now that we've got the right response, return it.
                return response

            except websocket._exceptions.WebSocketConnectionClosedException:
                self.close()
                self.open()   # try reopening

            except:
                self.close()
                self.open()   # try reopening
                #raise

    def wsSendBinary(self, binaryMessageType, blob, expectedResponse=None):
        """Send a binary packet to the Pixelblaze."""
        while True:
            try:
                # Break the frame into manageable chunks.
                response = None
                maxFrameSize = 8192
                if binaryMessageType == self.messageTypes.putByteCode: maxFrameSize = 1280
                for i in range(0, len(blob), maxFrameSize):

                    # Set the frame header values.
                    frameHeader = bytearray(2)
                    frameHeader[0] = binaryMessageType.value
                    frameFlag = self.frameTypes.frameNone
                    if i == 0: frameFlag |= self.frameTypes.frameFirst
                    if (len(blob) - i) <= maxFrameSize: frameFlag |= self.frameTypes.frameLast
                    else: frameFlag = self.frameTypes.frameMiddle
                    frameHeader[1] = frameFlag.value

                    # Send the packet.
                    self.ws.send_binary(bytes(frameHeader) + blob[i:i + maxFrameSize])

                    # Wait for the expected response.
                    while True:
                        # Loop until we get the right text response.
                        if type(expectedResponse) is str:
                            response = self.wsReceive(binaryMessageType=None)
                            if response is None: break
                            if response.startswith(expectedResponse): break
                        # Or the right binary response.
                        elif type(expectedResponse) is self.messageTypes:
                            response = self.wsReceive(binaryMessageType=expectedResponse)
                            break
                # Now that we've sent all the chunks, return the last status received.
                return response

            except websocket._exceptions.WebSocketConnectionClosedException:
                print("wsSendBinary reconnection")
                self.close()
                self.open()   # try reopening

            except:
                print("wsSendBinary received unexpected exception")
                self.close()
                self.open()
                #raise

    def getPeers(self):
        """A new command, added to the API but not yet implemented as of v2.29/v3.24, 
        that will return a list of all the Pixelblazes visible on the local network segment."""
        self.wsSendJson({"getPeers": True})
        return self.wsReceive(binaryMessageType=None)

    # --- PIXELBLAZE FILESYSTEM FUNCTIONS:

    def getUrl(self, endpoint=None):
        return urljoin(f"http://{self.ipAddress}", endpoint)

    def getFileList(self):
        """Returns a list of all the files contained on this Pixelblaze; for Pixelblazes running firmware 
        versions lower than 2.29/3.24, the list includes the names of optional configuration files that may 
        or may not exist on this particular Pixelblaze, depending on its setup."""
        fileList = []
        with requests.get(self.getUrl("list"), proxies=self.proxyDict) as rList:
            if rList.status_code == 200:
                fileList = rList.text.split('\n') # returns a number of lines, each containing [filename][tab][size][newline]
            elif rList.status_code == 404:
                # If the Pixelblaze doesn't support the "/list" endpoint, get the patternList using WebSocket calls.
                fileList = []
                for filename in self.getPatternList():
                    fileList.append(f"/p/{filename}\t0")    # the pattern blob
                    fileList.append(f"/p/{filename}.c\t0")  # the current value of any (optional) UI controls
                # Append the names of all the other files a Pixelblaze might contain, some of which may not exist on any particular device.
                for filename in ["apple-touch-icon.png", "favicon.ico", "config.json", "obconf.dat", "pixelmap.txt", "pixelmap.dat", "l/_defaultplaylist_"]:
                    fileList.append(f"/{filename}\t0")
            else: 
                rList.raise_for_status()

        fileList.sort()
        return fileList

    def getFile(self, fileName):
        """Downloads a file from this Pixelblaze using the HTTP API."""
        # Strip any leading slash from the filename.
        with requests.get(self.getUrl(fileName), proxies=self.proxyDict) as rGet:
            if rGet.status_code not in [200, 404]:
                rGet.raise_for_status()
                return None
            return rGet.content

    def putFile(self, fileName, fileContents):
        """Uploads a file to this Pixelblaze using the HTTP API."""
        fileData = {'data': (fileName, fileContents)}
        with requests.post(self.getUrl("edit"), files=fileData, proxies=self.proxyDict) as rPost:
            if rPost.status_code != 200:
                rPost.raise_for_status()
                return False
        return True

    def deleteFile(self, fileName):
        """Deletes a file from this Pixelblaze using the HTTP API."""
        with requests.get(self.getUrl(f"delete?path={fileName}"), proxies=self.proxyDict) as rFile:
            if rFile.status_code not in [200, 404]:
                rFile.raise_for_status()
                return False
        return True

    # --- GLOBAL functions: RENDERER STATISTICS:

    def getStatistics(self):
        """Grab one of the statistical packets that Pixelblaze sends every second."""
        #self.setSendPreviewFrames(True)
        while True:
            if not self.latestStats is None: return json.loads(self.latestStats)
            ignored = self.wsReceive(binaryMessageType=None)

    def setSendPreviewFrames(self, doUpdates):
        assert type(doUpdates) is bool
        if doUpdates is True: response = self.messageTypes.previewFrame
        else: response = None
        self.wsSendJson({"sendUpdates": doUpdates}, expectedResponse=response)

    def getPreviewFrame(self):
        """Grab one of the preview frames that Pixelblaze sends after every render cycle."""
        oldTimeout = self.ws.gettimeout()
        self.ws.settimeout(2 * self.default_recv_timeout)
        response = self.wsReceive(binaryMessageType=self.messageTypes.previewFrame)
        self.ws.settimeout(oldTimeout)
        return response

    # --- GLOBAL functions: RENDERER STATISTICS: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getFPS(self, savedStatistics=None):
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('fps')

    def getUptime(self, savedStatistics=None):
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('uptime')

    def getStorageUsed(self, savedStatistics=None):
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('storageUsed')

    def getStorageSize(self, savedStatistics=None):
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('storageSize')

    # --- GLOBAL functions: CONTROLS (available on all tabs):

    def setBrightnessSlider(self, brightness, save=False):
        """
        Set the value of the UI brightness slider.
        """
        self.wsSendJson({"brightness": self._clamp(brightness, 0, 1), "save": save}, expectedResponse=None)

    # --- GLOBAL functions: CONTROLS: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getBrightnessSlider(self, configSettings=None):
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('brightness')

    # --- PATTERNS tab: SEQUENCER section

    class sequencerModes(IntEnum):
        Off = 0
        ShuffleAll = 1
        Playlist = 2

    def setSequencerMode(self, sequencerMode, save=False):
        """Sets the sequencer mode to Off, ShuffleAll, or Playlist."""
        self.wsSendJson({"sequencerMode": sequencerMode, "save": save}, expectedResponse=None)

    # --- PATTERNS tab: SEQUENCER section: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getSequencerMode(self, configSequencer=None):
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get('sequencerMode')

    # --- PATTERNS tab: SEQUENCER section: SHUFFLE ALL mode

    def playSequencer(self):
        """Mimics the 'Play' button."""
        self.wsSendJson({"runSequencer": True}, expectedResponse=None)

    def pauseSequencer(self):
        """Mimics the 'Pause' button."""
        self.wsSendJson({"runSequencer": False}, expectedResponse=None)

    def nextSequencer(self):
        """Mimics the 'Next' button."""
        self.wsSendJson({"nextProgram": True}, expectedResponse=None)

    def setSequencerShuffleTime(self, nMillis):
        """
        Sets number of milliseconds the Pixelblaze's sequencer will run each pattern
        before switching to the next.
        """
        self.wsSendJson({"sequenceTimer": nMillis}, expectedResponse=None)

    # --- PATTERNS tab: SEQUENCER section: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getSequencerShuffleTime(self, configSequencer=None):
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get("ms")

    # --- PATTERNS tab: SEQUENCER section: PLAYLIST mode

    def getSequencerPlaylist(self, playlistId="_defaultplaylist_"):
        """This function fetches the named playlist."""
        return json.loads(self.wsSendJson({"getPlaylist": playlistId}, expectedResponse='{"playlist":'))

    def setSequencerPlaylist(self, playlistContents, playlistId="_defaultplaylist_"):
        """This function replaces the entire contents of the named playlist."""
        self.latestSequencer = None # clear cache to force refresh
        ignored = self.wsSendJson(playlistContents, expectedResponse=None)

    def addToSequencerPlaylist(self, patternId, duration, playlist="_defaultplaylist_"):
        """This function fetches the named playlist and appends a new item to it."""
        playlist = self.getSequencerPlaylist(playlist)
        playlist.get('playlist').get('items').append({'id': patternId, 'ms': duration})
        return self.setSequencerPlaylist(playlist)

    # --- PATTERNS tab: SEQUENCER section: convenience functions

    def startSequencer(self, mode=sequencerModes.ShuffleAll):
        """
        Enable and start the Pixelblaze's internal sequencer. The mode parameters
        can be 1 - shuffle all patterns, or 2 - playlist mode.  The playlist
        must be configured through the Pixelblaze's web UI.
        """
        self.wsSendJson({"sequencerMode": mode, "runSequencer": True}, expectedResponse=None)

    def stopSequencer(self):
        """Stop and disable the Pixelblaze's internal sequencer"""
        self.setSequencerMode(self.sequencerModes.Off) 
        self.wsSendJson({"runSequencer": False}, expectedResponse=None)

    def pauseSequencer(self):
        """
        Temporarily pause the Pixelblaze's internal sequencer, without
        losing your place in the shuffle or playlist. Call "playSequencer"
        to restart.  Has no effect if the sequencer is not currently running.
        """
        self.wsSendJson({"runSequencer": False}, expectedResponse=None)

    def playSequencer(self):
        """
        Start the Pixelblaze's internal sequencer in the current mode,
        at the current place in the shuffle or playlist.  Compliment to
        "pauseSequencer".  Will not start the sequencer if it has not
        been enabled via "startSequencer" or the Web UI.
        """
        self.wsSendJson({"runSequencer": True}, expectedResponse=None)

    # --- PATTERNS tab: SAVED PATTERNS section

    def getPatternList(self, forceRefresh=False):
        """
        Returns a dictionary containing the unique ID and the text name of all
        saved patterns on the Pixelblaze. Normally reads from the cached pattern
        list, which is refreshed every 10 minutes by default.

        To force a cache refresh, set the optional "refresh" parameter to True

        To change the cache refresh interval, call setCacheRefreshTime(seconds)
        """
        if forceRefresh is True or ((self._time_in_millis() - self.cacheRefreshTime) > self.cacheRefreshInterval):
            self._refreshPatternCache()
            self.cacheRefreshTime = self._time_in_millis()
        return self.patternCache

    def setActivePattern(self, pid, save=False):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.functionalityChanged, "setActivePattern(name_or_id)", "setActivePattern(id)")
        """
        Sets the active pattern by pattern ID.  

        It does not validate the input id, or determine if the pattern is available on the Pixelblaze.
        """
        self.wsSendJson({"activeProgramId": pid, "save": save}, expectedResponse='{"activeProgram":')

    def exportPatternAsEpe(self, patternId, name=None):
        # If no name was specified, look it up.
        if name is None: name = self.getPatternList(refresh=True).get(patternId, "Unknown Pattern")
        # Request the pattern elements from the Pixelblaze and combine them into an EPE.
        epe = {
            'name': self.name,
            'id': patternId,
            'sources': json.loads(self.getSourceCode(patternId)),
            'preview': base64.b64encode(self.getPreviewImage).decode('UTF-8')
        }
        return json.dumps(epe, indent=2)

    def deletePattern(self, patternId):
        self.wsSendJson({"deleteProgram": patternId}, expectedResponse=None)

    def getPreviewImage(self, patternId):
        return self.wsSendJson({"getPreviewImg": patternId}, expectedResponse=self.messageTypes.previewImage)

    def getVars(self):
        """
        Returns JSON object containing all vars exported from the active pattern.
        """
        return json.loads(self.wsSendJson({"getVars": True}, expectedResponse='{"vars":'))

    def setVars(self, json_vars):
        """
        Sets pattern variables contained in the json_vars (JSON object) argument.
        Does not check to see if the variables are exported by the current active pattern.
        """
        self.wsSendJson({"setVars": json.dumps(json_vars)})

    # --- PATTERNS tab: SAVED PATTERNS section: convenience functions

    def setCacheRefreshTime(self,seconds):
        """
        Set the interval, in seconds, at which the pattern cache is cleared and
        a new pattern list is loaded from the Pixelblaze.  Default is 600 (10 minutes)
        """
        # a million seconds is about 277 hours or about 11.5 days.  Probably long enough.
        self.cacheRefreshInterval = 1000 * self._clamp(seconds, 0, 1000000)

    def _refreshPatternCache(self):
        """
        Reads a dictionary containing the unique ID and the text name of all
        saved patterns on the Pixelblaze into the pattern cache.
        """
        self.patternCache = dict()
        oldTimeout = self.ws.gettimeout()
        self.ws.settimeout(3 * self.default_recv_timeout)
        response = self.wsSendJson({"listPrograms": True}, expectedResponse=self.messageTypes.getProgramList)
        self.ws.settimeout(oldTimeout)
        for pattern in [m.split("\t") for m in response.decode("utf-8").split("\n")]:
            if len(pattern) == 2: 
                self.patternCache[pattern[0]] = pattern[1]

    def setVariable(self, var_name, value):
        """
        Sets a single variable to the specified value. Does not check to see if the
        variable is actually exported by the current active pattern.
        """
        self.setVars({var_name: value})

    def variableExists(self, var_name):
        """
        Returns True if the specified variable exists in the active pattern,
        False otherwise.
        """
        val = self.getVars()
        if val is None:
            return False
        return True if var_name in val else False

    def getActivePattern(self, configSequencer=None):
        """
        Returns the ID of the pattern currently running on the Pixelblaze (if available).  
        Otherwise returns an empty dictionary object.
        WHY AN EMPTY DICTIONARY OBJECT, when the activeID is a string?
        """
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get('activeProgram', {}).get('activeProgramId', {})

    def _get_current_controls(self):
        """
        Utility Method: Returns controls for currently running pattern if
        available, None otherwise
        """
        return self.getConfigSequencer().get('activeProgram', {}).get('controls', {})

    def getControls(self, pattern=None):
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
        if pattern is None: return self._get_current_controls()

        # if pattern name or id was specified, attempt to validate against pattern list
        # and get stored values for that program
        pattern = self._get_pattern_id(pattern)
        if pattern is None: return {}

        response = self.wsSendJson({"getControls": pattern}, expectedResponse='{"controls":')
        if not response is None: return json.loads(response)
        return None

    def setControls(self, json_ctl, save=False):
        """
        Sets UI controls in the active pattern to values contained in
        the JSON object in argument json_ctl. To reduce wear on
        Pixelblaze's flash memory, the values are not saved by default.
        """
        self.wsSendJson({"setControls": json.dumps(json_ctl), "save": save}, expectedResponse='{"ack":')

    def setControl(self, ctl_name, value, save=False):
        """
        Sets the value of a single UI controls in the active pattern.
        to values contained in in argument json_ctl. To reduce wear on
        Pixelblaze's flash memory, the save parameter is ignored
        by default.  See documentation for _enable_flash_save() for
        more information.
        """
        val = {ctl_name: max(0, min(value, 1))}  # clamp value to proper 0-1 range
        self.setControls(val, save)

    def setColorControl(self, ctl_name, color, save=False):
        """
        Sets the 3-element color of the specified HSV or RGB color picker.
        The color argument should contain an RGB or HSV color with all values
        in the range 0-1. To reduce wear on Pixelblaze's flash memory, the save parameter
        is ignored by default.  See documentation for _enable_flash_save() for
        more information.
        """

        # based on testing w/Pixelblaze, no run-time length or range validation is performed
        # on color. Pixelblaze ignores extra elements, sets unspecified elements to zero,
        # takes only the fractional part of elements outside the range 0-1, and
        # does something (1-(n % 1)) for negative elements.
        val = {ctl_name: color}
        self.setControls(val, save)

    def controlExists(self, ctl_name, pattern=None):
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

    def getColorControlNames(self, pattern=None):
        """
        Returns a list of names of the specified pattern's rgbPicker or
        hsvPicker controls if any exist, None otherwise.  If the pattern
        argument is not specified, check the currently running pattern
        """
        controls = self.getControls(pattern)
        if controls is None:
            return None

        # check for hsvPicker
        result = dict(filter(lambda ctl: "hsvPicker" in ctl[0], controls.items()))
        ctl_list = list(result.keys())

        # check for rgbPicker
        result = dict(filter(lambda ctl: "rgbPicker" in ctl[0], controls.items()))
        ctl_list += list(result.keys())

        return ctl_list if (len(ctl_list) > 0) else None

    def getColorControlName(self, pattern=None):
        """
        Returns the name of the specified pattern's first rgbPicker or
        hsvPicker control if one exists, None otherwise.  If the pattern
        argument is not specified, checks in the currently running pattern
        """
        result = self.getColorControlNames(pattern)
        if result is None:
            return result
        else:
            return result[0]

    # --- EDIT tab:

    def sendToRenderer(self, bytecode, controls={}):
        """Sends a blob of bytecode and a JSON dictionary of UI controls to the Renderer.
        Mimics the actions of the webUI code editor.  Can also be used to change the displayed
        pattern (including to a pattern not saved on the Pixelblaze's filesystem!) without 
        actually setting the activePattern. """
        self.wsSendJson({"pause":True,"setCode":{ "size": len(bytecode)}}, expectedResponse='{"ack":')
        self.wsSendBinary(self.messageTypes.putByteCode, bytecode, expectedResponse='{"ack":')
        self.wsSendJson({"setControls": controls}, expectedResponse='{"ack":')
        self.wsSendJson({"pause":False}, expectedResponse='{"ack":')

    def getSourceCode(self, patternId):
        """Gets the sourceCode of a saved pattern from the Pixelblaze.  Can be used 
        to mimic the effects of the webUI's "Export" function. """
        sources = self.wsSendJson({"getSources":patternId}, expectedResponse=self.messageTypes.getSourceCode)
        if sources is not None: return LZstring.decompress(sources)
        return None

    def savePattern(self, previewImage, sourceCode, byteCode):
        """Saves the components of a pattern to the Pixelblaze filesystem. 
        Mimics the effects of the 'Save' button."""
        self.wsSendBinary(self.messageTypes.previewImage, previewImage, expectedResponse='{"ack":')
        self.wsSendBinary(self.messageTypes.putSourceCode, LZstring.compress(sourceCode), expectedResponse='{"ack":')
        self.wsSendBinary(self.messageTypes.putByteCode, byteCode, expectedResponse='{"ack":')

    # --- MAPPER tab: Pixelmap settings

    def getMapFunction(self):
        return self.getFile("/pixelmap.txt")

    def setMapFunction(self, mapFunction):
        # TBD:  This saves the mapFunction text into the file backing the map editor, which is unrelated
        #       to the actual mapData which is saved separately (see setMapData function below); in future,
        #       could we also execute the mapFunction and generate the binary mapData? We'd need to use an 
        #       intepreter like pyv8 (https://code.google.com/archive/p/pyv8/), pyMiniRacer 
        #       (https://github.com/sqreen/PyMiniRacer), quickjs (https://github.com/PetterS/quickjs),  
        #       js2py (https://github.com/PiotrDabkowski/Js2Py), or pyexecjs (https://github.com/doloopwhile/PyExecJS) 
        #       -- maybe wrapped in jsengine (https://pypi.org/project/jsengine/)?
        #
        #       OTHERWISE, we could use a Python function (or any other means) to generate the number values,
        #       and as the "map function" we could save a comment block containing the 'source code' as comments,
        #       along with a literal javascript array of numbers which match the mapData generated.
        return self.putFile('/pixelmap.txt', mapFunction)

    def getMapData(self):
        """Gets the binary representation of the pixelMap entered on the 'Mapper' tab."""
        return self.getFile('/pixelmap.dat')

    def setMapData(self, mapData, save=True):
        # Send the mapData...
        self.wsSendBinary(self.messageTypes.putPixelMap, mapData, expectedResponse='{"ack":')
        # ...and make it permanent (same as pressing "Save" in the map editor).
        if save: self.wsSendJson({"savePixelMap":True}, expectedResponse=None)

    # --- SETTINGS menu

    def getConfigSettings(self):
        """Returns a JSON dictionary containing the configuration of the Pixelblaze 
        settings, render engine, and the outputExpander (if it exists)."""
        # The configuration comes in the form of three packets; two text and one binary.
        # The second and third packets can come out of order so we'll have to be flexible.
        self.latestSequencer = None  # clear cache to force refresh
        self.latestExpander = None  # clear cache to force refresh
        self.wsSendJson({"getConfig": True}, expectedResponse=None)

        # First the config packet.
        settings = {}
        while True:
            response = self.wsReceive(binaryMessageType=None)
            if not response is None:
                settings = json.loads(response)
                break

        # Now the others, in any order.
        while True:
            if (self.latestSequencer is None) or (self.latestExpander is None):
                ignored = self.wsReceive(binaryMessageType=None)
                break

        # Now that we've got them all, return the settings.
        return settings

    def getConfigSequencer(self):
        """Retrieve the most recent Sequencer state."""
        while True:
            if not self.latestSequencer is None: return json.loads(self.latestSequencer)
            ignored = self.getConfigSettings()

    def getConfigExpander(self):
        """Retrieve any Expander configuration block that came along with the Settings."""
        while True:
            if not self.latestExpander is None: return self.latestExpander
            ignored = self.getConfigSettings()

    def __decodeExpanderData(self, data):
        # We can't store bytes into JSON so we'll have to encode it...
        # return base64.b64encode(data).decode('utf-8')
        # ...but it might be more user-friendly to convert it into something readable.

        # Check the magic number.
        versionNumber = data[0]
        #versionNumber = struct.unpack('<B', binaryData)[0]
        if versionNumber != 5:
            return {'expanders': [], 'error': f"expander data has incorrect magic number (expected 5, received {versionNumber})"}
        
        # Parse the rest of the file.
        binaryData = data[1:]
        binarySize = len(binaryData)
        if binarySize % 96 != 0:
            return {'expanders': [], 'error': f"expander data has incorrect length (must be a multiple of 96, received {versionNumber})"}
        
        # Convert the file to a human-readable equivalent.
        rowSize = 12
        boards = { 'expanders': [ ] }
        #ledTypes = [ 'notUsed', 'WS2812B', 'drawAll', 'APA102 Data', 'APA102 Clock' ]
        colorOrders = { 0x24: 'RGB', 0x18: 'RBG', 0x09: 'BRG', 0x06: 'BGR', 0x21: 'GRB', 0x12: 'GBR', 0xE4: 'RGBW', 0xE1: 'GRBW' }
        for row in range(binarySize // rowSize):
            offsets = struct.unpack('<4B2H4x', binaryData[(row * rowSize):(row + 1) * rowSize])
            boardAddress = offsets[0] >> 3
            channel = offsets[0] % 8
            ledType = offsets[1]
            numElements = offsets[2]
            colorOrder = offsets[3]
            pixelCount = offsets[4]
            startIndex = offsets[5]
            dataSpeed = offsets[6:10]

            #   boardAddress
            #       channel | type | startIndex | pixelCount | colorOrder | dataSpeed
            board = row // 8
            rowNumber = row % 8
            if rowNumber == 0: # start a new board
                boards['expanders'].append( { 'address': boardAddress, 'rows': { } } )
            boards['expanders'][board]['rows'][rowNumber] = [ ]
            if ledType == 1 or ledType == 3:
                boards['expanders'][board]['rows'][rowNumber].append( { 'channel': channel, 'type': ledType, 'startIndex': startIndex, 'count': pixelCount, 'options': colorOrders[colorOrder], 'dataSpeed': dataSpeed } )
                #boards['boards'][board]['rows'][rowNumber].append( { 'channel': channel, 'type': ledTypes[ledType], 'startIndex': startIndex, 'count': pixelCount, 'options': colorOrders[colorOrder], 'dataSpeed': dataSpeed } )
            else:
                boards['expanders'][board]['rows'][rowNumber].append( { 'channel': channel, 'type': ledType } )
                #boards['boards'][board]['rows'][rowNumber].append( { 'channel': channel, 'type': ledTypes[ledType] } )

        return boards #json.dumps(boards, indent=2)

    # --- SETTINGS menu: CONTROLLER section: NAME settings

    def setDeviceName(self, name):
        self.wsSendJson({"name":name}, expectedResponse=None)

    def setDiscovery(self, enableDiscovery, timezoneName=None):
        if timezoneName is not None: 
            # Validate the timezone name.
            if not timezoneName in pytz.all_timezones: 
                print(f"setDiscovery: unrecognized timezone {timezoneName}")
                return
        self.wsSendJson({"discoveryEnable": enableDiscovery, "timezone": timezoneName}, expectedResponse=None)

    def setTimezone(self, timezoneName):
        if timezoneName is not None: 
            # Validate the timezone name.
            if not timezoneName in pytz.all_timezones: 
                print(f"setDiscovery: unrecognized timezone {timezoneName}")
                return
        self.wsSendJson({"timezone": timezoneName}, expectedResponse=None)

    def setAutoOffEnable(self, boolValue, save=False):
        self.wsSendJson({"autoOffEnable": boolValue, "save": save}, expectedResponse=None)

    def setAutoOffStart(self, timeValue, save=False):
        if type(timeValue) is time:
            timeValue = timeValue.strftime('%H:%M')
        self.wsSendJson({"autoOffStart": timeValue, "save": save}, expectedResponse=None)

    def setAutoOffEnd(self, timeValue, save=False):
        if type(timeValue) is time:
            timeValue = timeValue.strftime('%H:%M')
        self.wsSendJson({"autoOffEnd": timeValue, "save": save}, expectedResponse=None)

    # --- SETTINGS menu: CONTROLLER section: NAME settings: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getDeviceName(self, configSettings=None):
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('name')

    def getDiscovery(self, configSettings=None):
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('discoveryEnable')

    def getTimezone(self, configSettings=None):
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('timezone')

    def getAutoOffEnable(self, configSettings=None):
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('autoOffEnable')

    def getAutoOffStart(self, configSettings=None):
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('autoOffStart')

    def getAutoOffEnd(self, configSettings=None):
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('autoOffEnd')

    # --- SETTINGS menu: CONTROLLER section: LED settings

    def setBrightnessLimit(self, maxBrightness, save=False):
        """
        Set the Pixelblaze's global brightness.  Valid range is 0-100 
        (yes, it's inconsistent with the 'brightness' settings).

        The optional save parameter controls whether or not the
        new brightness value is saved. By default, save is False
        to reduce wear on the Pixelblaze's flash memory, so values 
        set with this method will not persist through reboots.
        """
        self.wsSendJson({"maxBrightness": self._clamp(maxBrightness, 0, 100), "save": save}, expectedResponse=None)

    class ledTypes(IntEnum):
        noLeds = 0
        APA102 = 1
        SK9822 = 1                  #synonym
        DotStar = 1                 #synonym
        unbufferedWS2812 = 2        #v2
        unbufferedSK6822 = 2        #v2 synonym
        unbufferedNeoPixel = 2      #v2 synonym
        WS2812 = 2                  #v3
        SK6822 = 2                  #v3 synonym
        NeoPixel = 2                #v3 synonym
        WS2801 = 3
        bufferedWS2812 = 4          #v2 only
        bufferedSK6822 = 4          #v2 synonym
        bufferedNeoPixel = 4        #v2 synonym
        OutputExpander = 5

    def setLedType(self, ledType, dataSpeed=None, save=False):
        """Defines the type of LEDs connected to the Pixelblaze."""
        # If no dataSpeed was specified, default to what the v3 UI sends.
        if dataSpeed is None:
            if ledType.value == 0: dataSpeed = None
            if ledType.value == 1: dataSpeed = 2000000
            if ledType.value == 2: dataSpeed = 2250000 #3500000
            if ledType.value == 3: dataSpeed = 2000000
            if ledType.value == 4: dataSpeed = 3500000
            if ledType.value == 5: dataSpeed = 2000000

        self.wsSendJson({"ledType": ledType, "dataSpeed": dataSpeed, "save": save}, expectedResponse=None)

    def setPixelCount(self, nPixels, save=False):
        """
        Sets the number of LEDs attached to the Pixelblaze. Does
        not change the current pixel map. 
        CAUTION: Recommended for advanced users only.
        """
        self.wsSendJson({"pixelCount": nPixels, "save": save}, expectedResponse=None)
        # The Pixelblaze UI also re-evaluates the map function and resends the map data...How can we do the same?

    def setDataSpeed(self, speed, save=False):
        """
        Sets custom bit timing for WS2812-type LEDs.
        CAUTION: For advanced users only.  If you don't know
        exactly why you want to do this, DON'T DO IT.

        See discussion in this thread on the Pixelblaze forum:
        https://forum.electromage.com/t/timing-of-a-cheap-strand/739

        Note that you must call _enable_flash_save() in order to use
        the save parameter to make your new timing (semi) permanent.
        """
        self.wsSendJson({"dataSpeed": speed, "save": save}, expectedResponse=None)

    class colorOrders(Enum):
        RGB = 'RGB'
        RBG = 'RBG'
        BRG = 'BRG'
        BGR = 'BGR'
        GRB = 'GRB'
        GBR = 'GBR'
        RGBW = 'RGBW'
        GRBW = 'GRBW'
        RGB_W = 'RGB-W'
        GRB_W = 'GRB-W'

    def setColorOrder(self, colorOrder, save=False):
        assert type(colorOrder) is self.colorOrders
        self.wsSendJson({"colorOrder": colorOrder.value, "save": save}, expectedResponse=None)

    # --- SETTINGS menu: CONTROLLER section: LED settings: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getBrightnessLimit(self, configSettings=None):
        """Returns the maximum brightness for the Pixelblaze."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('maxBrightness', None)

    def getLedType(self, configSettings=None):
        """Returns the type of LEDs connected to the Pixelblaze."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('colorOrder', None)

    def getPixelCount(self, configSettings=None):
        """Returns the number of LEDs connected to the Pixelblaze."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('pixelCount', None)

    def getDataSpeed(self, configSettings=None):
        """Returns the data speed of the LEDs connected to the Pixelblaze."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('dataSpeed', None)

    def getColorOrder(self, configSettings=None):
        """Returns the color order of the LEDs connected to the Pixelblaze."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('colorOrder', None)

    # --- SETTINGS menu (v3 only): CONTROLLER section: POWER SAVING settings

    class cpuSpeeds(Enum):
        low = "80"
        medium = "160"
        high = "240"

    def setCpuSpeed(self, cpuSpeed):
        assert type(cpuSpeed) is self.cpuSpeeds
        # The "cpuSpeed" setting doesn't exist on v2, so ignore it if not v3.
        if (self.getConfigSettings().get('ver', '0').startswith('3')):
            self.wsSendJson({"cpuSpeed": cpuSpeed.value}, expectedResponse=None)

    def setNetworkPowerSave(self, disableWifi):
        """
        Pixelblaze can be used without Wifi, which significantly reduces power requirements 
        for battery powered installations.
        
        The "network power saving" setting only takes effect after a reboot.
        """
        self.wsSendJson({"networkPowerSave": disableWifi}, expectedResponse=None)

    # --- GLOBAL functions: CONTROLS: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getCpuSpeed(self, configSettings=None):
        # The "cpuSpeed" setting doesn't exist on v2, so return the default.
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('cpuSpeed', 240)

    def getNetworkPowerSave(self, configSettings=None):
        # The "networkPowerSave" setting doesn't exist on v2, so return the default.
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('networkPowerSave', False)

    # --- SETTINGS menu: UPDATES settings

    class updateStates(IntEnum):
        unknown = 0
        checking = 1
        inProgress = 2
        updateError = 3
        upToDate = 4
        updateAvailable = 5
        updateComplete = 6

    def getUpdateState(self):
        # We don't want to query the server every time, because changes don't happen very often.
        checkFrequency = 15 * 60 * 60 * 1000 # 15 minutes
        if self.latestUpdateCheck is None: self.latestUpdateCheck = self._time_in_millis() - (checkFrequency + 1)
        if (self._time_in_millis() - self.latestUpdateCheck) > checkFrequency:
            self.wsSendJson({"upgradeVersion": "check"}, expectedResponse=None)

        # Get the state. If it's indeterminate, wait until it resolves.
        state = self.wsSendJson({"getUpgradeState": True}, expectedResponse='{"upgradeState":')
        while True:
            if state is None: return self.updateStates.unknown
            state = json.loads(state).get("upgradeState").get("code", 0)
            if state != self.updateStates.checking: return state
            state = self.wsSendJson({"getUpgradeState": True}, expectedResponse='{"upgradeState":')

    def installUpdate(self):
        # We can't do the update if there isn't one available.
        if self.getUpdateState() != self.updateStates.updateAvailable: return self.updateStates.unknown
        # But if there is one available, we'll give it a try.
        self.latestVersion = None  # clear cache to force refresh
        self.wsSendJson({"upgradeVersion": "update"}, expectedResponse=None)
        state = self.updateStates.unknown
        while True:
            state = self.getUpdateState()
            if state in [3, 4, 5, 6]: break
            print(f"updateProgress: {self.updateStates(state).name}")
            time.sleep(0.5)
        return state

    # --- SETTINGS menu: UPDATES section: convenience functions

    def getVersion(self):
        if self.latestVersion is None: 
            self.latestVersion = self.getConfigSettings().get('ver', None)
        return self.latestVersion

    def getVersionMajor(self):
        """Returns the major version number as a positive integer (eg. for v3.24, returns 3)."""
        return math.trunc(float(self.getVersion()))
    
    def getVersionMinor(self):
        """Returns the minor version number as a positive integer (eg. for v3.24, returns 24)."""
        version = float(self.getVersion())
        return math.trunc(100 * (version - math.trunc(version)))

    # --- SETTINGS menu: BACKUPS section

    def saveBackup(self, fileName):
        """Save the contents of this Pixelblaze into a Pixelblaze Binary Backup file."""
        PBB.fromPixelblaze(self).toFile(fileName)

    def restoreFromBackup(self, fileName):
        """Restore the contents of this Pixelblaze from a Pixelblaze Binary Backup file."""
        PBB.toPixelblaze(self)

    def reboot(self):
        """Restart the Pixelblaze (necessary for the Pixelblaze to recognize changes to configuration files)."""
        with requests.post(self.getUrl("reboot"), proxies=self.proxyDict) as rReboot:
            if rReboot.status_code not in [200, 404]:
                rReboot.raise_for_status()

    # --- ADVANCED menu: 

    def setBrandName(self, brandName):
        """"""
        self.wsSendJson({"brandName": brandName}, expectedResponse=None)

    def setSimpleUiMode(self, doSimpleMode):
        """"""
        self.wsSendJson({"simpleUiMode": doSimpleMode}, expectedResponse=None)

    def setLearningUiMode(self, doLearningMode):
        """"""
        self.wsSendJson({"learningUiMode": doLearningMode}, expectedResponse=None)

    # --- ADVANCED menu: convenience functions
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getBrandName(self, configSettings=None):
        """Returns the brand name, if any, of this Pixelblaze (blank unless rebadged by a reseller)."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('brandName', None)

    def getSimpleUiMode(self, configSettings=None):
        """Returns whether Simple UI mode is enabled."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('simpleUiMode', None)
    
    def getLearningUiMode(self, configSettings=None):
        """Returns whether Learning UI mode is enabled."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('learningUiMode', None)
    
    # --- PRIVATE HELPER FUNCTIONS

    class deprecationReasons(IntEnum):
        renamed = 1
        functionalityChanged = 2
        notRequired = 3

    warningsGiven = []
    def __printDeprecationMessage(self, deprecationReason, oldFunction, newFunction):
        if not oldFunction in self.warningsGiven:
            self.warningsGiven.append(oldFunction)
            if deprecationReason == self.deprecationReasons.renamed:
                print(f'[pixelblaze-client] Warning: function "{oldFunction}" has been renamed and this compatibility stub will be removed in a future release; to avoid disruption, modify your code to use the replacement function "{newFunction}".')
            elif deprecationReason == self.deprecationReasons.functionalityChanged:
                print(f'[pixelblaze-client] Warning: function "{oldFunction}" has been changed and may not have the same behavior; review the changelog and (if necessary) modify your code to use the replacement function "{newFunction}".')
            elif deprecationReason == self.deprecationReasons.notRequired:
                print(f'[pixelblaze-client] Warning: function "{oldFunction}" is no longer required and will be removed in a future release; you may safely remove it from your code.')

    def _clamp(self, n, smallest, largest):
        """
        Utility Method: Why doesn't Python have clamp()?
        """
        return max(smallest, min(n, largest))

    def _time_in_millis(self):
        """
        Utility Method: Returns current time in milliseconds
        """
        return int(round(time.time() * 1000))

    # --- LEGACY FUNCTIONS (may be deprecated in the near future)

    def pauseRenderer(self, doPause):
        """
        Pause rendering. Lasts until unpause() is called or
        the Pixelblaze is reset.
        CAUTION: For advanced users only.  If you don't know
        exactly why you want to do this, DON'T DO IT.
        """
        assert type(doPause) is bool
        self.wsSendJson({"pause": doPause}, expectedResponse='{"ack":')

    def _id_from_name(self, patterns, name):
        """Utility Method: Given the list of patterns and text name of a pattern, returns that pattern's ID"""
        for key, value in patterns.items():
            if name == value:
                return key
        return None

    def _get_pattern_id(self, pid):
        """Utility Method: Returns a pattern ID if passed either a valid ID or a text name"""
        patterns = self.getPatternList()
        if patterns.get(pid) is None:
            pid = self._id_from_name(patterns, pid)
        return pid

    def setActivePatternByName(self, patternName, save=False):
        """Sets the currently running pattern using a text name"""
        self.setActivePattern(self._get_pattern_id(patternName), save)

    # --- PUBLIC FUNCTIONS TO BE DEPRECATED

    @property
    def ipAddr(self):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.renamed, "ipAddr", "ipAddress")
        return self.ipAddress

    def setSequenceTimer(self, n):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.renamed, "setSequenceTimer", "setShuffleTime")
        self.setShuffleTime(n)

    def ws_recv(self, wantBinary=False, packetType=0x07):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.functionalityChanged, "ws_recv", "wsReceive")
        """
        Utility method: Blocking websocket receive that waits for a packet of a given type
        and gracefully handles errors and stray extra packets.
        """
        result = None
        try:
            while True:  # loop until we hit timeout or have the packet we want
                result = self.ws.recv()
                #resp_opcode, result = self.ws.recv_data()
                if type(result) is str:
                    if wantBinary is False: break
                elif result[0] is packetType: break
                else: continue

        except websocket._exceptions.WebSocketTimeoutException:
            return None  # timeout -- we can just ignore this

        except websocket._exceptions.WebSocketConnectionClosedException:
            self.close()
            self.open()   # try reopening
        except Exception as e:
            print(f"ws_recv unknown exception: {e}")

        return result

    def pause(self):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.functionalityChanged, "pause", "pauseRenderer(true)")
        self.pauseRenderer(True)

    def unpause(self):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.functionalityChanged, "pause", "pauseRenderer(false)")
        self.pauseRenderer(False)

    def ws_flush(self):
        """
        Utility method: drain websocket receive buffers. Called to clear out unexpected
        packets before sending requests for data w/send_string(). We do not call it
        before simply sending commands because it has a small performance cost.

        This is one of the treacherously "clever" things done to make pixelblaze-client
        work as a synchronous API when the Pixelblaze may be sending out unexpected
        packets or talking to multiple devices.  We do some extra work to make sure
        we're only receiving the packets we want.
        """

        # set very short timeout.
        self.ws.settimeout(0.1)

        # eat packets until we get a timeout exception on recv(), indicating
        # that there are no more pending packets
        try:
            while True:
                self.ws.recv()
        except websocket._exceptions.WebSocketTimeoutException:
            # restore normal timeout when done
            self.ws.settimeout(self.default_recv_timeout)
        return

    def waitForEmptyQueue(self, timeout_ms=1000):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.notRequired, "waitForEmptyQueue", "{no longer needed}")
        """
        Wait until the Pixelblaze's websocket message queue is empty, or until
        timeout_ms milliseconds have elapsed.  Returns True if an empty queue
        acknowledgement was received, False otherwise.  Throws an exception
        if the socket is disconnected.
        """
        self.ws_flush()
        self.ws.settimeout(timeout_ms / 1000)
        try:
            result = self.wsSendJson({"ping": True}, expectedResponse='{"ack":')
            self.ws.settimeout(self.default_recv_timeout)
            #return True if ((result is not None) and (result.startswith('{"ack"'))) else False
            # was failing with "startswith needs string, not int"
            if result is not None:
                if len(result) > 0:
                    if result[0] == '{':
                        if result.startswith('{"ack"'):
                            return True
            return False

        except websocket._exceptions.WebSocketTimeoutException:
            self.ws.settimeout(self.default_recv_timeout)

        return False

    def setBrightness(self, n, save=False):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.renamed, "setBrightness", "setBrightnessLimit")
        self.setBrightnessLimit(n, save)

    def getHardwareConfig(self):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.functionalityChanged, "getHardwareConfig", "getConfig{Settings|Sequencer|Expander}")
        return self.getConfigSettings()

    def set_timeout(self, timeout):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.notRequired, "set_timeout", "{no longer needed}")
        """Sets the websocket timeout. If you don't know why you need to do this, you don't need to do this."""
        self.ws.settimeout(timeout)

    def get_timeout(self):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.notRequired, "get_timeout", "{no longer needed}")
        """Gets the websocket timeout. If you don't know why you need to do this, you don't need to do this."""
        return self.ws.gettimeout()

    def _enable_flash_save(self):
        """Deprecated."""
        self.__printDeprecationMessage(self.deprecationReasons.notRequired, "_enable_flash_save", "{no longer needed}")
        """
        IMPORTANT SAFETY TIP:
           To preserve your Pixelblaze's flash memory, which can wear out after a number of
           cycles, you must call this method before using setControls() with the
           save parameter set to True.
           If this method is not called, setControls() will ignore the save parameter
           and will not save settings to flash memory.
        """
        return

# ------------------------------------------------

class PBB:
    """This class represents a Pixelblaze Binary Backup, as created from the Settings menu on a Pixelblaze."""
    # Members:
    __textData = None
    __fromDevice = None

    # private constructor
    def __init__(self, name, bytes):
        self.__fromDevice = name
        self.__textData = bytes

    # Static methods:
    @staticmethod
    def fromFile(path):
        """Creates and returns a new PixelBlazeBackup whose contents are loaded from a file on disk."""
        newOne = object.__new__(PBB)
        with open(path, "r") as file:
            newOne.__init__(pathlib.Path(path).stem, file.read())
        return newOne

    @staticmethod
    def fromIpAddress(ipAddress, proxyUrl=None, verbose=False):
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl=proxyUrl) as pb:
            return PBB.fromPixelblaze(pb, verbose)

    @staticmethod
    def fromPixelblaze(pb, verbose=False):
        newOne = object.__new__(PBB)
        fromDevice = pb.ipAddress
        archive = {"files": {}}
        #   Get the file list.
        for line in pb.getFileList():
            filename = line.split('\t')[0]
            if len(filename) > 0 and not filename in ['/index.html.gz', '/recovery.html.gz']: 
                if verbose: print(f"  Downloading {filename}")
                contents = pb.getFile(filename)
                if not contents is None:
                    archive['files'][filename] = base64.b64encode(contents).decode('UTF-8')
        newOne.__init__(fromDevice, json.dumps(archive, indent=2))
        return newOne

    # Class properties:
    @property
    def deviceName(self):
        """Returns the name of the device from which this PixelBlazeBackup was made."""
        return self.__fromDevice

    @property
    def contents(self):
        """Returns a sorted list of the filenames contained in this PixelBlazeBackup."""
        fileList = []
        for key in json.loads(self.__textData.encode().decode('utf-8-sig'))['files']:
            fileList.append(key)
        fileList.sort()
        return fileList

    def getFile(self, key):
        """Returns the contents of a particular file contained in this PixelBlazeBackup."""
        return base64.b64decode(json.loads(self.__textData.encode().decode('utf-8-sig'))['files'][key])

    #def putFile(self, key, contents):
        """Replaces or inserts the contents of a particular file into this PixelBlazeBackup."""
        # TBD

    # Class methods:
    def toFile(self, filename=None, explode=False):
        """Writes this Pixelblaze Binary Backup (PBB) to a file on disk."""
        def safeFilename(unsafeName):
            # Sanitize filenames: Only '/' (U+002F SOLIDUS) is forbidden. 
            # Other suitable candidates: '⁄' (U+2044 FRACTION SLASH); '∕' (U+2215 DIVISION SLASH); '⧸' (U+29F8 BIG SOLIDUS); 
            #   '／' (U+FF0F FULLWIDTH SOLIDUS); and '╱' (U+2571 BOX DRAWINGS LIGHT DIAGONAL UPPER RIGHT TO LOWER LEFT).
            return unsafeName.replace("/", "∕")

        if filename is None: path = pathlib.Path.cwd().joinpath(self.deviceName).with_suffix(".pbb")
        else: path = pathlib.Path(filename).with_suffix(".pbb")
        with open(path, "w") as file:
            file.write(self.__textData)
        # If 'explode' is requested, export the contents of this Pixelblaze Binary Backup (PBB) as individual files.
        if explode is True: 
            # Exploded files go in a subdirectory named after the Pixelblaze Binary Backup.
            path = pathlib.Path(path).with_suffix('')
            path.mkdir(parents=True, exist_ok=True)
            # Loop through the backup contents and save them appropriately.
            for filename in self.contents:
                # Config files go in the "Configuration" subdirectory...
                if filename[1:] in ["config.json", "config2.json", "obconf.dat", "pixelmap.txt", "pixelmap.dat"]:
                    configPath = path.joinpath("Configuration/")
                    configPath.mkdir(parents=True, exist_ok=True)
                    configPath.joinpath(filename[1:]).write_bytes(self.getFile(filename))
                # Playlists go in the "Playlists" subdirectory...
                elif filename in ["/l/_defaultplaylist_"]:
                    playlistPath = path.joinpath("Playlists/")
                    playlistPath.mkdir(parents=True, exist_ok=True)
                    playlistPath.joinpath("defaultPlaylist.json").write_bytes(self.getFile(filename))
                # Patterns go in the "Patterns" subdirectory...
                elif filename.startswith('/p/'):
                    patternPath = path.joinpath("Patterns/")
                    patternPath.mkdir(parents=True, exist_ok=True)
                    if filename.endswith('.c'):
                        # For pattern settings files, get the name from the original pattern.
                        pbp = PBP.fromBytes(pathlib.Path(filename[3:]).stem, self.getFile(filename[:-2]))
                        patternPath.joinpath(safeFilename(pbp.name)).with_suffix('.json').write_bytes(self.getFile(filename))
                    else:
                        pbp = PBP.fromBytes(pathlib.Path(filename[3:]).stem, self.getFile(filename))
                        pbpPath = patternPath.joinpath(safeFilename(pbp.name))
                        pbp.toFile(pbpPath.with_suffix('.pbp'))
                        pbp.explode(pbpPath)
                # And everything else (should just be the Icons) goes in the root directory...
                else:
                    path.joinpath(filename[1:]).write_bytes(self.getFile(filename))

    def toIpAddress(self, ipAddress, proxyUrl=None, verbose=False):
        """Uploads the contents of this PixelBlazeBackup to the destination Pixelblaze."""
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl) as pb:
            self.toPixelblaze(pb, verbose)

    def toPixelblaze(self, pb, verbose=False):
        """Uploads the contents of this PixelBlazeBackup to the destination Pixelblaze."""
        # Delete all the files that are currently loaded on the Pixelblaze (excepting the WebApp itself).
        for line in pb.getFileList():
            filename = line.split('\t')[0]
            if len(filename) > 0 and not filename in ['/index.html.gz', '/recovery.html.gz']:
                if verbose: print(f"  Deleting {filename}")
                pb.deleteFile(filename)
        # Upload everything that's in this PixelBlazeBackup to the Pixelblaze.
        for filename in self.contents:
            if verbose: print(f"  Uploading {filename}")
            pb.putFile(filename, self.getFile(filename))
        # Send a reboot command so the Pixelblaze will recognize the new configuration.
        if verbose: print(f"  Rebooting {pb.ipAddress}")
        pb.reboot()

# ------------------------------------------------

class PBP:
    """This class represents a Pixelblaze Binary Pattern that is contained in a Pixelblaze Binary Backup."""
    # Members:
    __id = None
    __binaryData = None
        # The first 9 DWORDs of the binaryData is a header containing offsets to the components:
        #   0=version, 
        #   1=nameOffset, 2=nameLength, 
        #   3=jpegOffset, 4=jpegLength,
        #   5=bytecodeOffset, 6=bytecodeLength,
        #   7=sourceOffset, 8=sourceLength

    # private constructor
    def __init__(self, id, bytes):
        self.__id = id
        self.__binaryData = bytes

    # Static methods:
    @staticmethod
    def fromBytes(id, bytes):
        """Creates and returns a new Pixelblaze Binary Pattern (PBP) whose contents are initialized from a bytes array."""
        newOne = object.__new__(PBP)
        newOne.__init__(id, bytes)
        return newOne

    @staticmethod
    def fromFile(path):
        """Creates and returns a new Pixelblaze Binary Pattern (PBP) whose contents are loaded from a file on disk."""
        with open(path, "rb") as file:
            return PBP.fromBytes(pathlib.Path(path).stem, file.read())

    @staticmethod
    def fromIpAddress(ipAddress, patternId, proxyUrl=None):
        """Creates and returns a new pattern Pixelblaze Binary Pattern (PBP) whose contents are downloaded from a URL."""
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl=proxyUrl) as pb:
            return PBP.fromPixelblaze(pb, patternId)

    @staticmethod
    def fromPixelblaze(pb, patternId):
        """Creates and returns a new pattern Pixelblaze Binary Pattern (PBP) whose contents are downloaded from a URL."""
        return PBP.fromBytes(patternId, pb.getFile(f"/p/{patternId}"))

    # Class properties:
    @property
    def id(self):
        """Returns the (internal) ID of the pattern in this Pixelblaze Binary Pattern (PBP)."""
        return self.__id

    @property
    def name(self):
        """Returns the (human-readable) name of the pattern in this Pixelblaze Binary Pattern (PBP)."""
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return self.__binaryData[offsets[1]:offsets[1]+offsets[2]].decode('UTF-8')

    @property
    def jpeg(self):
        """Returns (as a collection of bytes) the preview JPEG of the pattern in this Pixelblaze Binary Pattern (PBP)."""
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return self.__binaryData[offsets[3]:offsets[3]+offsets[4]]

    @property
    def byteCode(self):
        """Returns (as a collection of bytes) the bytecode of the pattern in this Pixelblaze Binary Pattern (PBP)."""
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return self.__binaryData[offsets[5]:offsets[5]+offsets[6]]

    @property
    def sourceCode(self):
        """Returns the source code of the pattern in this Pixelblaze Binary Pattern (PBP)."""
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return LZstring.decompress(self.__binaryData[offsets[7]:offsets[7]+offsets[8]])

    # Class methods:
    def toFile(self, path=None):
        """Saves this Pixelblaze Binary Pattern (PBP) to a file on disk."""
        if path is None: path = pathlib.Path.cwd().joinpath(self.id).with_suffix(".pbp")
        else: path = pathlib.Path(path).joinpath(self.id).with_suffix(".pbp")
        with open(path, "wb") as file:
            file.write(self.__binaryData)

    def toIpAddress(self, ipAddress, proxyUrl=None):
        """Uploads this Pixelblaze Binary Pattern (PBP) to a Pixelblaze."""
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl) as pb:
            self.toPixelblaze(pb)

    def toPixelblaze(self, pb):
        """Uploads this Pixelblaze Binary Pattern (PBP) to a Pixelblaze."""
        pb.putFile(self.id, self.__binaryData)

    def toEPE(self):
        """Creates a new EPE and initializes it from the contents of this Pixelblaze Binary Pattern (PBP)."""
        epe = {
            'name': self.name,
            'id': self.id,
            'sources': json.loads(self.sourceCode),
            'preview': base64.b64encode(self.jpeg).decode('UTF-8')
        }
        return EPE.fromBytes(json.dumps(epe, indent=2))

    def explode(self, path=None):
        """Exports (as individual files) all the components of the pattern in this Pixelblaze Binary Pattern (PBP)."""
        # Get a Path to help with creating filenames.
        if path is None: path = pathlib.Path.cwd().joinpath(self.id)
        patternPath = pathlib.Path(path)

        # ...the human-readable name.
        with open(patternPath.with_suffix('.metadata'), 'w') as outfile:
            outfile.write(self.name)

        # ...the preview image.
        with open(patternPath.with_suffix('.jpg'), 'wb') as outfile:
            outfile.write(self.jpeg)

        # ...the human-readable source code.
        with open(patternPath.with_suffix('.js'), 'w') as outfile:
            outfile.write(json.loads(self.sourceCode)['main'])

        # ...the bytecode.
        with open(patternPath.with_suffix('.bytecode'), 'wb') as outfile:
            outfile.write(self.byteCode)

        # and combine the above into a portable JSON archive (.EPE)
        self.toEPE().toFile(patternPath.with_suffix('.epe'))

# ------------------------------------------------

class EPE:
    """This class represents an Exported Pattern Envelope, as exported from the Patterns list on a Pixelblaze."""
    # Members:
    __textData = None

    # private constructor
    def __init__(self, bytes):
        self.__textData = bytes

    # Static methods:
    @staticmethod
    def fromBytes(bytes):
        """Creates and returns a new portable pattern EPE whose contents are loaded from a bytes array."""
        newOne = object.__new__(EPE)
        newOne.__init__(bytes)
        return newOne

    @staticmethod
    def fromFile(path):
        """Creates and returns a new portable pattern EPE whose contents are loaded from a file on disk."""
        with open(path, "r") as file:
            return EPE.fromBytes(file.read())

    # Class properties:
    @property
    def id(self):
        """Returns the (internal) ID of the pattern in this EPE."""
        return json.loads(self.__textData)['id']

    @property
    def name(self):
        """Returns the (human-readable) name of the pattern in this EPE."""
        return json.loads(self.__textData)['name']

    @property
    def sources(self):
        """Returns the source code of the pattern in this EPE."""
        # if @wizard ever implements code sharing this may need to change (remove ['main']?).
        return json.loads(self.__textData)['sources']['main']

    @property
    def preview(self):
        """Returns (as bytes) the preview JPEG of the pattern in this EPE."""
        return json.loads(self.__textData)['preview']

    # Class methods:
    def toFile(self, path=None):
        """Saves this portable pattern EPE to a file on disk."""
        if path is None:
            path = pathlib.Path.cwd().joinpath(self.id).with_suffix(".epe")
        with open(path, "w") as file:
            file.write(self.__textData)

    def explode(self, path):
        """Explodes the components of this portable pattern EPE into separate files"""
        print("TBD")

# ------------------------------------------------

class LZstring:
    # LZstring code borrowed (and truncated) from https://github.com/marcel-dancak/lz-string-python, which
    # on a cursory examination seems to be largely a copy of https://github.com/eduardtomasek/lz-string-python,
    # which has been forked to https://github.com/gkovacs/lz-string-python and published in PyPi as lzstring 1.0.4,
    # but which has unresolved merge issues with the parent repository, so who do you trust? Might as well 
    # keep a private copy until somebody sorts it out.

    @staticmethod
    def decompress(compressed):
        if compressed is None: return ""
        if compressed == "": return None

        resetValue = 128
        dictionary = {}
        enlargeIn = 4
        dictSize = 4
        numBits = 3
        entry = ""
        result = []

        val=compressed[0]
        position=resetValue
        index=1

        for i in range(3): dictionary[i] = i

        bits = 0
        maxpower = math.pow(2, 2)
        power = 1

        while power != maxpower:
            resb = val & position
            position >>= 1
            if position == 0:
                position = resetValue
                val = compressed[index]
                index += 1

            bits |= power if resb > 0 else 0
            power <<= 1

        next = bits
        if next == 0:
            bits = 0
            maxpower = math.pow(2, 8)
            power = 1
            while power != maxpower:
                resb = val & position
                position >>= 1
                if position == 0:
                    position = resetValue
                    val = compressed[index]
                    index += 1
                bits |= power if resb > 0 else 0
                power <<= 1
            c = chr(bits)
        elif next == 1:
            bits = 0
            maxpower = math.pow(2, 16)
            power = 1
            while power != maxpower:
                resb = val & position
                position >>= 1
                if position == 0:
                    position = resetValue
                    val = compressed[index]
                    index += 1
                bits |= power if resb > 0 else 0
                power <<= 1
            c = chr(bits)
        elif next == 2:
            return ""

        dictionary[3] = c
        w = c
        result.append(c)
        counter = 0
        while True:
            counter += 1
            if index > len(compressed): return ""

            bits = 0
            maxpower = math.pow(2, numBits)
            power = 1
            while power != maxpower:
                resb = val & position
                position >>= 1
                if position == 0:
                    position = resetValue
                    val = compressed[index]
                    index += 1
                bits |= power if resb > 0 else 0
                power <<= 1

            c = bits
            if c == 0:
                bits = 0
                maxpower = math.pow(2, 8)
                power = 1
                while power != maxpower:
                    resb = val & position
                    position >>= 1
                    if position == 0:
                        position = resetValue
                        val = compressed[index]
                        index += 1
                    bits |= power if resb > 0 else 0
                    power <<= 1

                dictionary[dictSize] = chr(bits)
                dictSize += 1
                c = dictSize - 1
                enlargeIn -= 1
            elif c == 1:
                bits = 0
                maxpower = math.pow(2, 16)
                power = 1
                while power != maxpower:
                    resb = val & position
                    position >>= 1
                    if position == 0:
                        position = resetValue
                        val = compressed[index]
                        index += 1
                    bits |= power if resb > 0 else 0
                    power <<= 1
                dictionary[dictSize] = chr(bits)
                dictSize += 1
                c = dictSize - 1
                enlargeIn -= 1
            elif c == 2: return "".join(result)

            if enlargeIn == 0:
                enlargeIn = math.pow(2, numBits)
                numBits += 1

            if c in dictionary: entry = dictionary[c]
            else:
                if c == dictSize: entry = w + w[0]
                else: return None
            result.append(entry)

            # Add w+entry[0] to the dictionary.
            dictionary[dictSize] = w + entry[0]
            dictSize += 1
            enlargeIn -= 1

            w = entry
            if enlargeIn == 0:
                enlargeIn = math.pow(2, numBits)
                numBits += 1

    def compress(uncompressed):
        if (uncompressed is None):
            return ""

        bitsPerChar = 16
        getCharFromInt = chr
        context_dictionary = {}
        context_dictionaryToCreate= {}
        context_c = ""
        context_wc = ""
        context_w = ""
        context_enlargeIn = 2 # Compensate for the first entry which should not count
        context_dictSize = 3
        context_numBits = 2
        context_data = []
        context_data_val = 0
        context_data_position = 0

        for ii in range(len(uncompressed)):
            context_c = uncompressed[ii]
            if context_c not in context_dictionary:
                context_dictionary[context_c] = context_dictSize
                context_dictSize += 1
                context_dictionaryToCreate[context_c] = True

            context_wc = context_w + context_c
            if context_wc in context_dictionary:
                context_w = context_wc
            else:
                if context_w in context_dictionaryToCreate:
                    if ord(context_w[0]) < 256:
                        for i in range(context_numBits):
                            context_data_val = (context_data_val << 1)
                            if context_data_position == bitsPerChar-1:
                                context_data_position = 0
                                context_data.append(getCharFromInt(context_data_val))
                                context_data_val = 0
                            else:
                                context_data_position += 1
                        value = ord(context_w[0])
                        for i in range(8):
                            context_data_val = (context_data_val << 1) | (value & 1)
                            if context_data_position == bitsPerChar - 1:
                                context_data_position = 0
                                context_data.append(getCharFromInt(context_data_val))
                                context_data_val = 0
                            else:
                                context_data_position += 1
                            value = value >> 1

                    else:
                        value = 1
                        for i in range(context_numBits):
                            context_data_val = (context_data_val << 1) | value
                            if context_data_position == bitsPerChar - 1:
                                context_data_position = 0
                                context_data.append(getCharFromInt(context_data_val))
                                context_data_val = 0
                            else:
                                context_data_position += 1
                            value = 0
                        value = ord(context_w[0])
                        for i in range(16):
                            context_data_val = (context_data_val << 1) | (value & 1)
                            if context_data_position == bitsPerChar - 1:
                                context_data_position = 0
                                context_data.append(getCharFromInt(context_data_val))
                                context_data_val = 0
                            else:
                                context_data_position += 1
                            value = value >> 1
                    context_enlargeIn -= 1
                    if context_enlargeIn == 0:
                        context_enlargeIn = math.pow(2, context_numBits)
                        context_numBits += 1
                    del context_dictionaryToCreate[context_w]
                else:
                    value = context_dictionary[context_w]
                    for i in range(context_numBits):
                        context_data_val = (context_data_val << 1) | (value & 1)
                        if context_data_position == bitsPerChar - 1:
                            context_data_position = 0
                            context_data.append(getCharFromInt(context_data_val))
                            context_data_val = 0
                        else:
                            context_data_position += 1
                        value = value >> 1

                context_enlargeIn -= 1
                if context_enlargeIn == 0:
                    context_enlargeIn = math.pow(2, context_numBits)
                    context_numBits += 1
                
                # Add wc to the dictionary.
                context_dictionary[context_wc] = context_dictSize
                context_dictSize += 1
                context_w = str(context_c)

        # Output the code for w.
        if context_w != "":
            if context_w in context_dictionaryToCreate:
                if ord(context_w[0]) < 256:
                    for i in range(context_numBits):
                        context_data_val = (context_data_val << 1)
                        if context_data_position == bitsPerChar-1:
                            context_data_position = 0
                            context_data.append(getCharFromInt(context_data_val))
                            context_data_val = 0
                        else:
                            context_data_position += 1
                    value = ord(context_w[0])
                    for i in range(8):
                        context_data_val = (context_data_val << 1) | (value & 1)
                        if context_data_position == bitsPerChar - 1:
                            context_data_position = 0
                            context_data.append(getCharFromInt(context_data_val))
                            context_data_val = 0
                        else:
                            context_data_position += 1
                        value = value >> 1
                else:
                    value = 1
                    for i in range(context_numBits):
                        context_data_val = (context_data_val << 1) | value
                        if context_data_position == bitsPerChar - 1:
                            context_data_position = 0
                            context_data.append(getCharFromInt(context_data_val))
                            context_data_val = 0
                        else:
                            context_data_position += 1
                        value = 0
                    value = ord(context_w[0])
                    for i in range(16):
                        context_data_val = (context_data_val << 1) | (value & 1)
                        if context_data_position == bitsPerChar - 1:
                            context_data_position = 0
                            context_data.append(getCharFromInt(context_data_val))
                            context_data_val = 0
                        else:
                            context_data_position += 1
                        value = value >> 1
                context_enlargeIn -= 1
                if context_enlargeIn == 0:
                    context_enlargeIn = math.pow(2, context_numBits)
                    context_numBits += 1
                del context_dictionaryToCreate[context_w]
            else:
                value = context_dictionary[context_w]
                for i in range(context_numBits):
                    context_data_val = (context_data_val << 1) | (value & 1)
                    if context_data_position == bitsPerChar - 1:
                        context_data_position = 0
                        context_data.append(getCharFromInt(context_data_val))
                        context_data_val = 0
                    else:
                        context_data_position += 1
                    value = value >> 1

        context_enlargeIn -= 1
        if context_enlargeIn == 0:
            context_enlargeIn = math.pow(2, context_numBits)
            context_numBits += 1

        # Mark the end of the stream
        value = 2
        for i in range(context_numBits):
            context_data_val = (context_data_val << 1) | (value & 1)
            if context_data_position == bitsPerChar - 1:
                context_data_position = 0
                context_data.append(getCharFromInt(context_data_val))
                context_data_val = 0
            else:
                context_data_position += 1
            value = value >> 1

        # Flush the last char
        while True:
            context_data_val = (context_data_val << 1)
            if context_data_position == bitsPerChar - 1:
                context_data.append(getCharFromInt(context_data_val))
                break
            else:
                context_data_position += 1

        return "".join(context_data)

# ------------------------------------------------

class PixelblazeEnumerator:
    """
    Listens on a network to detect available Pixelblazes, which the user can then list
    or open as Pixelblaze objects.  Also provides time synchronization services for
    running synchronized patterns on a network of Pixelblazes.
    """
    PORT = 1889
    SYNC_ID = 890
    BEACON_PACKET = 42
    TIMESYNC_PACKET = 43
    DEVICE_TIMEOUT = 30000
    LIST_CHECK_INTERVAL = 5000

    listTimeoutCheck = 0
    isRunning = False
    threadObj = None
    listener = None
    devices = dict()
    autoSync = False

    def __init__(self, hostIP="0.0.0.0"):
        """
        Create an object that listens continuously for Pixelblaze beacon
        packets, maintains a list of Pixelblazes and supports synchronizing time
        on multiple Pixelblazes to allows them to run patterns simultaneously.
        Takes the IPv4 address of the interface to use for listening on the calling computer.
        Listens on all available interfaces if addr is not specified.
        """
        self.start(hostIP)

    def __del__(self):
        self.stop()

    def _unpack_beacon(self, data):
        """
        Utility Method: Unpacks data from a Pixelblaze beacon
        packet, returning a 3 element list which contains
        (packet_type, sender_id, sender_time)
        """
        return struct.unpack("<LLL", data)

    def _pack_timesync(self, now, sender_id, sender_time):
        """
        Utility Method: Builds a Pixelblaze timesync packet from
        supplied data.
        """
        return struct.pack("<LLLLL", self.TIMESYNC_PACKET, self.SYNC_ID,
                           now, sender_id, sender_time)

    def _set_timesync_id(self, id):
        """Utility Method:  Sets the PixelblazeEnumerator object's network
           id for time synchronization. At the moment, any 32 bit value will
           do, and calling this method does (almost) nothing.  In the
           future, the ID might be used to determine priority among multiple time sources.
        """
        self.SYNC_ID = id

    def setDeviceTimeout(self, ms):
        """
        Sets the interval in milliseconds which the enumerator will wait without
        hearing from a device before removing it from the active devices list.

        The default timeout is 30000 (30 seconds).
        """
        self.DEVICE_TIMEOUT = ms

    def enableTimesync(self):
        """
        Instructs the PixelblazeEnumerator object to automatically synchronize
        time on all Pixelblazes. (Note that time synchronization
        is off by default when a new PixelblazeEnumerator is created.)
        """
        self.autoSync = True

    def disableTimesync(self):
        """
        Turns off the time synchronization -- the PixelblazeEnumerator will not
        automatically synchronize Pixelblazes.
        """
        self.autoSync = False

    def start(self, hostIP):
        """
        Open socket for listening to Pixelblaze datagram traffic,
        set appropriate options and bind to specified interface and
        start listener thread.
        """
        try:
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener.bind((hostIP, self.PORT))

            self.threadObj = threading.Thread(target=self._listen)
            self.isRunning = True
            self.listTimeoutCheck = 0
            self.threadObj.start()

            return True
        except socket.error as e:
            print(e)
            self.stop()
            return False

    def stop(self):
        """
        Stop listening for datagrams, terminate listener thread and close socket.
        """
        if self.listener is None:
            return
        else:
            self.isRunning = False
            self.threadObj.join()
            time.sleep(0.5)
            self.listener.close()
            self.threadObj = None
            self.listener = None

    def _send_timesync(self, now, sender_id, sender_time, addr):
        """
        Utility Method: Composes and sends a timesync packet to a single Pixelblaze
        """
        try:
            self.listener.sendto(self._pack_timesync(now, sender_id, sender_time), addr)

        except socket.error as e:
            print(e)
            self.stop()

    def _listen(self):
        """
        Internal Method: Datagram listener thread handler -- loop and listen.
        """

        while self.isRunning:
            data, addr = self.listener.recvfrom(1024)
            now = self._time_in_millis()

            # check the list periodically,and remove devices we haven't seen in a while
            if (now - self.listTimeoutCheck) >= self.LIST_CHECK_INTERVAL:
                newlist = dict()

                for dev, record in self.devices.items():
                    if (now - record["timestamp"]) <= self.DEVICE_TIMEOUT:
                        newlist[dev] = record

                self.devices = newlist
                self.listTimeoutCheck = now

            # when we receive a beacon packet from a Pixelblaze,
            # update device record and timestamp in our device list
            pkt = self._unpack_beacon(data)
            if pkt[0] == self.BEACON_PACKET:
                # add pixelblaze to list of devices
                self.devices[pkt[1]] = {"address": addr,
                                        "timestamp": now,
                                        "sender_id": pkt[1],
                                        "sender_time": pkt[2]}

                # immediately send timesync if enabled
                if self.autoSync: # send
                    self._send_timesync(now, pkt[1], pkt[2], addr)

            elif pkt[0] == self.TIMESYNC_PACKET:   # always defer to other time sources
                if self.autoSync:
                    self.disableTimesync()

    def getPixelblazeList(self):
        dev = []
        for record in self.devices.values():
            dev.append(record["address"][0])  # just the ip
        return dev
