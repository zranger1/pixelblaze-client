#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
A library that provides a simple, synchronous interface for communicating with and controlling Pixelblaze LED controllers.

This module contains the following classes:

- [`Pixelblaze`](#class-pixelblaze): an object for controlling Pixelblazes.

- [`PBB`](#class-pbb): an object for creating and manipulating Pixelblaze Binary Backups.

- [`PBP`](#class-pbp): an object for creating and manipulating Pixelblaze Binary Patterns.

- [`EPE`](#class-epe): an object for creating and manipulating Electromage Pattern Exports.
"""

# ----------------------------------------------------------------------------
# Copyright 2020-2025 by the pixelblaze-client team
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
# to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
# BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
# AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# ----------------------------------------------------------------------------

__version__ = "1.1.6"

# | Version | Date       | Author        | Comment
# |---------|------------|---------------|--------------------------------------------------
# |  v1.1.6 | 09/02/2025 | TheMariday,   | Fix expander data bug, remove unused imports
# |         |            | zwily,        | replace py-mini-racer with mini-racer
# |         |            | zranger1      |
# |  v1.1.5 | 02/23/2025 | m@bustos.org  | Add socket timeout to lightweight enumerator
# |  v1.1.4 | 08/27/2024 | zranger1      | Update pattern compilation for new firmware
# |  v1.1.3 | 03/01/2023 | savdb         | Enhance mapping functionality
# |  v1.1.2 | 02/22/2023 | zranger1      | Bug fix for long-lived connections
# |  v1.1.1 | 02/15/2023 | zranger1      | Minor bug fix for Windows
# |  v1.1.0 | 12/25/2022 | @pixie        | Added pattern and map compilation functions
# |  v1.0.2 | 11/06/2022 | @pixie        | Bug fixes, added new map functions
# |  v1.0.1 | 11/04/2022 | zranger1      | Bug fixes, revisions to compatibility functions
# |  v1.0.0 | 10/10/2022 | @pixie        | large-scale refactoring to add new features; minor loss of compatibility
# |  v0.9.6 | 07/17/2022 | @pixie        | Tweak getPatternList() to handle slower Pixelblazes
# |  v0.9.5 | 07/16/2022 | @pixie        | Update ws_recv to receive long preview packets
# |  v0.9.4 | 02/04/2022 | zranger1      | Added setPixelcount(), pause(), unpause(), pattern cache
# |  v0.9.3 | 04/13/2021 | zranger1      | waitForEmptyQueue() return now agrees w/docs
# |  v0.9.2 | 01/16/2021 | zranger1      | Updated Pixelblaze sequencer support
# |  v0.9.1 | 12/16/2020 | zranger1      | Support for pypi upload
# |  v0.9.0 | 12/06/2020 | zranger1      | Added PixelblazeEnumerator class
# |  v0.0.2 | 12/01/2020 | zranger1      | Name change + color control methods
# |  v0.0.1 | 11/20/2020 | zranger1      | Created
# ----------------------------------------------------------------------------

#   Standard library imports.
import sys
import socket

import select
import errno
import json
import time
import threading
import math
import random
import base64
import binascii
import struct
import pathlib
import pytz
import traceback
import gzip
from typing import Union
from enum import Enum, Flag, IntEnum, IntFlag
from urllib.parse import urlparse, urljoin

#   Related third party imports.
import websocket
import requests
from py_mini_racer import MiniRacer


#   Local application/library specific imports.
#   -None-

# ----------------------------------------------------------------------------
#
#   ██████╗ ██╗██╗  ██╗███████╗██╗     ██████╗ ██╗      █████╗ ███████╗███████╗
#   ██╔══██╗██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██║     ██╔══██╗╚══███╔╝██╔════╝
#   ██████╔╝██║ ╚███╔╝ █████╗  ██║     ██████╔╝██║     ███████║  ███╔╝ █████╗
#   ██╔═══╝ ██║ ██╔██╗ ██╔══╝  ██║     ██╔══██╗██║     ██╔══██║ ███╔╝  ██╔══╝
#   ██║     ██║██╔╝ ██╗███████╗███████╗██████╔╝███████╗██║  ██║███████╗███████╗
#   ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝
#   ╔╦╗┬ ┬┌─┐  ╔═╗┬─┐ ┬┌─┐┬  ┌┐ ┬  ┌─┐┌─┐┌─┐  ╦ ╦┌─┐┌┐ ┌─┐┌─┐┌─┐┬┌─┌─┐┌┬┐  ╔═╗╔═╗╦
#    ║ ├─┤├┤   ╠═╝│┌┴┬┘├┤ │  ├┴┐│  ├─┤┌─┘├┤   ║║║├┤ ├┴┐└─┐│ ││  ├┴┐├┤  │   ╠═╣╠═╝║
#    ╩ ┴ ┴└─┘  ╩  ┴┴ └─└─┘┴─┘└─┘┴─┘┴ ┴└─┘└─┘  ╚╩╝└─┘└─┘└─┘└─┘└─┘┴ ┴└─┘ ┴   ╩ ╩╩  ╩
#
class Pixelblaze:
    """
    The Pixelblaze class presents a simple synchronous interface to a single Pixelblaze's websocket API.

    The constructor takes the Pixelblaze's IPv4 address in the usual 12 digit numeric form (for example, "192.168.4.1"). To control multiple Pixelblazes, create multiple objects.

    The objective is to provide 99% coverage of the functionality of the Pixelblaze webUI, and so the supported methods are named and grouped according to the tabs of the webUI:

    **CREATION**

    - [`__init__()`](#method-init)
    - [`EnumerateAddresses()`](#method-enumerateaddresses)
    - [`EnumerateDevices()`](#method-enumeratedevices)

    **PATTERNS tab**

    *SEQUENCER section*

    - [`getSequencerMode`](#method-getSequencerMode)/[`setSequencerMode`](#method-setSequencerMode)
    - [`getSequencerState`](#method-getSequencerState)/[`setSequencerState`](#method-setSequencerState)
    - [`getSequencerShuffleTime`](#method-getSequencerShuffleTime)/[`setSequencerShuffleTime`](#method-setSequencerShuffleTime)
    - [`getSequencerPlaylist`](#method-getSequencerPlaylist)/[`addToSequencerPlaylist`](#method-addToSequencerPlaylist)/[`setSequencerPlaylist`](#method-setSequencerPlaylist)

    *SAVED PATTERNS section*

    - [`getPatternList`](#method-getPatternList)
    - [`getActivePattern`](#method-getActivePattern)/[`setActivePattern`](#method-setActivePattern)
    - [`getActiveVariables`](#method-getActiveVariables)/[`setActiveVariables`](#method-setActiveVariables)
    - [`getActiveControls`](#method-getActiveControls)/[`setActiveControls`](#method-setActiveControls)
    - [`deletePattern`](#method-deletePattern)
    - [`getPatternAsEpe`](#method-getPatternAsEpe)

    **EDIT tab**

    - [`getPatternControls`](#method-getPatternControls)
    - [`getPatternSourceCode`](#method-getPatternSourceCode)
    - [`sendPatternToRenderer`](#method-sendPatternToRenderer)
    - [`savePattern`](#method-savePattern)

    **MAPPER tab**
    - [`createMapData`](#method-createMapData)
    - [`getMapFunction`](#method-getMapFunction)/[`setMapFunction`](#method-setMapFunction)
    - [`getMapData`](#method-getMapData)/[`setMapData`](#method-setMapData)

    **SETTINGS tab**

    - [`getConfigSettings`](#method-getConfigSettings)
    - [`getConfigSequencer`](#method-getConfigSequencer)
    - [`getConfigExpander`](#method-getConfigExpander)

    ***NAME section***

    - [`getDeviceName`](#method-getDeviceName)/[`setDeviceName`](#method-setDeviceName)
    - [`getDiscovery`](#method-getDiscovery)/[`setDiscovery`](#method-setDiscovery)
    - [`getTimezone`](#method-getTimezone)/[`setTimezone`](#method-setTimezone)
    - [`getAutoOffEnable`](#method-getAutoOffEnable)/[`setAutoOffEnable`](#method-setAutoOffEnable)
    - [`getAutoOffStart`](#method-getAutoOffStart)/[`setAutoOffStart`](#method-setAutoOffStart)
    - [`getAutoOffEnd`](#method-getAutoOffEnd)/[`setAutoOffEnd`](#method-setAutoOffEnd)

    ***LED section***

    - [`getBrightnessLimit`](#method-getBrightnessLimit)/[`setBrightnessLimit`](#method-setBrightnessLimit)
    - [`getLedType`](#method-getLedType)/[`setLedType`](#method-setLedType)
    - [`getPixelCount`](#method-getPixelCount)/[`setPixelCount`](#method-setPixelCount)
    - [`getDataSpeed`](#method-getDataSpeed)/[`setDataSpeed`](#method-setDataSpeed)
    - [`getColorOrder`](#method-getColorOrder)/[`setColorOrder`](#method-setColorOrder)
    - [`getCpuSpeed`](#method-getCpuSpeed)/[`setCpuSpeed`](#method-setCpuSpeed)
    - [`getNetworkPowerSave`](#method-getNetworkPowerSave)/[`setNetworkPowerSave`](#method-setNetworkPowerSave)

    ***UPDATES section***

    - [`getUpdateState`](#method-getUpdateState)/[`installUpdate`](#method-installUpdate)
    - [`getVersion`](#method-getVersion)/[`getVersionMajor`](#method-getVersionMajor)/[`getVersionMinor`](#method-getVersionMinor)/

    ***BACKUPS section***

    - [`saveBackup`](#method-saveBackup)/[`restoreFromBackup`](#method-restoreFromBackup)
    - [`reboot`](#method-reboot)

    **ADVANCED tab**

    - [`getBrandName`](#method-getBrandName)/[`setBrandName`](#method-setBrandName)
    - [`getSimpleUiMode`](#method-getSimpleUiMode)/[`setSimpleUiMode`](#method-setSimpleUiMode)
    - [`getLearningUiMode`](#method-getLearningUiMode)/[`setLearningUiMode`](#method-setLearningUiMode)

    **GLOBAL CONTROLS**

    - [`getBrightnessSlider`](#method-getBrightnessSlider)/[`setBrightnessSlider`](#method-setBrightnessSlider)

    **LOW-LEVEL SEND/RECEIVE**

    - [`wsReceive`](#method-wsreceive)
    - [`wsSendJson`](#method-wssendjson)
    - [`wsSendBinary`](#method-wssendbinary)

    **FILESYSTEM**

    - [`getFileList`](#method-getfilelist)
    - [`getFile`](#method-getfile)/[`putFile`](#method-putfile)/[`deleteFile`](#method-deletefile)

    **STATISTICS**

    - [`getStatistics`](#method-getStatistics)
    - [`getFPS`](#method-getFPS)
    - [`getUptime`](#method-getUptime)
    - [`getStorageSize`](#method-getStorageSize)
    - [`getStorageUsed`](#method-getStorageUsed)

    """

    # --- PRIVATE DATA
    default_recv_timeout = 1
    max_open_retries = 5
    ws = None
    connected = False
    ipAddress = None
    proxyUrl = None
    proxyDict = None

    # Pattern cache
    cacheRefreshTime = 0
    cacheRefreshInterval = 1000  # milliseconds used internally
    patternCache = None

    # Parser state cache
    latestStats = None
    latestSequencer = None
    latestExpander = None
    latestVersion = None
    latestUpdateCheck = None
    connectionBroken = False

    # --- OBJECT LIFETIME MANAGEMENT (CREATION/DELETION)

    def __init__(self, ipAddress: str, ignoreOpenFailure: bool = False, *, proxyUrl: str = None):
        """Initializes an object for communicating with and controlling a Pixelblaze.

        Args:
            ipAddress (str): The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1").
            ignoreOpenFailure (bool, optional): If True, the constructor will create the Pixelblaze object and not raise an exception
                if connection to the Pixelblaze can't be established. (The connection will be retried on any subsequent
                attempts to send to, or receive from, the Pixelblaze.) Defaults to False.
            proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port"
            (for example, "http://192.168.0.1:8888"). Defaults to None.
        """
        self.proxyUrl = proxyUrl
        if not proxyUrl is None:
            self.proxyDict = {"http": proxyUrl, "https": proxyUrl}
        self.ipAddress = ipAddress
        self.setCacheRefreshTime(600)  # seconds used in public api

        # try to connect to the Pixelblaze.  If we can't, raise an exception unless ignoreOpenFailure is True.
        try:
            self._open()
        except Exception:
            if not ignoreOpenFailure:
                raise

    def __enter__(self):
        """Internal class method for resource management.

        Returns:
            Pixelblaze: This object.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Internal class method for resource management.

        Args:
            exc_type (_type_): As per Python standard.
            exc_value (_type_): As per Python standard.
            traceback (_type_): As per Python standard.
        """
        # Make sure we clean up after ourselves.
        if not self is None: self._close()

    # --- STATIC METHODS

    class LightweightEnumerator:
        """Internal implementation class for the [`EnumerateAddresses`](#method-enumerateaddresses) and [`EnumerateDevices`](#method-enumeratedevices) methods."""

        # Enumerated type for the type of the Enumerator.
        class EnumeratorTypes(IntEnum):
            """Enumerator to specify the desired LightweightEnumerator type."""
            noType = 0  # Not used
            ipAddress = 1  # An enumerator that returns the IP Address of any Pixelblazes found.
            pixelblazeObject = 2  # An enumerator that returns a Pixelblaze object for any Pixelblazes found.

        # Members:
        listenSocket = None
        timeout = 0
        timeStop = 0
        seenPixelblazes = []
        enumeratorType = EnumeratorTypes.noType
        proxyUrl = None

        # private constructor:
        def __init__(self, enumeratorType: EnumeratorTypes, *, timeout: int = 1500, proxyUrl: str = None,
                     hostIP: str = "0.0.0.0"):
            """
            Create an iterable object that listens for Pixelblaze beacon packets, returning a Pixelblaze object for each unique beacon seen during the timeout period.

            Args:
                enumeratorType (EnumeratorTypes): Which of the available enumerator types to create.
                hostIP (str, optional): The network interface on which to listen for Pixelblazes. Defaults to "0.0.0.0" meaning all available interfaces.
                timeout (int, optional): The amount of time in milliseconds to listen for a new Pixelblaze to announce itself (They announce themselves once per second). Defaults to 1500.
                proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None.

            Note:
                This method is not intended to be called directly; use the static methods [`EnumerateAddresses`](#method-enumerateaddresses) or [`EnumerateDevices`](#method-enumeratedevices) to create and return an iterator object.
            """
            try:
                self.enumeratorType = enumeratorType
                self.timeout = timeout
                self.proxyUrl = proxyUrl
                self.listenSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.listenSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.listenSocket.settimeout(timeout / 1000.0)
                self.listenSocket.bind((hostIP, 1889))
            except socket.error as e:
                print(e)

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
                try:
                    data, ipAddress = self.listenSocket.recvfrom(1024)
                    pkt = struct.unpack("<LLL", data)
                    if pkt[0] == 42:  # beacon packet
                        if ipAddress not in self.seenPixelblazes:
                            # Add this address to our list so we don't repeat it.
                            self.seenPixelblazes.append(ipAddress)
                            # Return an enumerator of the appropriate type.
                            if self.enumeratorType == Pixelblaze.LightweightEnumerator.EnumeratorTypes.ipAddress:
                                return ipAddress[0]
                            elif self.enumeratorType == Pixelblaze.LightweightEnumerator.EnumeratorTypes.pixelblazeObject:
                                return Pixelblaze(ipAddress[0], proxyUrl=self.proxyUrl)
                            else:
                                # No such type...How did that happen?
                                raise
                except socket.timeout:
                    raise StopIteration

            # Exit because the timeout has expired.
            raise StopIteration

        def _time_in_millis(self) -> int:
            """
            Utility Method: Returns last 32 bits of the current time in milliseconds
            """
            return int(round(time.time() * 1000)) % 0xFFFFFFFF

    # Static methods:
    @staticmethod
    def EnumerateAddresses(*, timeout: int = 1500, proxyUrl: str = None,
                           hostIP: str = "0.0.0.0") -> LightweightEnumerator:
        """Returns an enumerator that will iterate through all the Pixelblazes on the local network, until {timeout} milliseconds have passed with no new devices appearing.

        Args:
            hostIP (str, optional): The network interface on which to listen for Pixelblazes. Defaults to "0.0.0.0" meaning all available interfaces.
            timeout (int, optional): The amount of time in milliseconds to listen for a new Pixelblaze to announce itself (They announce themselves once per second). Defaults to 1500.
            proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None.

        Returns:
            LightweightEnumerator: A subclassed Python enumerator object that returns (as a string) the IPv4 address of a Pixelblaze, in the usual dotted-quads numeric format.
        """
        return Pixelblaze.LightweightEnumerator(Pixelblaze.LightweightEnumerator.EnumeratorTypes.ipAddress,
                                                timeout=timeout, proxyUrl=proxyUrl, hostIP=hostIP)

    @staticmethod
    def EnumerateDevices(*, timeout: int = 1500, proxyUrl: str = None,
                         hostIP: str = "0.0.0.0") -> LightweightEnumerator:
        """Returns an enumerator that will iterate through all the Pixelblazes on the local network, until {timeout} milliseconds have passed with no new devices appearing.

        Args:
            hostIP (str, optional): The network interface on which to listen for Pixelblazes. Defaults to "0.0.0.0" meaning all available interfaces.
            timeout (int, optional): The amount of time in milliseconds to listen for a new Pixelblaze to announce itself (They announce themselves once per second). Defaults to 1500.
            proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None.

        Returns:
            LightweightEnumerator: A subclassed Python enumerator object that returns a Pixelblaze object for controlling a discovered Pixelblaze.
        """
        return Pixelblaze.LightweightEnumerator(Pixelblaze.LightweightEnumerator.EnumeratorTypes.pixelblazeObject,
                                                timeout=timeout, proxyUrl=proxyUrl, hostIP=hostIP)

    # --- CONNECTION MANAGEMENT

    def _open(self):
        """
        Opens a websocket connection to the Pixelblaze.

        This is called automatically when a Pixelblaze object is created; it is not necessary to explicitly
        call open to connect unless the websocket has been explicitly closed by the user previously.
        """
        if self.connected is False:
            uri = "ws://" + self.ipAddress + ":81"
            retryCount = 0
            while True:
                try:
                    if self.proxyUrl is not None:
                        url = urlparse(self.proxyUrl)
                        self.ws = websocket.create_connection(uri, sockopt=(
                        (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1), (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)),
                                                              proxy_type=url.scheme, http_proxy_host=url.hostname,
                                                              http_proxy_port=url.port)
                    else:
                        self.ws = websocket.create_connection(uri, sockopt=(
                        (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1), (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),))
                    break
                except websocket._exceptions.WebSocketConnectionClosedException:
                    # print("Open failed.  Retry # ",retryCount)
                    retryCount += 1
                    if retryCount >= self.max_open_retries:
                        raise

            self.ws.settimeout(self.default_recv_timeout)
            self.connected = True
            self._connection_maint()
            # Reset our caches so we'll get them afresh.
            self.latestStats = None
            self.latestUpdateCheck = None
            self.latestVersion = None
            self.latestSequencer = None
            self.latestExpander = None

    def _close(self):
        """Close websocket connection."""
        if self.connected is True:
            self.ws.close()
            self.connected = False

    # --- LOW-LEVEL SEND/RECEIVE

    class messageTypes(IntEnum):
        """Types of binary messages sent and received by a Pixelblaze.  The first byte of a binary frame contains the message type."""
        putSourceCode = 1  # from client to PB
        putByteCode = 3  # from client to PB
        previewImage = 4  # from client to PB
        previewFrame = 5  # from PB to client
        getSourceCode = 6  # from PB to client
        getProgramList = 7  # from client to PB
        putPixelMap = 8  # from client to PB
        ExpanderConfig = 9  # from client to PB *and* PB to client
        # SPECIAL MESSAGE TYPES: These aren't part of the Pixelblaze protocol; they're flags for the state machine.
        specialConfig = -1
        specialStats = -2

    class frameTypes(Flag):
        """Continuation flags for messages sent and received by a Pixelblaze.  The second byte of a binary frame tells whether this packet is part of a set."""
        frameNone = 0
        frameFirst = 1
        frameMiddle = 2
        frameLast = 4

    def wsReceive(self, *, binaryMessageType: messageTypes = None) -> Union[str, bytes, None]:
        """Wait for a message of a particular type from the Pixelblaze.

        Args:
            binaryMessageType (messageTypes, optional): The type of binary message to wait for (if None, waits for a text message). Defaults to None.

        Returns:
            Union[str, bytes, None]: The message received from the Pixelblaze (of type bytes for binaryMessageTypes, otherwise of type str), or None if a timeout occurred.
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
                        if binaryMessageType is self.messageTypes.specialStats: return frame
                    elif frame.startswith('{"activeProgram":'):
                        self.latestSequencer = frame
                        if binaryMessageType is self.messageTypes.specialConfig: return frame
                    # We wanted a text frame, we got a text frame.
                    elif binaryMessageType is None:
                        return frame
                else:
                    frameType = frame[0]
                    if frameType == self.messageTypes.previewFrame.value:
                        # This packet type doesn't have frameType flags.
                        if binaryMessageType == self.messageTypes.previewFrame:
                            return frame[19:]
                        else:
                            continue  # We weren't looking for a preview frame, so ignore it.

                    # Check the flags to see if we need to read more packets.
                    frameFlags = frame[1]
                    if message is None and not (
                            frameFlags & self.frameTypes.frameFirst.value): raise  # The first frame must be a start frame
                    if message is not None and (
                            frameFlags & self.frameTypes.frameFirst.value): raise  # We shouldn't get a start frame after we've started
                    if message is None:
                        message = frame[2:]  # Start with the first packet...
                    else:
                        message += frame[2:]  # ...and append the rest until we reach the end.

                    # If we've received all the packets, deal with the message.
                    if frameFlags & self.frameTypes.frameLast.value:
                        # Expander config frames are ONLY sent during a config request, but they sometimes arrive
                        # out of order so we'll save them and retrieve them separately.
                        if frameType == self.messageTypes.ExpanderConfig:
                            self.latestExpander = self.__decodeExpanderData(frame[2:])
                            if binaryMessageType == self.messageTypes.specialConfig: return message
                            continue
                        if frameType != binaryMessageType:
                            # print(f"got unwanted binary frame type {frameType} (wanted {binaryMessageType})")
                            traceback.print_stack()
                            continue  # skip this unwanted binary frame (which shouldn't really happen anyway)
                        return message

            except websocket._exceptions.WebSocketTimeoutException:  # timeout -- we can just ignore this
                endTime = self._time_in_millis()
                if (endTime - startTime) > (1000 * self.default_recv_timeout):
                    return None

            except websocket._exceptions.WebSocketConnectionClosedException:  # try reopening
                # print("wsReceive reconnection")
                self.connectionBroken = True
                self._close()
                self._open()

            except IOError as e:
                # add test for WinError 10054 - existing connection reset
                if e.errno == errno.EPIPE or e.errno == 10054:
                    self.connectionBroken = True
                    self._close()
                    self._open()

            except Exception as e:
                self.connectionBroken = True
                traceback.print_stack()
                # print(f"wsReceive: unknown exception: {e}")
                raise

    def sendPing(self) -> Union[str, None]:
        """Send a Ping message to the Pixelblaze and wait for the Acknowledgement response.

        Returns:
            Union[str, None]: The acknowledgement message received from the Pixelblaze, or None if a timeout occurred.
        """
        return self.wsSendJson({"ping": True}, expectedResponse="ack")

    def _connection_maint(self):
        """
        Flush receive buffer and see that connection handshake is maintained.
        This is needed to keep the connection alive during extended sessions
        where the application is mostly sending data to the Pixelblaze

        It keeps the receive buffer clear of stray packets, and since connection maintenance
        is handled by ws.recv(), keeps the connection alive.  Otherwise it'll time out and hang or
        disconnect after about 10 minutes.
        """
        while True:
            ready = select.select([self.ws.sock], [], [], 0)
            if not ready[0]:
                break
            try:
                self.ws.recv()
            except:
                raise

    def wsSendJson(self, command: dict, *, expectedResponse=None) -> Union[str, bytes, None]:
        """Send a JSON-formatted command to the Pixelblaze, and optionally wait for a suitable response.

        Args:
            command (dict): A Python dictionary which will be sent to the Pixelblaze as a JSON command.
            expectedResponse (str, optional): If present, the initial key of the expected JSON response to the command. Defaults to None.

        Returns:
            Union[str, bytes, None]: The message received from the Pixelblaze (of type bytes for binaryMessageTypes, otherwise of type str), or None if a timeout occurred.
        """
        self.connectionBroken = False
        while True:
            try:
                self._open()  # make sure it's open, even if it closed while we were doing other things.
                self._connection_maint()
                self.ws.send(json.dumps(command, indent=None, separators=(',', ':')).encode("utf-8"))

                if expectedResponse is None:
                    return None

                    # If the pipe broke while we were sending, restart from the beginning.
                if self.connectionBroken: break

                # Wait for the expected response.
                while True:
                    # Loop until we get the right text response.
                    if type(expectedResponse) is str:
                        if expectedResponse == "activeProgram":
                            response = self.wsReceive(binaryMessageType=self.messageTypes.specialConfig)
                        else:
                            response = self.wsReceive(binaryMessageType=None)
                        if response is None: break
                        if response.startswith(f'{{"{expectedResponse}":'): break
                    # Or the right binary response.
                    elif type(expectedResponse) is self.messageTypes:
                        response = self.wsReceive(binaryMessageType=expectedResponse)
                        break
                # Now that we've got the right response, return it.
                return response

            except websocket._exceptions.WebSocketConnectionClosedException:
                self.connectionBroken = True
                self._close()
                self._open()  # try reopening

            except IOError as e:
                # add test for WinError 10054 - existing connection reset
                if e.errno == errno.EPIPE or e.errno == 10054:
                    self.connectionBroken = True
                    self._close()
                    self._open()

            except:
                self.connectionBroken = True
                self._close()
                self._open()  # try reopening
                # raise

    def wsSendBinary(self, binaryMessageType: messageTypes, blob: bytes, *, expectedResponse: str = None):
        """Send a binary command to the Pixelblaze, and optionally wait for a suitable response.

        Args:
            binaryMessageType (messageTypes, optional): The type of binary message to send.
            blob (bytes): The message body to be sent.
            expectedResponse (str, optional): If present, the initial key of the expected JSON response to the command. Defaults to None.

        Returns:
            response: The message received from the Pixelblaze (of type bytes for binaryMessageTypes, otherwise of type str), or None if a timeout occurred.
        """
        self.connectionBroken = False
        while True:
            try:
                # Break the frame into manageable chunks.
                response = None
                maxFrameSize = 8192  ### the webUI source code says limit for v2 is 1024 but this still works...
                if binaryMessageType == self.messageTypes.putByteCode: maxFrameSize = 1280
                for i in range(0, len(blob), maxFrameSize):

                    # Set the frame header values.
                    frameHeader = bytearray(2)
                    frameHeader[0] = binaryMessageType.value
                    frameFlag = self.frameTypes.frameNone
                    if i == 0: frameFlag |= self.frameTypes.frameFirst
                    if (len(blob) - i) <= maxFrameSize:
                        frameFlag |= self.frameTypes.frameLast
                    else:
                        frameFlag = self.frameTypes.frameMiddle
                    frameHeader[1] = frameFlag.value

                    # Send the packet.
                    self._connection_maint()
                    self.ws.send_binary(bytes(frameHeader) + blob[i:i + maxFrameSize])

                    # If the pipe broke while we were sending, restart from the beginning.
                    if self.connectionBroken: break

                    # Wait for the expected response.
                    while True:
                        # Loop until we get the right text response.
                        if type(expectedResponse) is str:
                            response = self.wsReceive(binaryMessageType=None)
                            if response is None: break
                            if response.startswith(f'{{"{expectedResponse}":'): break
                        # Or the right binary response.
                        elif type(expectedResponse) is self.messageTypes:
                            response = self.wsReceive(binaryMessageType=expectedResponse)
                            break
                # Now that we've sent all the chunks, return the last status received.
                return response

            except websocket._exceptions.WebSocketConnectionClosedException:
                # print("wsSendBinary reconnection")
                # try reopening
                self.connectionBroken = True
                self._close()
                self._open()

            except IOError as e:
                # add test for WinError 10054 - existing connection reset
                if e.errno == errno.EPIPE or e.errno == 10054:
                    self.connectionBroken = True
                    self._close()
                    self._open()

            except:
                # print("wsSendBinary received unexpected exception")
                # try reopening
                self.connectionBroken = True
                self._close()
                self._open()
                # raise

    def getPeers(self):
        """A new command, added to the API but not yet implemented as of v2.29/v3.24, that will return a list of all the Pixelblazes visible on the local network segment.

        Returns:
            TBD: To be defined once @wizard implements the function.
        """
        self.wsSendJson({"getPeers": True})
        return self.wsReceive(binaryMessageType=None)

    # --- PIXELBLAZE FILESYSTEM FUNCTIONS:

    def getUrl(self, endpoint: str = None) -> str:
        """Build the URL to communicate with the Pixelblaze using an HTTP endpoint.

        Args:
            endpoint (str, optional): The HTTP endpoint. Defaults to None, which returns the URL of the Pixelblaze webUI.

        Returns:
            str: The URL of the HTTP endpoint on the Pixelblaze.
        """
        return urljoin(f"http://{self.ipAddress}", endpoint)

    class fileTypes(IntFlag):
        """A Pixelblaze contains Patterns, PatternSettings, Configs, Playlists, System and Other types of files."""
        fileConfig = 1
        filePattern = 2
        filePatternSetting = 4
        filePlaylist = 8
        fileSystem = 16
        fileOther = 32
        fileAll = fileConfig | filePattern | filePatternSetting | filePlaylist | fileSystem | fileOther

    def getFileList(self, fileTypes: fileTypes = fileTypes.fileAll) -> list[str]:
        """Returns a list of all the files of a particular type stored on the Pixelblaze's filesystem.

        For Pixelblazes running firmware versions lower than 2.29/3.24 (the point at which
        the necessary API was introduced), the list includes the names of optional configuration
        files that may or may not exist on a particular Pixelblaze, depending on its setup.

        Args:
            fileTypes (fileTypes, optional): A bitmasked enumeration of the fileTypes to be listed. Defaults to fileTypes.fileAll.

        Returns:
            list[str]: A list of filenames of the requested fileType.
        """
        fileList = []
        with requests.get(self.getUrl("list"), proxies=self.proxyDict) as rList:
            if rList.status_code == 200:
                for line in rList.text.split('\n'):
                    fileName = line.split('\t')[
                        0]  # '/list' returns a number of lines, each containing [filename][tab][size][newline]
                    if len(fileName) > 0: fileList.append(fileName)  # '/list' returns a blank line at the end.
            elif rList.status_code == 404:
                # If the Pixelblaze doesn't support the "/list" endpoint, get the patternList using WebSocket calls.
                fileList = []
                for fileName in self.getPatternList():
                    fileList.append(f"/p/{fileName}")  # the pattern blob
                    fileList.append(f"/p/{fileName}.c")  # the current value of any (optional) UI controls
                # Append the names of all the other files a Pixelblaze might contain, some of which may not exist on any particular device.
                for fileName in ["apple-touch-icon.png", "favicon.ico", "config.json", "obconf.dat", "pixelmap.txt",
                                 "pixelmap.dat", "l/_defaultplaylist_"]:
                    fileList.append(f"/{fileName}")
            else:
                rList.raise_for_status()

        # Filter the list depending on the fileTypes requested.
        for fileName in list(fileList):
            # fileConfigs:
            if fileName[1:] in ["config.json", "config2.json", "obconf.dat", "pixelmap.txt", "pixelmap.dat"]:
                if not bool(fileTypes & self.fileTypes.fileConfig):
                    fileList.remove(fileName)
            # filePatterns and filePatternSettings:
            elif fileName.startswith("/p/"):
                if fileName.endswith(".c"):
                    # filePatternSettings:
                    if not bool(fileTypes & self.fileTypes.filePatternSetting):
                        fileList.remove(fileName)
                else:
                    # filePattern:
                    if not bool(fileTypes & self.fileTypes.filePattern):
                        fileList.remove(fileName)
            # filePlaylists:
            elif fileName.startswith("/l/"):
                if not bool(fileTypes & self.fileTypes.filePlaylist):
                    fileList.remove(fileName)
            # fileSystem:
            elif fileName.endswith(".gz"):
                if not bool(fileTypes & self.fileTypes.fileSystem):
                    fileList.remove(fileName)
            # fileOthers:
            else:
                # Ignore the blank line returned by the '/list' endpoint.
                if not bool(fileTypes & self.fileTypes.fileOther):
                    fileList.remove(fileName)

        # Return the filtered list.
        fileList.sort()
        return fileList

    def getFile(self, fileName: str) -> bytes:
        """Downloads a file from the Pixelblaze using the HTTP API.

        Args:
            fileName (str): The pathname (as returned from `getFileList`) of the file to be downloaded.

        Returns:
            bytes: The contents of the file.
        """
        with requests.get(self.getUrl(fileName), proxies=self.proxyDict) as rGet:
            if rGet.status_code not in [200, 404]:
                rGet.raise_for_status()
            if rGet.status_code != 200: return None
            return rGet.content

    def putFile(self, fileName: str, fileContents: bytes) -> bool:
        """Uploads a file to the Pixelblaze using the HTTP API.

        Args:
            fileName (str): The pathname at which to store the file.
            fileContents (bytes): The data to store in the file.

        Returns:
            bool: True if the file was successfully stored; False otherwise.
        """
        fileData = {'data': (fileName, fileContents)}
        with requests.post(self.getUrl("edit"), files=fileData, proxies=self.proxyDict) as rPost:
            if rPost.status_code != 200:
                rPost.raise_for_status()
                return False
        return True

    def deleteFile(self, fileName: str) -> bool:
        """Deletes a file from this Pixelblaze using the HTTP API.

        Args:
            fileName (str): The pathname (as returned from `getFileList`) of the file to be deleted.

        Returns:
            bool: True if the file was successfully stored; False otherwise.
        """
        with requests.get(self.getUrl(f"delete?path={fileName}"), proxies=self.proxyDict) as rFile:
            if rFile.status_code not in [200, 404]:
                rFile.raise_for_status()
                return False
        return True

    # --- GLOBAL functions: RENDERER STATISTICS:

    def getStatistics(self) -> dict:
        """Grab one of the statistical packets that Pixelblaze sends every second.

        Returns:
            dict: the JSON message received from the Pixelblaze.
        """
        self.setSendPreviewFrames(True)  # Make sure the Pixelblaze will send something.
        while True:
            if not self.latestStats is None: return json.loads(self.latestStats)
            ignored = self.wsReceive(binaryMessageType=self.messageTypes.specialStats)

    def setSendPreviewFrames(self, doUpdates: bool):
        """Set whether or not the Pixelblaze sends pattern preview frames.

        Args:
            doUpdates (bool): True sends preview frames, False stops.
        """
        assert type(doUpdates) is bool
        if doUpdates is True:
            response = self.messageTypes.previewFrame
        else:
            response = None
        self.wsSendJson({"sendUpdates": doUpdates}, expectedResponse=response)

    def getPreviewFrame(self) -> bytes:
        """Grab one of the preview frames that Pixelblaze sends after every render cycle.

        Returns:
            bytes: a collection of bytes representing `pixelCount` tuples containing the (R, G, B) values for each pixel in the pattern preview.
        """
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

    def getFPS(self, savedStatistics: dict = None) -> float:
        """Return the speed (in Frames per Second) of the pattern rendering.

        Args:
            savedStatistics (dict, optional): If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None.

        Returns:
            int: The pattern speed in FPS, as reported in a Pixelblaze statistics message.
        """
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('fps')

    def getUptime(self, savedStatistics: dict = None) -> int:
        """Return the uptime (in seconds) of the Pixelblaze.

        Args:
            savedStatistics (dict, optional): If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None.

        Returns:
            int: The uptime in seconds, as reported in a Pixelblaze statistics message.
        """
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('uptime')

    def getStorageUsed(self, savedStatistics: dict = None) -> int:
        """Return the amount of Flash storage used on the Pixelblaze.

        Args:
            savedStatistics (dict, optional): If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None.

        Returns:
            int: The used storage in bytes, as reported in a Pixelblaze statistics message.
        """
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('storageUsed')

    def getStorageSize(self, savedStatistics: dict = None) -> int:
        """Return the available Flash storage on the Pixelblaze.

        Args:
            savedStatistics (dict, optional): If provided, extracts the value from the results of a previous call to 'getStatistics`; otherwise, fetches the statistics from the Pixelblaze anew.  Defaults to None.

        Returns:
            int: The available storage in bytes, as reported in a Pixelblaze statistics message.
        """
        if savedStatistics is None: savedStatistics = self.getStatistics()
        return savedStatistics.get('storageSize')

    # --- GLOBAL functions: CONTROLS (available on all tabs):

    def setBrightnessSlider(self, brightness: float, *, saveToFlash: bool = False):
        """Set the value of the UI brightness slider.

        Args:
            brightness (float): A floating-point value between 0.0 and 1.0.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"brightness": self._clamp(brightness, 0, 1), "save": saveToFlash}, expectedResponse=None)

    # --- GLOBAL functions: CONTROLS: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings from the Pixelblaze anew."""

    def getBrightnessSlider(self, configSettings: dict = None) -> float:
        """Get the value of the UI brightness slider.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            float: A floating-point value between 0.0 and 1.0.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('brightness')

    # --- PATTERNS tab: SEQUENCER section

    class sequencerModes(IntEnum):
        Off = 0
        ShuffleAll = 1
        Playlist = 2

    def setSequencerMode(self, sequencerMode: sequencerModes, *, saveToFlash: bool = False):
        """Sets the sequencer mode to one of the available sequencerModes (Off, ShuffleAll, or Playlist).

        Args:
            sequencerMode (enum): The desired sequencer mode.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"sequencerMode": sequencerMode, "save": saveToFlash}, expectedResponse=None)

    def setSequencerState(self, sequencerState: bool, saveToFlash: bool = False):
        """Set the run state of the sequencer.

        Args:
            sequencerState (bool): A boolean value determining whether or not the sequencer should run.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"runSequencer": sequencerState}, expectedResponse=None)

    # --- PATTERNS tab: SEQUENCER section: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getSequencerMode(self, configSequencer: dict = None) -> sequencerModes:
        """Gets the current sequencer mode.

        Args:
            configSequencer (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None.

        Returns:
            sequencerModes: The sequencerMode.
        """
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get('sequencerMode')

    def getSequencerState(self, configSequencer: dict = None) -> bool:
        """Gets the current sequencer run state.

        Args:
            configSequencer (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None.

        Returns:
            bool: True if the sequencer is running; False otherwise.
        """
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get('runSequencer')

    # --- PATTERNS tab: SEQUENCER section: SHUFFLE ALL mode

    def playSequencer(self, *, saveToFlash: bool = False):
        """Mimics the 'Play' button in the UI. Starts the pattern sequencer,
        the consequences of which will vary depending upon the sequencerMode.

        Args:
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.setSequencerState(True, saveToFlash)

    def pauseSequencer(self, *, saveToFlash: bool = False):
        """Mimics the 'Pause' button in the UI.  Pauses the pattern sequencer,
        without changing the current position in the shuffle or playlist.
        Has no effect if the sequencer is not currently running.

        Args:
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.setSequencerState(False, saveToFlash)

    def nextSequencer(self, *, saveToFlash: bool = False):
        """Mimics the 'Next' button in the UI.  If the sequencerMode is ShuffleAll or Playlist, advances the pattern sequencer to the next pattern.

        Args:
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"nextProgram": True, "save": saveToFlash}, expectedResponse=None)

    def setSequencerShuffleTime(self, nMillis: int, *, saveToFlash: bool = False):
        """Sets the time the Pixelblaze's sequencer will run each pattern before switching to the next.

        Args:
            nMillis (int): The number of milliseconds to play each pattern.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"sequenceTimer": nMillis, "save": saveToFlash}, expectedResponse=None)

    # --- PATTERNS tab: SEQUENCER section: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getSequencerShuffleTime(self, configSequencer: dict = None) -> int:
        """Gets the time the Pixelblaze's sequencer will run each pattern before switching to the next.

        Args:
            configSequencer (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None.

        Returns:
            int: The number of milliseconds to play each pattern.
        """
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get("ms")

    # --- PATTERNS tab: SEQUENCER section: PLAYLIST mode

    def getSequencerPlaylist(self, playlistId: str = "_defaultplaylist_"):
        """Fetches the specified playlist.  At the moment, only the default playlist is supported by the Pixelblaze.

        Args:
            playlistId (str, optional): The name of the playlist (for future enhancement; currently only '_defaultplaylist_' is supported). Defaults to "_defaultplaylist_".

        Returns:
            dict: The contents of the playlist.
        """
        return json.loads(self.wsSendJson({"getPlaylist": playlistId}, expectedResponse="playlist"))

    def setSequencerPlaylist(self, playlistContents: dict, playlistId: str = "_defaultplaylist_"):
        """Replaces the entire contents of the specified playlist.  At the moment, only the default playlist is supported by the Pixelblaze.

        Args:
            playlistContents (dict): The new playlist contents.
            playlistId (str, optional): The name of the playlist (for future enhancement; currently only '_defaultplaylist_' is supported). Defaults to "_defaultplaylist_".
        """
        self.latestSequencer = None  # clear cache to force refresh
        ignored = self.wsSendJson(playlistContents, expectedResponse=None)

    def addToSequencerPlaylist(self, playlistContents: dict, *, patternId: str, duration: int) -> dict:
        """Appends a new entry to the specified playlist.

        Args:
            patternId (str): The patternId of the pattern to be played.
            duration (int): The number of milliseconds to play the pattern.
            playlistContents (dict): The results of a previous call to `getSequencerPlaylist`.

        Returns:
            dict: The updated playlist, which can then be sent back to the Pixelblaze with `setSequencerPlaylist`.
        """
        playlistContents.get('playlist').get('items').append({'id': patternId, 'ms': duration})
        return playlistContents

    # --- PATTERNS tab: SAVED PATTERNS section

    def getPatternList(self, forceRefresh: bool = False) -> dict:
        """Returns a list of all the patterns saved on the Pixelblaze.

        Normally reads from the cached pattern list, which is refreshed every 10 minutes by default. To change the cache refresh interval, call setCacheRefreshTime(seconds).

        Args:
            forceRefresh (bool, optional): Forces a refresh of the cached patternList. Defaults to False.

        Returns:
            dict: A dictionary of the patterns stored on the Pixelblaze, where the patternId is the key and the patternName is the value.
        """
        if forceRefresh is True or ((self._time_in_millis() - self.cacheRefreshTime) > self.cacheRefreshInterval):
            # Update the patternList cache.
            newPatternCache = dict()
            oldTimeout = self.ws.gettimeout()
            self.ws.settimeout(3 * self.default_recv_timeout)
            response = self.wsSendJson({"listPrograms": True}, expectedResponse=self.messageTypes.getProgramList)
            self.ws.settimeout(oldTimeout)
            if response is not None:
                for pattern in [m.split("\t") for m in response.decode("utf-8").split("\n")]:
                    if len(pattern) == 2:
                        newPatternCache[pattern[0]] = pattern[1]
                self.patternCache = newPatternCache
            self.cacheRefreshTime = self._time_in_millis()

        # Return the cached list.
        return self.patternCache

    def setActivePattern(self, patternId: str, *, saveToFlash: bool = False):
        """Sets the active pattern.

        Args:
            patternId (str): The patternId of the desired pattern.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        """Functionality changed."""
        if len(patternId) != 17: self.__printDeprecationMessage(self.deprecationReasons.functionalityChanged,
                                                                "setActivePattern(name_or_id)",
                                                                "setActivePattern(id)/setActivePatternByName(name")
        self.wsSendJson({"activeProgramId": patternId, "save": saveToFlash}, expectedResponse="activeProgram")

    def getPatternAsEpe(self, patternId: str) -> str:
        """Convert a stored pattern into an exportable, portable JSON format (which then needs to be saved by the caller).

        Args:
            patternId (str): The patternId of the desired pattern.

        Returns:
            str: The exported pattern as a JSON dictionary.
        """
        # Request the pattern elements from the Pixelblaze and combine them into an EPE.
        epe = {
            'name': self.getPatternList(refresh=True).get(patternId, "Unknown Pattern"),
            'id': patternId,
            'sources': json.loads(self.getPatternSourceCode(patternId)),
            'preview': base64.b64encode(self.getPreviewImage(patternId)).decode('UTF-8')
        }
        return json.dumps(epe, indent=2)

    def deletePattern(self, patternId: str):
        """Delete a pattern saved on the Pixelblaze.

        Args:
            patternId (str): The patternId of the desired pattern.
        """
        self.wsSendJson({"deleteProgram": patternId}, expectedResponse=None)

    def getPreviewImage(self, patternId: str) -> bytes:
        """Gets the preview image (a JPEG with 150 iterations of the pattern) saved within a pattern.

        Args:
            patternId (str): The patternId of the desired pattern.

        Returns:
            bytes: A JPEG image in which each column represents a particular LED and each row represents an iteration of the pattern.
        """
        return self.wsSendJson({"getPreviewImg": patternId}, expectedResponse=self.messageTypes.previewImage)

    def getActiveVariables(self) -> dict:
        """Gets the names and values of all variables exported by the current pattern.

        Returns:
            dict: A dictionary containing all the variables exported by the active pattern, with variableName as the key and variableValue as the value.
        """
        return json.loads(self.wsSendJson({"getVars": True}, expectedResponse="vars")).get('vars')

    def setActiveVariables(self, dictVariables: dict):
        """Sets the values of one or more variables exported by the current pattern.

        Variables not present in the current pattern are ignored.

        Args:
            dictVariables: A dictionary containing the variables to be set, with variableName as the key and variableValue as the value.
        """
        self.wsSendJson({"setVars": dictVariables}, expectedResponse=None)

    def setActiveControls(self, dictControls: dict, *, saveToFlash: bool = False):
        """Sets the value of one or more UI controls exported from the active pattern.

        Args:
            dictControls (dict): A dictionary containing the values to be set, with controlName as the key and controlValue as the value.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"setControls": dictControls, "save": saveToFlash}, expectedResponse="ack")

    # --- PATTERNS tab: SAVED PATTERNS section: convenience functions
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getActivePattern(self, configSequencer: dict = None) -> str:
        """Returns the ID of the pattern currently running on the Pixelblaze.

        Args:
            configSequencer (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None.

        Returns:
            str: The patternId of the current pattern, if any; otherwise an empty string.
        """
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get('activeProgram').get('activeProgramId', '')

    def getActiveControls(self, configSequencer: dict = None) -> dict:
        """Returns the collection of controls for the pattern currently running on the Pixelblaze.

        If there are no controls or no pattern has been set, returns an empty dictionary.

        Args:
            configSequencer (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSequencer`; otherwise, fetches the configSequencer from the Pixelblaze anew. Defaults to None.

        Returns:
            dict: A dictionary containing the control names and values, with controlName as the key and controlValue as the value.
        """
        if configSequencer is None: configSequencer = self.getConfigSequencer()
        return configSequencer.get('activeProgram', {}).get('controls', {})

    # --- EDIT tab:

    def getPatternControls(self, patternId: str) -> dict:
        """Returns the name and value of any UI controls exported by the specified pattern.

        Args:
            patternId (str): The patternId of the pattern.

        Returns:
            dict: A dictionary containing the control names and values, with controlName as the key and controlValue as the value.
        """
        response = self.wsSendJson({"getControls": patternId}, expectedResponse="controls")
        if not response is None: return json.loads(response)
        return None

    def getPatternSourceCode(self, patternId: str) -> str:
        """Gets the sourceCode of a saved pattern from the Pixelblaze.

        Args:
            patternId (str): The patternId of the desired pattern.

        Returns:
            str: A string representation of a JSON dictionary containing the pattern source code.
        """
        sources = self.wsSendJson({"getSources": patternId}, expectedResponse=self.messageTypes.getSourceCode)
        if sources is not None: return _LZstring.decompress(sources)
        return None

    def compilePattern(self, patternCode: str) -> bytes:
        """Compiles pattern sourcecode into a bytecode blob.

        Args:
            patternCode (str): The PBscript sourcecode of the pattern.

        Returns:
            bytes: a compiled blob of bytecode, ready to send to the Pixelblaze using `sendPatternToRenderer()`.
        """

        # Firmware-dependent adapters.
        def getSubstring(text: str, startValue: str, endValue: str):
            start = text.index(startValue)
            finish = text.index(endValue, start)
            return text[start:finish]

        def extractCompiler(webUI: str):
            # Search through the script blocks to find the compiler module.
            while len(webUI) > 0:
                before, during, after = webUI.partition("<script>")
                script, during, webUI = after.partition("</script>")
                # Find the compiler.
                if script.find("window.compile") != -1:
                    return script

        def v2Adapter(webUI: str):
            # Extract the model-dependent constants from the webUI.
            components = {}
            components["hardwareVariant"] = ""
            components["extendedOperators"] = getSubstring(webUI, "extendedOperators={", ",constants=")
            components["constants"] = getSubstring(webUI, "constants=", ",lastErrorMarkers=[],")
            components["compiler"] = extractCompiler(webUI)
            return components

        def v3AdapterV1(webUI: str):
            # Extract the model-dependent constants from the webUI.
            components = {}
            components["hardwareVariant"] = getSubstring(webUI, "var hardwareVariant=", ",")
            components["extendedOperators"] = getSubstring(webUI, "extendedOperators={", "var constants;")
            components["constants"] = getSubstring(webUI, "var constants;", "var lastErrorMarkers=[],")
            components["compiler"] = extractCompiler(webUI)
            return components

        def v3AdapterV2(webUI: str):
            # Extract the model-dependent constants from the webUI.
            components = {}
            components["hardwareVariant"] = getSubstring(webUI, "var hardwareVariant=", "$('")
            components["extendedOperators"] = getSubstring(webUI, "extendedOperators={", "var constants;")
            components["constants"] = getSubstring(webUI, "var constants;", "var lastErrorMarkers=[],")
            components["compiler"] = extractCompiler(webUI)
            return components

        ",[])"

        def v3AdapterV3(webUI: str):
            # Extract the model-dependent constants from the webUI.
            components = {}
            components["hardwareVariant"] = "var " + getSubstring(webUI, "hardwareVariant=", ",varWatcherPoller") + ";"
            components["extendedOperators"] = getSubstring(webUI, "extendedOperators={", ",lastErrorMarkers=") + ";"
            components["constants"] = "var constants;" + getSubstring(webUI, '"ESP8266"===hardwareVariant&&',
                                                                      ",[])") + ";"
            components["compiler"] = extractCompiler(webUI) + ";"
            return components

        # Determine which adapter to use based on the firmware version.
        def getAdapter(version: float):
            # print("Version is: ", version)
            if version < 3.0:
                # print("Using v2Adapter")
                return v2Adapter
            elif version <= 3.20:
                # print("Using v3AdapterV1")
                return v3AdapterV1
            elif version <= 3.4:
                # print("Using v3AdapterV2")
                return v3AdapterV2
            else:
                # print("Using v3AdapterV3")
                return v3AdapterV3

        # Download the webUI from the Pixelblaze and extract the pieces we need for compilation.
        webUI = gzip.decompress(self.getFile("/index.html.gz")).decode('utf-8-sig')
        version = self.getVersion()
        # DEBUG BLOCK -- REMOVE BEFORE COMMITTING
        # print(webUI.encode('utf-8-sig'))
        # quit(0)
        # DEBUG BLOCK -- REMOVE BEFORE COMMITTING
        components = getAdapter(float(version))(webUI)
        # print("Hardware Variant: ", components["hardwareVariant"].encode('utf-8-sig'))
        # print("Constants: ", components["constants"].encode('utf-8'))
        # print("Extended Operators: ", components["extendedOperators"].encode('utf-8'))
        # print("Compiler: ", components["compiler"].encode('utf-8-sig'))

        # Build up the compilation environment from bits and pieces.
        compiler = 'window = {};\nvar predefinedGlobals = ["pixelCount"];\n' + components["hardwareVariant"] + '\n' + \
                   components["constants"] + '\n' + components["extendedOperators"] + '\n' + components[
                       "compiler"] + '\n' + """
            const compilePattern = (src) => {
                try {
                    compilerOptions = { predefinedGlobals: predefinedGlobals, extendedOperators: extendedOperators, constants: constants }
                    program = window.compile(src, compilerOptions);

                    //  Get rid of a few recursive properties that inhibit serialization.
                    delete program.parent; delete program.breaks; delete program.continues; delete program.placeholders; delete program.placeholder;
                    program.blocks.forEach(function (v) { delete v.parent; delete v.breaks; delete v.continues; delete v.placeholders; delete v.placeholder; });
                    program.sourceBits.forEach(function (v) { delete v.short; v.start = {}; v.end = {}; });
                    program.sourceBits.forEach(function (v) { if (v.loc != null) for (const [key, value] of Object.entries(v.loc.start)) { v.start[key] = value; } });
                    program.sourceBits.forEach(function (v) { if (v.loc != null) for (const [key, value] of Object.entries(v.loc.end)) { v.end[key] = value; } });
                    program.sourceBits.forEach(function (v) { delete v.loc; });

                    //  Rearrange a few properties for easier access from Python.
                    function surfaceList(list) { temp = Object.keys(list).reduce(function (r, k) { return r.concat(list[k]); }, []); return temp; }
                    program.exports = surfaceList(program.exports);
                    program.identifiers = surfaceList(program.identifiers);
                    program.blocks.forEach(function (v) { v.identifiers = surfaceList(v.identifiers); })

                    return { "status": "OK", "program": program }
                }
                catch (ex) {
                    return { "status": ex.description + " at line " + ex.lineNumber.toString() + " column " + ex.column.toString(), "program": {} }
                }
            }
            """

        # Load the compiler into the interpreter.
        ctx = MiniRacer()
        ctx.eval(compiler)

        # Use the interpreter to run the compiler to convert the sourcecode into the bytecode.
        # set up MiniRacer to give detailed error messages

        result = ctx.call("compilePattern", patternCode)
        if result["status"] != "OK":
            raise ValueError(f'Compilation error: {result["status"]}')

        # Build the results into a bytecode packet.
        program = result["program"]

        # We first need to build the EXPORTS table to determine its size.
        exportSize = 0
        for symbol in program["exports"]: exportSize += 4 + len(symbol["name"]) + 1

        # First DWORD is the size in bytes of the OPCODES section.
        bytecode = int.to_bytes(4 * len(program["compiled"]), 4, "little")

        # Second DWORD is the size in bytes of the EXPORTS section.
        bytecode += int.to_bytes(exportSize, 4, "little")

        # Then come the OPCODES themselves...
        for opcode in program["compiled"]:
            bytecode += int.to_bytes(opcode, 4, "little", signed=True)

        # ...And finally the EXPORTS.
        for symbol in program["exports"]:
            bytecode += int.to_bytes(symbol["address"], 4, "little")
            bytecode += bytes(symbol["name"], "ascii") + int.to_bytes(0, 1, "little")

        # save flag.  (apparently new with v3.5-ish firmware
        # bytecode += int.to_bytes(0, 1, "little")

        # Return the completed bytecode blob.
        return bytecode

    def makeId(self):
        e = "23456789ABCDEFGHJKLMNPQRSTWXYZabcdefghijkmnopqrstuvwxyz"
        # build a 17-character ID consisting of characters from the list above
        return ''.join(random.choice(e) for _ in range(17))

    def calculate_crc32(self, data):
        return binascii.crc32(data) & 0xffffffff

    def sendPatternToRenderer(self, bytecode: bytes, controls: dict = {}):
        """Sends a blob of bytecode and a JSON dictionary of UI controls to the Renderer. Mimics the actions of the webUI code editor.

        Args:
            bytecode (bytes): A valid blob of bytecode as generated by the Editor tab in the Pixelblaze webUI.
            controls (dict, optional): a dictionary of UI controls exported by the pattern, with controlName as the key and controlValue as the value. Defaults to {}.
        """
        # NOTE: crc may only be needed for v3.5+ firmware, but doesn't seem to hurt other versions
        crcVal = self.calculate_crc32(bytecode)
        self.wsSendJson(
            {"pause": True, "setCode": {"size": len(bytecode), "crc": crcVal, "name": "", "id": self.makeId()}},
            expectedResponse="ack")
        self.wsSendBinary(self.messageTypes.putByteCode, bytecode, expectedResponse="ack")
        time.sleep(0.25)
        self.wsSendJson({"setControls": controls})
        self.wsSendJson({"pause": False}, expectedResponse="ack")
        time.sleep(0.25)

    def savePattern(self, *, previewImage: bytes, sourceCode: str, byteCode: bytes):
        """Saves a new pattern to the Pixelblaze filesystem.  Mimics the effects of the 'Save' button.

        If you don't know how to generate the previewImage and byteCode components, you don't want to do this.

        Args:
            previewImage (bytes): A JPEG image in which each column represents a particular LED and each row represents an iteration of the pattern.
            sourceCode (str): A string representation of a JSON dictionary containing the pattern source code.
            byteCode (bytes): A valid blob of bytecode as generated by the Editor tab in the Pixelblaze webUI.
        """
        self.wsSendBinary(self.messageTypes.previewImage, previewImage, expectedResponse="ack")
        self.wsSendBinary(self.messageTypes.putSourceCode, _LZstring.compress(sourceCode), expectedResponse="ack")
        self.wsSendBinary(self.messageTypes.putByteCode, byteCode, expectedResponse="ack")

    # --- MAPPER tab: Pixelmap settings

    def getMapFunction(self) -> str:
        """Returns the mapFunction text used to populate the Mapper tab in the Pixelblaze UI.

        Returns:
            str: The text of the mapFunction.
        """
        return self.getFile("/pixelmap.txt")

    def setMapCoordinates(self, mapCoordinates: list) -> bool:
        """Sets raw coordinates for the map

        Note that setting the coordinates also compiles and updates the mapData
        used by the Pixelblaze.

        Args:
            mapCoordinates (list): A list-of-lists containing the map coordinates

        Returns:
            bool: True if the function text was successfully saved; otherwise False.
        """
        mapData = self.createMapData(mapCoordinates)
        mapFunction = str(mapCoordinates)
        self.putFile('/pixelmap.txt', mapFunction)
        self.putFile('/pixelmap.dat', mapData)
        return self.setMapData(mapData)

    def setMapFunction(self, mapFunction: str) -> bool:
        """Sets the mapFunction text used to populate the Mapper tab in the Pixelblaze UI.

        Note that setting the map function also compiles and updates the mapData
        used by the Pixelblaze.

        Args:
            mapFunction (str): The text of the mapFunction.

        Returns:
            bool: True if the function text was successfully saved; otherwise False.
        """
        # Call the mapping function and get the pixelmap.
        mapCoordinates = MiniRacer().call(mapFunction, self.getPixelCount())
        mapData = self.createMapData(mapCoordinates)
        self.putFile('/pixelmap.txt', mapFunction)
        self.putFile('/pixelmap.dat', mapData)
        return self.setMapData(mapData)

    def createMapData(self, mapCoordinates: list) -> bytes:
        """Returns binary mapData based on a list of coordinates.

        Args:
            mapCoordinates (list): A list-of-lists containing the map coordinates

        Returns:
            bytes: The binary mapData generated by this function
        """
        numPixels = len(mapCoordinates)
        numDimensions = len(mapCoordinates[0])

        # Normalize the pixelmap coordinates.
        maxValue = [sys.float_info.min, sys.float_info.min, sys.float_info.min]
        minValue = [sys.float_info.max, sys.float_info.max, sys.float_info.max]
        for pixel in range(numPixels):
            for dimension in range(numDimensions):
                maxValue[dimension] = max(maxValue[dimension], mapCoordinates[pixel][dimension])
                minValue[dimension] = min(minValue[dimension], mapCoordinates[pixel][dimension])

        # Build a mapData structure for consumption by the Pixelblaze.
        formatVersion = self.getVersionMajor() - 1  # v3 uses version 2; v2 uses version 1
        maxInt = pow(2, 8 * formatVersion) - 1
        mapData = int.to_bytes(formatVersion, 4, 'little')
        mapData += int.to_bytes(numDimensions, 4, 'little')
        mapData += int.to_bytes(numPixels * numDimensions * formatVersion, 4, 'little')
        for pixel in range(numPixels):
            for dimension in range(numDimensions):
                # Rescale the elements appropriately.
                value = int(maxInt * ((mapCoordinates[pixel][dimension] - minValue[dimension]) / (
                            maxValue[dimension] - minValue[dimension])))
                mapData += int.to_bytes(value, int(formatVersion), 'little', signed=False)
        return mapData

    def getMapData(self) -> bytes:
        """Gets the binary representation of the pixelMap entered on the 'Mapper' tab.

        Returns:
            bytes: The binary mapData as generated by the Mapper tab of the Pixelblaze webUI.
        """
        return self.getFile('/pixelmap.dat')

    def setMapData(self, mapData: bytes, *, saveToFlash: bool = True):
        """Sets the binary mapData used by the Pixelblaze.

        Args:
            mapData (bytes): a blob of binary mapData as generated by the Mapper tab of the Pixelblaze webUI.
            saveToFlash (bool, optional): A boolean indicating whether the mapData should be saved to Flash. Defaults to True.
        """
        # Send the mapData...
        self.wsSendBinary(self.messageTypes.putPixelMap, mapData, expectedResponse="ack")
        # ...and make it permanent (same as pressing "Save" in the map editor).
        if saveToFlash: self.wsSendJson({"savePixelMap": True}, expectedResponse=None)

    def getMapCoordinates(self, mapData: bytes = None) -> list:
        """Gets a unit-normalized representation of the pixelMap as an array (1D/2D/3D) of arrays.

        Args:
            mapData (bytes, optional): A blob of mapData as returned from getMapData(); if omitted, the mapData will be fetched from the Pixelblaze anew.

        Returns:
            list: A list containing one to three lists of floats, representing the X, Y and Z world coordinates (range 0..1) for each pixel.
        """
        # Get the pixelCount because we'll need it for one thing or another.
        pixelCount = self.getPixelCount()

        # If no mapData was provided, fetch it from the Pixelblaze.
        if mapData is None: mapData = self.getMapData()

        # If no map has been defined, generate and return a 1D map with the pixels spaced at regular intervals.
        if mapData is None:
            return [list((pixel / (pixelCount - 1)) for pixel in range(pixelCount))]

        # Parse the mapData to build the worldMap.
        headerSize = 3 * 4  # first 3 longwords are the header.
        offsets = struct.unpack('<3I', mapData[:headerSize])
        fileVersion = offsets[0]
        numDimensions = offsets[1]
        dataSize = offsets[2]
        wordSize = fileVersion * 1  # v1 uses uint8, v2 uses uint16
        numElements = dataSize // wordSize // numDimensions
        # If the number of elements in the worldMap doesn't match the pixelCount, it's stale and needs to be refreshed.
        if (numElements != pixelCount):
            raise ValueError("Map does not match pixelCount; re-save map and try again.")

        # Read in the list of 8- or 16-bit coordinates
        worldMap = []
        exponent = pow(2, 8 * wordSize)
        format = f"<{numDimensions}{'BH'[wordSize - 1]}"
        for tuple in struct.iter_unpack(format, mapData[headerSize:]):
            for dimension in range(numDimensions):
                value = tuple[dimension] / (exponent - 1)
                if len(worldMap) < dimension + 1: worldMap.append([])
                worldMap[dimension].append(value)

        # Return the resulting worldMap.
        return worldMap

    def getMapOffsets(self, mapCoordinates: list = None) -> list:
        """Gets an integer-based representation of the pixelMap as an array (1D/2D/3D) of arrays.

        Args:
            mapCoordinates (list, optional): A list of mapCoordinates as returned from getMapCoordinates(); if omitted, the mapCoordinates will be fetched from the Pixelblaze anew.

        Returns:
            list: A list containing one to three lists of integers, representing the X, Y and Z indices (range 0..pixelCount) for each pixel.
        """
        # Get the worldMap.
        if mapCoordinates is None: mapCoordinates = self.getMapCoordinates()
        numElements = len(mapCoordinates[0])

        # Analyze the sparseness of the points in the worldMap.
        minValue = []
        maxValue = []
        minDelta = []
        for dimension in range(len(mapCoordinates)):
            sortedMap = sorted(mapCoordinates[dimension])
            minValue.append(min(sortedMap))
            maxValue.append(max(sortedMap))
            minDelta.append(1.0)
            for element in range(len(mapCoordinates[dimension])):
                delta = abs(sortedMap[element] - sortedMap[(element + 1) % numElements])
                if delta > 0: minDelta[dimension] = min(minDelta[dimension], delta)

        # Rescale the elements in this dimension appropriately.
        offsetMap = []
        for dimension in range(len(mapCoordinates)):
            offsetMap.append([])
            for element in range(len(mapCoordinates[dimension])):
                offsetMap[dimension].append(
                    round((mapCoordinates[dimension][element] - minValue[dimension]) / minDelta[dimension]))

        # Return the resulting map.
        return offsetMap

    # --- SETTINGS menu

    def getConfigSettings(self) -> dict:
        """Returns the configuration as defined on the Settings tab of the Pixelblaze.

        Returns:
            dict: A dictionary containing the configuration settings, with settingName as the key and settingValue as the value.
        """
        # In response to this command, the Pixelblaze actually returns three separate messages representing the
        # configuration of the Settings page, the configuration of the Sequencer and the configuration of the outputExpander (if it exists).
        # The Settings configuration is a JSON message and always comes first; the Sequencer configuration (a JSON message)
        # and the OutputExpander configuration (a binary message) can come in either order so we have to be flexible in what we accept.
        self.latestSequencer = None  # clear cache to force refresh
        self.latestExpander = None  # clear cache to force refresh

        # First the config packet.
        settings = {}
        while True:
            self.wsSendJson({"getConfig": True}, expectedResponse=None)
            response = self.wsReceive(binaryMessageType=None)
            if not response is None:
                settings = json.loads(response)
                break

        # Now the others, in any order.
        while True:
            ignored = self.wsReceive(binaryMessageType=self.messageTypes.specialConfig)
            # If we've got both packets, exit the loop.
            if (not self.latestSequencer is None) and (not self.latestExpander is None): break
            # If we timed out waiting for an expanderConfig, there mustn't be one configured so give up.
            if self.latestSequencer is not None and ignored is None: break

        # Now that we've got them all, return the settings.
        return settings

    def getConfigSequencer(self) -> dict:
        """Retrieves the Sequencer state.

        Returns:
            dict: The sequencer configuration as a dictionary, with settingName as the key and settingValue as the value.
        """
        self.latestSequencer = None
        while True:
            if self.latestSequencer is None: ignored = self.getConfigSettings()
            return json.loads(self.latestSequencer)

    def getConfigExpander(self) -> dict:
        """Retrieves the OutputExpander configuration.

        Returns:
            dict: The OutputExpander configuration as a dictionary, with settingName as the key and settingValue as the value.
        """
        while True:
            if not self.latestExpander is None: return self.latestExpander
            ignored = self.getConfigSettings()

    def __decodeExpanderData(self, data: bytes) -> dict:
        """An internal function to convert the OutputExpander from its native binary format into a human-readable JSON representation.

        Args:
            data (bytes): The binary OutputExpander blob received from the Pixelblaze.

        Returns:
            dict: A human-readable dictionary of the configuration items.
        """
        # Check that we support the version number.
        versionNumber = data[0]
        if versionNumber != 5:
            return {'expanders': [],
                    'error': f"expander data has incorrect magic number (expected 5, received {versionNumber})"}

        # Parse the rest of the data.
        binaryData = data[1:]
        binarySize = len(binaryData)
        if binarySize % 96 != 0:
            return {'expanders': [],
                    'error': f"expander data has incorrect length (must be a multiple of 96, received {versionNumber})"}

        # Convert the file to a human-readable equivalent.
        rowSize = 12
        boards = {'expanders': []}
        # ledTypes = [ 'notUsed', 'WS2812B', 'drawAll', 'APA102 Data', 'APA102 Clock' ]
        colorOrders = {0x24: 'RGB', 0x18: 'RBG', 0x09: 'BRG', 0x06: 'BGR', 0x21: 'GRB', 0x12: 'GBR', 0xE4: 'RGBW',
                       0xE1: 'GRBW'}
        for row in range(binarySize // rowSize):
            offsets = struct.unpack('<4B2H4x', binaryData[(row * rowSize):(row + 1) * rowSize])
            boardAddress = offsets[0] >> 3
            channel = offsets[0] % 8
            ledType = offsets[1]
            numElements = offsets[2]
            colorOrder = offsets[3]
            pixelCount = offsets[4]
            startIndex = offsets[5:7]
            dataSpeed = offsets[7:12]

            #   boardAddress
            #       channel | type | startIndex | pixelCount | colorOrder | dataSpeed
            board = row // 8
            rowNumber = row % 8
            if rowNumber == 0:  # start a new board
                boards['expanders'].append({'address': boardAddress, 'rows': {}})
            boards['expanders'][board]['rows'][rowNumber] = []
            if ledType == 1 or ledType == 3:
                boards['expanders'][board]['rows'][rowNumber].append(
                    {'channel': channel, 'type': ledType, 'numElements' : numElements, 'startIndex': startIndex,
                     'count': pixelCount,'options': colorOrders[colorOrder], 'dataSpeed': dataSpeed})
            else:
                boards['expanders'][board]['rows'][rowNumber].append({'channel': channel, 'type': ledType})

        # Return the finished configuration.
        return boards

    # --- SETTINGS menu: CONTROLLER section: NAME settings

    def setDeviceName(self, name: str):
        """Sets the device name of the Pixelblaze.

        Args:
            name (str): The human-readable name of the Pixelblaze.
        """
        self.wsSendJson({"name": name}, expectedResponse=None)

    def setDiscovery(self, enableDiscovery: bool, timezoneName: str = None):
        """Sets whether this Pixelblaze announces its presence to (and gets a clocktime reference from) the Electromage Discovery Service.

        Args:
            enableDiscovery (bool): A boolean controlling whether this Pixelblaze announces itself to the Electromage Discovery Service.
            timezoneName (str, optional): If present, a Unix tzstring specifying how to adjust the clocktime reference received from the Electromage Discovery Service. Defaults to None.
        """
        if timezoneName is not None:
            # Validate the timezone name.
            if not timezoneName in pytz.all_timezones:
                print(f"setDiscovery: unrecognized timezone {timezoneName}")
                return
        self.wsSendJson({"discoveryEnable": enableDiscovery, "timezone": timezoneName}, expectedResponse=None)

    def setTimezone(self, timezoneName: str):
        """Sets the Pixelblaze's timezone, which specifies how to adjust the clocktime reference provided by the Electromage Discovery Service.

        To clear the timezone, pass an empty string.

        Args:
            timezoneName (str): A Unix tzstring specifying how to adjust the clocktime reference provided by the Electromage Discovery Service.
        """
        if len(timezoneName) > 0:
            # Validate the timezone name.
            if not timezoneName in pytz.all_timezones: raise ValueError(
                f"setDiscovery: unrecognized timezone {timezoneName}")
        self.wsSendJson({"timezone": timezoneName}, expectedResponse=None)

    def setAutoOffEnable(self, boolValue: bool, *, saveToFlash: bool = False):
        """Enables or disables the Pixelblaze's auto-Off scheduler.

        Args:
            boolValue (bool): A boolean indicating whether the auto-Off scheduler should be used.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"autoOffEnable": boolValue, "save": saveToFlash}, expectedResponse=None)

    def setAutoOffStart(self, timeValue: str, saveToFlash: bool = False):
        """Sets the time at which the Pixelblaze will turn off the pattern.

        Args:
            timeValue (str): A Unix time string in "HH:MM" format.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        # if type(timeValue) is time: timeValue = timeValue.strftime('%H:%M')
        self.wsSendJson({"autoOffStart": timeValue, "save": saveToFlash}, expectedResponse=None)

    def setAutoOffEnd(self, timeValue: str, saveToFlash: bool = False):
        """Sets the time at which the Pixelblaze will turn on the pattern.

        Args:
            timeValue (str): A Unix time string in "HH:MM" format.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        # if type(timeValue) is time: timeValue = timeValue.strftime('%H:%M')
        self.wsSendJson({"autoOffEnd": timeValue, "save": saveToFlash}, expectedResponse=None)

    # --- SETTINGS menu: CONTROLLER section: NAME settings: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getDeviceName(self, configSettings: dict = None) -> str:
        """Returns the user-friendly name of the Pixelblaze.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            str: The user-friendly name of the Pixelblaze.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('name')

    def getDiscovery(self, configSettings: dict = None) -> bool:
        """
        Returns a boolean signifying whether the Pixelblaze announces itself to the Electromage Discovery Service.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            bool: A boolean signifying whether the Pixelblaze announces itself to the Electromage Discovery Service.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('discoveryEnable')

    def getTimezone(self, configSettings: dict = None) -> str:
        """Returns the timezone, if any, for the Pixelblaze.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            str: A standard Unix tzstring.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('timezone')

    def getAutoOffEnable(self, configSettings: dict = None) -> bool:
        """Returns whether the auto-Off timer is enabled.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            bool: A boolean indicating whether the auto-Off timer is enabled.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('autoOffEnable')

    def getAutoOffStart(self, configSettings: dict = None) -> str:
        """Returns the time, if any, at which the Pixelblaze will turn off the pattern when the auto-Off timer is enabled.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            str: A Unix time string in "HH:MM" format.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('autoOffStart')

    def getAutoOffEnd(self, configSettings: dict = None) -> str:
        """Returns the time, if any, at which the Pixelblaze will turn on the pattern when the auto-Off timer is enabled.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            str: A Unix time string in "HH:MM" format.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('autoOffEnd')

    # --- SETTINGS menu: CONTROLLER section: LED settings

    def setBrightnessLimit(self, maxBrightness: int, *, saveToFlash: bool = False):
        """Sets the Pixelblaze's global brightness limit.

        Args:
            maxBrightness (int): The maximum brightness, expressed as a percent value between 0 and 100 (yes, it's inconsistent with the 'brightness' settings).
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"maxBrightness": self._clamp(maxBrightness, 0, 100), "save": saveToFlash},
                        expectedResponse=None)

    class ledTypes(IntEnum):
        noLeds = 0
        APA102 = 1
        SK9822 = 1  # synonym for APA102
        DotStar = 1  # synonym for APA102
        unbufferedWS2812 = 2  # v2 type
        unbufferedSK6822 = 2  # v2 synonym for unbufferedWS2812
        unbufferedNeoPixel = 2  # v2 synonym for unbufferedWS2812
        WS2812 = 2  # v3 type
        SK6822 = 2  # v3 synonym for WS2812
        NeoPixel = 2  # v3 synonym for WS2812
        WS2801 = 3
        bufferedWS2812 = 4  # v2 only
        bufferedSK6822 = 4  # v2 synonym for bufferedWS2812
        bufferedNeoPixel = 4  # v2 synonym for bufferedWS2812
        OutputExpander = 5

    def setLedType(self, ledType: ledTypes, *, dataSpeed: int = None, saveToFlash: bool = False):
        """Defines the type of LEDs connected to the Pixelblaze.

        Args:
            ledType (ledTypes): The type of LEDs connected to the Pixelblaze.
            dataSpeed (int, optional): If provided, sets a custom data speed for communication with the LEDs; otherwise the defaults from the webUI are used. Defaults to None.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        assert type(ledType) is self.ledTypes
        # If no dataSpeed was specified, default to what the v3 UI sends.
        if dataSpeed is None:
            if ledType == self.ledTypes.noLeds: dataSpeed = None
            if ledType == self.ledTypes.APA102: dataSpeed = 2000000
            if ledType == self.ledTypes.WS2812: dataSpeed = 2250000  # 3500000 for v2
            if ledType == self.ledTypes.WS2801: dataSpeed = 2000000
            if ledType == self.ledTypes.bufferedWS2812: dataSpeed = 3500000
            if ledType == self.ledTypes.OutputExpander: dataSpeed = 2000000

        self.wsSendJson({"ledType": ledType, "dataSpeed": dataSpeed, "save": saveToFlash}, expectedResponse=None)

    def setPixelCount(self, nPixels: int, *, saveToFlash: bool = False):
        """Sets the number of LEDs attached to the Pixelblaze.

        Note that changing the number of pixels does not recalculate the pixelMap.

        Args:
            nPixels (int): The number of pixels.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        # TBD: The Pixelblaze UI also re-evaluates the map function and resends the map data...Should we do the same?
        self.wsSendJson({"pixelCount": nPixels, "save": saveToFlash}, expectedResponse=None)

    def setDataSpeed(self, speed: int, *, saveToFlash: bool = False):
        """Sets custom data rate for communicating with the LEDs.

        CAUTION: For advanced users only.  If you don't know exactly why you want to do this, DON'T DO IT.
        See discussion in this thread on the Pixelblaze forum: https://forum.electromage.com/t/timing-of-a-cheap-strand/739

        Args:
            speed (int): The data rate for communicating with the LEDs.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        self.wsSendJson({"dataSpeed": speed, "save": saveToFlash}, expectedResponse=None)

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

    def setColorOrder(self, colorOrder: colorOrders, *, saveToFlash: bool = False):
        """Sets the color order for the LEDs connected to the Pixelblaze.

        Args:
            colorOrder (colorOrders): The ordering for the color data sent to the LEDs.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        assert type(colorOrder) is self.colorOrders
        self.wsSendJson({"colorOrder": colorOrder.value, "save": saveToFlash}, expectedResponse=None)

    # --- SETTINGS menu: CONTROLLER section: LED settings: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getBrightnessLimit(self, configSettings: dict = None) -> int:
        """Returns the maximum brightness for the Pixelblaze.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            int: The maximum brightness, expressed as a percent value between 0 and 100 (yes, it's inconsistent with the 'brightness' settings).
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('maxBrightness', None)

    def getLedType(self, configSettings: dict = None) -> ledTypes:
        """Returns the type of LEDs connected to the Pixelblaze."""
        if configSettings is None: configSettings = self.getConfigSettings()
        return self.ledTypes(configSettings.get('ledType'))

    def getPixelCount(self, configSettings: dict = None) -> int:
        """Returns the number of LEDs connected to the Pixelblaze.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            int: The number of LEDs connected to the Pixelblaze.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('pixelCount', None)

    def getDataSpeed(self, configSettings: dict = None) -> int:
        """Returns the data speed of the LEDs connected to the Pixelblaze.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            int: The data speed for communicating with the LEDs.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('dataSpeed', None)

    def getColorOrder(self, configSettings: dict = None) -> colorOrders:
        """Returns the color order of the LEDs connected to the Pixelblaze.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            colorOrders: The ordering for the color data sent to the LEDs.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('colorOrder', None)

    # --- SETTINGS menu (v3 only): CONTROLLER section: POWER SAVING settings

    class cpuSpeeds(Enum):
        low = "80"
        medium = "160"
        high = "240"

    def setCpuSpeed(self, cpuSpeed: cpuSpeeds):
        """Sets the CPU speed of the Pixelblaze.

        Note that this setting will not take effect until the Pixelblaze is rebooted (which can be done with the `reboot` function).

        Args:
            cpuSpeed (cpuSpeeds): The desired CPU speed.
        """
        assert type(cpuSpeed) is self.cpuSpeeds
        # The "cpuSpeed" setting doesn't exist on v2, so ignore it if not v3.
        if (self.getConfigSettings().get('ver', '0').startswith('3')):
            self.wsSendJson({"cpuSpeed": cpuSpeed.value}, expectedResponse=None)

    def setNetworkPowerSave(self, disableWifi: bool):
        """Enables or disables the WiFi connection on the Pixelblaze, which can significantly reduce power requirements for battery-powered installations.

        Note that this setting will not take effect until the Pixelblaze is rebooted (which can be done with the `reboot` function).

        Args:
            disableWifi (bool): A boolean indicating whether to disable Wifi.
        """
        self.wsSendJson({"networkPowerSave": disableWifi}, expectedResponse=None)

    # --- GLOBAL functions: CONTROLS: helper functions:
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getCpuSpeed(self, configSettings: dict = None) -> cpuSpeeds:
        """Returns the CPU speed of the Pixelblaze.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            cpuSpeeds: An enumeration representing the CPU speed.
        """
        # The "cpuSpeed" setting doesn't exist on v2, so return the default.
        if configSettings is None: configSettings = self.getConfigSettings()
        return self.cpuSpeeds(configSettings.get('cpuSpeed', 240))

    def getNetworkPowerSave(self, configSettings: dict = None) -> bool:
        """Returns whether the "Network Power Saving" mode is enabled (and WiFi is disabled).

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            bool: Whether the "Network Power Saving" mode is enabled.
        """
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

    def getUpdateState(self) -> updateStates:
        """Returns the updateState of the Pixelblaze.

        Returns:
            updateStates: An enumeration describing the updateState of the Pixelblaze.
        """
        # We don't want to query the server every time, because changes don't happen very often.
        checkFrequency = 15 * 60 * 60 * 1000  # 15 minutes
        if self.latestUpdateCheck is None: self.latestUpdateCheck = self._time_in_millis() - (checkFrequency + 1)
        if (self._time_in_millis() - self.latestUpdateCheck) > checkFrequency:
            self.wsSendJson({"upgradeVersion": "check"}, expectedResponse=None)

        # Get the state. If it's indeterminate, wait until it resolves.
        state = self.wsSendJson({"getUpgradeState": True}, expectedResponse="upgradeState")
        while True:
            if state is None: return self.updateStates.unknown
            state = json.loads(state).get("upgradeState").get("code", 0)
            if state != self.updateStates.checking: return state
            state = self.wsSendJson({"getUpgradeState": True}, expectedResponse="upgradeState")

    def installUpdate(self) -> updateStates:
        """Installs new Pixelblaze firmware, if the current updateState indicates that an update is available.

        Returns:
            updateStates: An enumeration describing the new updateState of the Pixelblaze.
        """
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

    def getVersion(self) -> float:
        """Returns the firmware version of the Pixelblaze.

        Returns:
            float: The firmware version, in major.minor format.
        """
        if self.latestVersion is None:
            self.latestVersion = self.getConfigSettings().get('ver', None)
        return self.latestVersion

    def getVersionMajor(self) -> int:
        """Returns the major version number.

        Returns:
            int: A positive integer representing the integer portion of the version number (e.g. for v3.24, returns 3).
        """
        return math.trunc(float(self.getVersion()))

    def getVersionMinor(self) -> int:
        """Returns the minor version number.

        Returns:
            int: A positive integer representing the fractional portion of the version number (e.g. for v3.24, returns 24).
        """
        version = self.getVersion().split('.')[1]
        return int(version)

    # --- SETTINGS menu: BACKUPS section

    def saveBackup(self, fileName: str):
        """Saves the contents of this Pixelblaze into a Pixelblaze Binary Backup file.

        Args:
            fileName (str): The desired filename for the Pixelblaze Binary Backup.
        """
        PBB.fromPixelblaze(self).toFile(fileName)

    def restoreFromBackup(self, fileName: str):
        """Restores the contents of this Pixelblaze from a Pixelblaze Binary Backup file.

        Args:
            fileName (str): The desired filename for the Pixelblaze Binary Backup.
        """
        PBB.fromFile(fileName).toPixelblaze(self)

    def reboot(self):
        """Reboots the Pixelblaze.

        This is occasionally necessary, e.g. to force the Pixelblaze to recognize changes to configuration files.
        """
        with requests.post(self.getUrl("reboot"), proxies=self.proxyDict) as rReboot:
            if rReboot.status_code not in [200, 404]:
                rReboot.raise_for_status()

    # --- ADVANCED menu:

    def setBrandName(self, brandName: str):
        """Sets the brand name of the Pixelblaze (used by VARs to change the brand name that appears on the webUI).

        Args:
            brandName (str): The new name.
        """
        self.wsSendJson({"brandName": brandName}, expectedResponse=None)

    def setSimpleUiMode(self, doSimpleMode: bool):
        """Enables or disables "Simple UI Mode" which makes the UI more suitable for non-technical audiences.

        Args:
            doSimpleMode (bool): Whether to enable "Simple UI Mode".
        """
        self.wsSendJson({"simpleUiMode": doSimpleMode}, expectedResponse=None)

    def setLearningUiMode(self, doLearningMode: bool):
        """Enables or disables "Learning UI Mode" which has additional UI help for new users.

        Args:
            doLearningMode (bool): Whether to enable "Learning UI Mode".
        """
        self.wsSendJson({"learningUiMode": doLearningMode}, expectedResponse=None)

    # --- ADVANCED menu: convenience functions
    """The Pixelblaze API has functions to 'set' individual property values, 
    but can only 'get' property values as part of a JSON dictionary containing all the settings
    on a particular UI page. These functions will extract the property value from a 
    previously-fetched dictionary, if provided; otherwise they will fetch the settings anew."""

    def getBrandName(self, configSettings: dict = None) -> str:
        """Returns the brand name, if any, of this Pixelblaze (blank unless rebadged by a reseller).

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            str: The brand name.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('brandName', None)

    def getSimpleUiMode(self, configSettings: dict = None) -> bool:
        """Returns whether "Simple UI Mode" is enabled.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            bool: A boolean indicating whether "Simple UI Mode" is enabled.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('simpleUiMode', None)

    def getLearningUiMode(self, configSettings: dict = None) -> bool:
        """Returns whether "Learning UI Mode" is enabled.

        Args:
            configSettings (dict, optional): If provided, extracts the value from the results of a previous call to `getConfigSettings`; otherwise, fetches the configSettings from the Pixelblaze anew. Defaults to None.

        Returns:
            bool: A boolean indicating whether "Learning UI Mode" is enabled.
        """
        if configSettings is None: configSettings = self.getConfigSettings()
        return configSettings.get('learningUiMode', None)

    # --- PRIVATE HELPER FUNCTIONS

    class deprecationReasons(IntEnum):
        renamed = 1
        functionalityChanged = 2
        notRequired = 3

    warningsGiven = []

    def __printDeprecationMessage(self, deprecationReason: deprecationReasons, oldFunction: str, newFunction: str):
        """For functions that have been deprecated, print an explanatory warning message the first time they are called.

        Args:
            deprecationReason (deprecationReasons): An enumerated value indicating which message to display.
            oldFunction (str): The old name of the function.
            newFunction (str): The new name of the function, where appropriate.
        """
        if not oldFunction in self.warningsGiven:
            self.warningsGiven.append(oldFunction)
            if deprecationReason == self.deprecationReasons.renamed:
                print(
                    f'[pixelblaze-client] Warning: function "{oldFunction}" has been renamed and this compatibility stub will be removed in a future release; to avoid disruption, modify your code to use the replacement function "{newFunction}".')
            elif deprecationReason == self.deprecationReasons.functionalityChanged:
                print(
                    f'[pixelblaze-client] Warning: function "{oldFunction}" has been changed and may not have the same behavior; review the changelog and (if necessary) modify your code to use the replacement function "{newFunction}".')
            elif deprecationReason == self.deprecationReasons.notRequired:
                print(
                    f'[pixelblaze-client] Warning: function "{oldFunction}" is no longer required and will be removed in a future release; you may safely remove it from your code.')

    def _clamp(self, n, smallest, largest):
        """
        Utility Method: Why doesn't Python have clamp()?
        """
        return max(smallest, min(n, largest))

    def _time_in_millis(self) -> int:
        """
        Utility Method: Returns current time in milliseconds
        """
        return int(round(time.time() * 1000))

    # --- LEGACY FUNCTIONS (may be deprecated, removed or altered in the near future)
    #
    # Note to future editors: Some of these will probably need to stay around as a
    # simplified syntax "convenience" layer. In particular, the color control functions are handy
    # for home automation integrations. When deprecating or eliminating, make sure there's an
    # easy-to-use replacement in the current API.

    def pauseRenderer(self, doPause: bool):
        """Pause rendering. Lasts until unpaused or the Pixelblaze is reset.

        CAUTION: For advanced users only.  Only used to stop the render engine before
        sending new bytecode.

        If you don't know exactly why you want to do this, DON'T DO IT.

        Args:
            doPause (bool): If True, pause the render engine; if False, resume it.
        """
        self.wsSendJson({"pause": doPause}, expectedResponse="ack")

    def setActivePatternByName(self, patternName: str, *, saveToFlash: bool = False):
        """Sets the currently running pattern using a text name.

        Args:
            patternName (str): The name of the pattern.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        patternId = dict((value, key) for key, value in self.getPatternList().items()).get(patternName)
        self.setActivePattern(patternId, saveToFlash=saveToFlash)

    def controlExists(self, controlName: str, patternId: str = None) -> bool:
        """Tests whether the named control exists in the specified pattern.
        If no pattern is specified, the currently active pattern is assumed.

        Note that the active pattern can be undefined on a freshly started
        Pixelblaze until the pattern has been explicitly set.  This function
        also will return False if the active pattern is not available.

        Args:
            controlName (str): The name of the control.
            patternId (str, optional): The pattern in which to test for the presence of the control. Defaults to None.

        Returns:
            bool: True if the specified control exists, False otherwise.
        """
        result = self.getPatternControls(patternId)
        return True if controlName in result else False

    def getColorControlNames(self, patternId: str = None) -> list:
        """
        Returns a list of names of the specified pattern's rgbPicker or
        hsvPicker controls if any exist, None otherwise.  If the pattern
        argument is not specified, check the currently running pattern
        """
        controls = self.getActiveControls()
        if controls is None:
            return None

        # check for hsvPicker
        result = dict(filter(lambda ctl: "hsvPicker" in ctl[0], controls.items()))
        ctl_list = list(result.keys())

        # check for rgbPicker
        result = dict(filter(lambda ctl: "rgbPicker" in ctl[0], controls.items()))
        ctl_list += list(result.keys())

        return ctl_list if (len(ctl_list) > 0) else None

    def getColorControlName(self, patternId: str = None) -> str:
        """Returns the name of the specified pattern's first rgbPicker or
        hsvPicker control if one exists, or None otherwise.

        Args:
            patternId (str, optional): The pattern to search for color controls; or the currently active pattern if not specified. Defaults to None.

        Returns:
            str: The name of the specified pattern's first rgbPicker or hsvPicker control if one exists, or None otherwise.
        """
        result = self.getColorControlNames(patternId)
        if result is None:
            return result
        else:
            return result[0]

    def setColorControl(self, controlName: str, color, saveToFlash: bool = False):
        """Sets the 3-element color of the specified HSV or RGB color picker.

        Args:
            controlName (str): The name of the color control to change.
            color: RGB or HSV colors, with all values in the range 0-1.
            saveToFlash (bool, optional): If True, the setting is stored in Flash memory; otherwise the value reverts on a reboot. Defaults to False.
        """
        # based on testing w/Pixelblaze, no run-time length or range validation is performed
        # on color. Pixelblaze ignores extra elements, sets unspecified elements to zero,
        # takes only the fractional part of elements outside the range 0-1, and
        # does something (1-(n % 1)) for negative elements.
        self.setActiveControls({controlName: color}, saveToFlash=saveToFlash)

    def setCacheRefreshTime(self, seconds: int):
        """Set the interval, in seconds, after which calls to `getPatternList()` clear the pattern cache and fetch a new pattern list from the Pixelblaze.

        The Default is 600 seconds (10 minutes); the maximum allowable value is clamped to a million seconds (about 277 hours, or 11.5 days). Anything else would be excessive.

        Args:
            seconds (int): The maximum age of the pattern cache.
        """
        self.cacheRefreshInterval = 1000 * self._clamp(seconds, 0, 1000000)


# ----------------------------------------------------------------------------
#
#   ██████╗ ██████╗ ██████╗
#   ██╔══██╗██╔══██╗██╔══██╗
#   ██████╔╝██████╔╝██████╔╝
#   ██╔═══╝ ██╔══██╗██╔══██╗
#   ██║     ██████╔╝██████╔╝
#   ╚═╝     ╚═════╝ ╚═════╝
#   ╔═╗┬─┐ ┬┌─┐┬  ┌┐ ┬  ┌─┐┌─┐┌─┐  ╔╗ ┬┌┐┌┌─┐┬─┐┬ ┬  ╔╗ ┌─┐┌─┐┬┌─┬ ┬┌─┐
#   ╠═╝│┌┴┬┘├┤ │  ├┴┐│  ├─┤┌─┘├┤   ╠╩╗││││├─┤├┬┘└┬┘  ╠╩╗├─┤│  ├┴┐│ │├─┘
#   ╩  ┴┴ └─└─┘┴─┘└─┘┴─┘┴ ┴└─┘└─┘  ╚═╝┴┘└┘┴ ┴┴└─ ┴   ╚═╝┴ ┴└─┘┴ ┴└─┘┴
#
class PBB:
    """This class provides methods for importing, exporting, and manipulating the contents of a Pixelblaze Binary Backup, as created from the Settings menu on a Pixelblaze.

    **CREATION**
    - [`fromFile()`](method-fromfile)
    - [`fromIpAddress()`](method-fromipaddress)
    - [`fromPixelblaze()`](method-frompixelblaze)

    **PROPERTIES**
    - [`deviceName()`](method-devicename)
    - [`getFileList()`](method-getfilelist)

    **MANIPULATION**
    - [`getFile()`](method-getfile)/[`putFile()`](method-putfile)/[`deleteFile()`](method-deletefile)

    **PERSISTENCE**
    - [`toFile()`](method-tofile)
    - [`toIpAddress()`](method-toipaddress)
    - [`toPixelblaze()`](method-topixelblaze)

    Note:
        The constructor is not intended to be called directly; objects are created and returned from the object creation methods described above.
    """
    # Members:
    __textData = None
    __fromDevice = None

    # private constructor
    def __init__(self, name: str, blob: bytes):
        """Initializes a new Pixelblaze Binary Backup (PBB) object.

        Args:
            id (str): The patternId of the pattern.
            blob (bytes): The binary contents of the pattern.

        Note:
            This method is not intended to be called directly; use the static methods `fromFile()`, `fromIpAddress()` or `fromPixelblaze()` methods to create and return a Pixelblaze Binary Backup (PBB) object.
        """
        self.__fromDevice = name
        self.__textData = blob

    # Static methods:
    @staticmethod
    def fromFile(
            fileName: str) -> 'PBB':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new Pixelblaze Binary Backup whose contents are loaded from a file on disk.

        Args:
            fileName (str): The filename of the Pixelblaze Binary Backup.

        Returns:
            PBB: A new Pixelblaze Binary Backup object.
        """
        return PBB(pathlib.Path(fileName).stem, pathlib.Path(fileName).read_text())

    @staticmethod
    def fromIpAddress(ipAddress: str, *, proxyUrl: str = None,
                      verbose: bool = False) -> 'PBB':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new Pixelblaze Binary Backup whose contents are loaded from a Pixelblaze specified by IP address.

        Args:
            ipAddress (str): The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1").
            proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None.
            verbose (bool, optional): A boolean specifying whether to print detailed progress statements. Defaults to False.

        Returns:
            PBB: A new Pixelblaze Binary Backup object.
        """
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl=proxyUrl) as pb:
            return PBB.fromPixelblaze(pb, verbose=verbose)

    @staticmethod
    def fromPixelblaze(pb: Pixelblaze, *,
                       verbose: bool = False) -> 'PBB':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new Pixelblaze Binary Backup whose contents are loaded from an existing Pixelblaze object.

        Args:
            pb (Pixelblaze): A Pixelblaze object.
            verbose (bool, optional): A boolean specifying whether to print detailed progress statements. Defaults to False.

        Returns:
            PBB: A new Pixelblaze Binary Backup object.
        """
        newOne = PBB(pb.ipAddress, json.dumps({"files": {}}, indent=2))
        #   Get the file list.
        for line in pb.getFileList(PBB.fileTypes.fileAll ^ PBB.fileTypes.fileSystem):
            filename = line.split('\t')[0]
            if verbose: print(f"  Downloading {filename}")
            contents = pb.getFile(filename)
            if not contents is None:
                newOne.putFile(filename, contents)
        return newOne

    # Class properties:
    @property
    def deviceName(self) -> str:
        """Gets the user-friendly name of the device from which this PixelBlazeBackup was made.

        Returns:
            str: The user-friendly name of the device from which this PixelBlazeBackup was made.
        """
        return self.__fromDevice

    # Class methods:
    class fileTypes(IntFlag):
        """A Pixelblaze contains Patterns, PatternSettings, Configs, Playlists, System and Other types of files."""
        fileConfig = 1
        filePattern = 2
        filePatternSetting = 4
        filePlaylist = 8
        fileSystem = 16
        fileOther = 32
        fileAll = fileConfig | filePattern | filePatternSetting | filePlaylist | fileSystem | fileOther

    def getFileList(self, fileTypes: fileTypes = fileTypes.fileAll) -> list[str]:
        """Returns a sorted list of the files contained in this PixelBlazeBackup.

        Args:
            fileTypes (fileTypes, optional): An bitwise enumeration indicating the types of files to list. Defaults to fileTypes.fileAll.

        Returns:
            list[str]: A list of filenames.
        """
        fileList = []
        for fileName in json.loads(self.__textData.encode().decode('utf-8-sig'))['files']:
            # Filter the list depending on the fileTypes requested.
            # fileConfigs:
            if fileName[1:] in ["config.json", "config2.json", "obconf.dat", "pixelmap.txt", "pixelmap.dat"]:
                if not bool(fileTypes & self.fileTypes.fileConfig):
                    continue
            # filePatterns and filePatternSettings:
            elif fileName.startswith("/p/"):
                if fileName.endswith(".c"):
                    # filePatternSettings:
                    if not bool(fileTypes & self.fileTypes.filePatternSetting):
                        continue
                else:
                    # filePattern:
                    if not bool(fileTypes & self.fileTypes.filePattern):
                        continue
            # filePlaylists:
            elif fileName.startswith("/l/"):
                if not bool(fileTypes & self.fileTypes.filePlaylist):
                    continue
            # fileSystem:
            elif fileName.endswith(".gz"):
                if not bool(fileTypes & self.fileTypes.fileSystem):
                    continue
            # fileOthers:
            else:
                # Ignore the blank line returned by the '/list' endpoint.
                if not bool(fileTypes & self.fileTypes.fileOther):
                    continue

            # This file must have passed safely through all the filters.
            fileList.append(fileName)

        # Return the filtered list.
        fileList.sort()
        return fileList

    def getFile(self, fileName: str) -> bytes:
        """Returns the contents of a particular file contained in this PixelBlazeBackup.

        Args:
            fileName (str): The name of the file to be returned.

        Returns:
            bytes: The contents of the requested file.
        """
        return base64.b64decode(json.loads(self.__textData.encode().decode('utf-8-sig'))['files'][fileName])

    def putFile(self, fileName: str, fileContents: bytes):
        """Inserts or replaces the contents of a particular file into this PixelBlazeBackup.

        Args:
            fileName (str): The name of the file to be stored.
            fileContents (bytes): The contents of the file to be stored.
        """
        jsonContents = json.loads(self.__textData.encode().decode('utf-8-sig'))
        jsonContents.get('files', {})[fileName] = base64.b64encode(fileContents).decode('UTF-8')
        self.__textData = json.dumps(jsonContents, indent=2)

    def deleteFile(self, fileName: str):
        """Removes a particular file from this PixelBlazeBackup.

        Args:
            fileName (str): The name of the file to be deleted.
        """
        jsonContents = json.loads(self.__textData.encode().decode('utf-8-sig'))
        if jsonContents.get(fileName, None):
            del jsonContents[fileName]
            self.__textData = json.dumps(jsonContents, indent=2)

    def toFile(self, fileName: str = None, explode: bool = False):
        """Writes this Pixelblaze Binary Backup to a file on disk.

        Args:
            fileName (str, optional): If specified, the filename of the Pixelblaze Binary Backup to be created; otherwise the originating Pixelblaze name is used. Defaults to None.
            explode (bool, optional): If specified, also exports the files within the Pixelblaze Binary Backup to a subdirectory. Defaults to False.
        """

        def safeFilename(unsafeName):
            # Sanitize filenames: Only '/' (U+002F SOLIDUS) is forbidden.
            # Other suitable candidates: '⁄' (U+2044 FRACTION SLASH); '∕' (U+2215 DIVISION SLASH); '⧸' (U+29F8 BIG SOLIDUS);
            #   '／' (U+FF0F FULLWIDTH SOLIDUS); and '╱' (U+2571 BOX DRAWINGS LIGHT DIAGONAL UPPER RIGHT TO LOWER LEFT).
            return unsafeName.replace("/", "∕")

        if fileName is None:
            path = pathlib.Path.cwd().joinpath(self.deviceName).with_suffix(".pbb")
        else:
            path = pathlib.Path(fileName).with_suffix(".pbb")
        with open(path, "w") as file:
            file.write(self.__textData)
        # If 'explode' is requested, export the contents of this Pixelblaze Binary Backup (PBB) as individual files.
        if explode is True:
            # Exploded files go in a subdirectory named after the Pixelblaze Binary Backup.
            path = pathlib.Path(path).with_suffix('')
            path.mkdir(parents=True, exist_ok=True)
            # Loop through the backup contents and save them appropriately.
            for fileName in self.getFileList(PBB.fileTypes.fileConfig):
                # Config files go in the "Configuration" subdirectory...
                configPath = path.joinpath("Configuration/")
                configPath.mkdir(parents=True, exist_ok=True)
                configPath.joinpath(fileName[1:]).write_bytes(self.getFile(fileName))
            for fileName in self.getFileList(PBB.fileTypes.filePlaylist):
                # Playlists go in the "Playlists" subdirectory...
                playlistPath = path.joinpath("Playlists/")
                playlistPath.mkdir(parents=True, exist_ok=True)
                playlistPath.joinpath("defaultPlaylist.json").write_bytes(self.getFile(fileName))
            for fileName in self.getFileList(PBB.fileTypes.filePattern | PBB.fileTypes.filePatternSetting):
                # Patterns go in the "Patterns" subdirectory...
                patternPath = path.joinpath("Patterns/")
                patternPath.mkdir(parents=True, exist_ok=True)
                if fileName.endswith('.c'):
                    # For pattern settings files, get the name from the original pattern.
                    pbp = PBP.fromBytes(pathlib.Path(fileName[3:]).stem, self.getFile(fileName[:-2]))
                    patternPath.joinpath(safeFilename(pbp.name)).with_suffix('.json').write_bytes(
                        self.getFile(fileName))
                else:
                    pbp = PBP.fromBytes(pathlib.Path(fileName[3:]).stem, self.getFile(fileName))
                    pbpPath = patternPath.joinpath(safeFilename(pbp.name)).with_suffix('.pbp')
                    pbp.toFile(pbpPath)
                    pbp.explode(pbpPath)
            for fileName in self.getFileList(PBB.fileTypes.fileOther):
                # And everything else (should just be the Icons) goes in the root directory...
                path.joinpath(fileName[1:]).write_bytes(self.getFile(fileName))

    def toIpAddress(self, ipAddress: str, *, proxyUrl: str = None, verbose: bool = False):
        """Restores the contents of this PixelBlazeBackup to a Pixelblaze identified by IP Address.

        Args:
            ipAddress (str): The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1").
            proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None.
            verbose (bool, optional): A boolean specifying whether to print detailed progress statements. Defaults to False.
        """
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl=proxyUrl) as pb:
            self.toPixelblaze(pb, verbose=verbose)

    def toPixelblaze(self, pb: Pixelblaze, *, verbose: bool = False):
        """Uploads the contents of this PixelBlazeBackup to the destination Pixelblaze.

        Args:
            pb (Pixelblaze): A Pixelblaze object.
            verbose (bool, optional): A boolean specifying whether to print detailed progress statements. Defaults to False.
        """
        # Delete all the files that are currently loaded on the Pixelblaze (excepting the WebApp itself).
        for filename in pb.getFileList(PBB.fileTypes.fileAll ^ PBB.fileTypes.fileSystem):
            if verbose: print(f"  Deleting {filename}")
            pb.deleteFile(filename)
        # Upload everything that's in this PixelBlazeBackup to the Pixelblaze.
        for filename in self.getFileList():
            if verbose: print(f"  Uploading {filename}")
            pb.putFile(filename, self.getFile(filename))
        # Send a reboot command so the Pixelblaze will recognize the new configuration.
        if verbose: print(f"  Rebooting {pb.ipAddress}")
        pb.reboot()


# ----------------------------------------------------------------------------
#
#   ██████╗ ██████╗ ██████╗
#   ██╔══██╗██╔══██╗██╔══██╗
#   ██████╔╝██████╔╝██████╔╝
#   ██╔═══╝ ██╔══██╗██╔═══╝
#   ██║     ██████╔╝██║
#   ╚═╝     ╚═════╝ ╚═╝
#   ╔═╗┬─┐ ┬┌─┐┬  ┌┐ ┬  ┌─┐┌─┐┌─┐  ╔╗ ┬┌┐┌┌─┐┬─┐┬ ┬  ╔═╗┌─┐┌┬┐┌┬┐┌─┐┬─┐┌┐┌
#   ╠═╝│┌┴┬┘├┤ │  ├┴┐│  ├─┤┌─┘├┤   ╠╩╗││││├─┤├┬┘└┬┘  ╠═╝├─┤ │  │ ├┤ ├┬┘│││
#   ╩  ┴┴ └─└─┘┴─┘└─┘┴─┘┴ ┴└─┘└─┘  ╚═╝┴┘└┘┴ ┴┴└─ ┴   ╩  ┴ ┴ ┴  ┴ └─┘┴└─┘└┘
#
class PBP:
    """This class represents a Pixelblaze Binary Pattern, as stored on the Pixelblaze filesystem or contained in a Pixelblaze Binary Backup.

    **CREATION**
    - [`fromBytes()`](method-frombytes)
    - [`fromFile()`](method-fromfile)
    - [`fromIpAddress()`](method-fromipaddress)
    - [`fromPixelblaze()`](method-frompixelblaze)

    **PROPERTIES**
    - [`id()`](method-id)
    - [`name()`](method-name)
    - [`jpeg()`](method-jpeg)
    - [`byteCode()`](method-bytecode)
    - [`sourceCode()`](method-sourcecode)

    **PERSISTENCE**
    - [`toFile()`](method-tofile)
    - [`toIpAddress()`](method-toipaddress)
    - [`toPixelblaze()`](method-topixelblaze)
    - [`toEPE()`](method-toepe)
    - [`explode()`](method-explode)


    Note:
        The constructor is not intended to be called directly; objects are created and returned from the object creation methods described above.
    """
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
    def __init__(self, id: str, blob: bytes):
        """Initializes a new Pixelblaze Binary Pattern (PBP) object.

        Args:
            id (str): The patternId of the pattern.
            blob (bytes): The binary contents of the pattern.

        Note:
            This method is not intended to be called directly; use the static methods `fromBytes()`, `fromFile()`, `fromIpAddress()` or `fromPixelblaze()` methods to create and return a PBP object.
        """
        self.__id = id
        self.__binaryData = blob

    # Static methods:
    @staticmethod
    def fromBytes(patternId: str,
                  blob: bytes) -> 'PBP':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new Pixelblaze Binary Pattern (PBP) whose contents are initialized from a bytes array.

        Args:
            patternId (str): A patternId for the Pixelblaze Binary Pattern to be created.
            blob (bytes): The binary contents of the Pixelblaze Binary Pattern to be created.

        Returns:
            PBP: A new Pixelblaze Binary Pattern object.
        """
        return PBP(patternId, blob)

    @staticmethod
    def fromFile(
            fileName: str) -> 'PBP':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new Pixelblaze Binary Pattern (PBP) whose contents are loaded from a file on disk.

        Args:
            fileName (str): The name of the file to be loaded into a Pixelblaze Binary Pattern.

        Returns:
            PBP: A new Pixelblaze Binary Pattern object.
        """
        return PBP.fromBytes(pathlib.Path(fileName).stem, pathlib.Path(fileName).read_bytes())

    @staticmethod
    def fromIpAddress(ipAddress: str, patternId: str, *,
                      proxyUrl: str = None) -> 'PBP':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new pattern Pixelblaze Binary Pattern (PBP) whose contents are downloaded from a URL.

        Args:
            ipAddress (str): The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1").
            patternId (str): The patternId of the Pixelblaze Binary Pattern to be loaded from the Pixelblaze.
            proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None.

        Returns:
            PBP: A new Pixelblaze Binary Pattern object.
        """
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl=proxyUrl) as pb:
            return PBP.fromPixelblaze(pb, patternId)

    @staticmethod
    def fromPixelblaze(pb: Pixelblaze,
                       patternId: str) -> 'PBP':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new pattern Pixelblaze Binary Pattern (PBP) whose contents are downloaded from an active Pixelblaze object.

        Args:
            pb (Pixelblaze): An active Pixelblaze object.
            patternId (str): The patternId of the Pixelblaze Binary Pattern to be loaded from the Pixelblaze.

        Returns:
            PBP: A new Pixelblaze Binary Pattern object.
        """
        return PBP.fromBytes(patternId, pb.getFile(f"/p/{patternId}"))

    # Class properties:
    @property
    def id(self) -> str:
        """Returns the patternId of the pattern contained in this Pixelblaze Binary Pattern (PBP).

        Returns:
            str: The patternId of the pattern contained in this Pixelblaze Binary Pattern (PBP).
        """
        return self.__id

    @property
    def name(self) -> str:
        """Returns the (human-readable) name of the pattern contained in this Pixelblaze Binary Pattern (PBP).

        Returns:
            str: The (human-readable) name of the pattern contained in this Pixelblaze Binary Pattern (PBP).
        """
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return self.__binaryData[offsets[1]:offsets[1] + offsets[2]].decode('UTF-8')

    @property
    def jpeg(self) -> bytes:
        """Returns (as a collection of bytes) the preview JPEG of the pattern contained in this Pixelblaze Binary Pattern (PBP).

        Returns:
            bytes: The preview JPEG of the pattern contained in this Pixelblaze Binary Pattern (PBP).
        """
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return self.__binaryData[offsets[3]:offsets[3] + offsets[4]]

    @property
    def byteCode(self) -> bytes:
        """Returns (as a collection of bytes) the bytecode of the pattern contained in this Pixelblaze Binary Pattern (PBP).

        Returns:
            bytes: The bytecode of the pattern contained in this Pixelblaze Binary Pattern (PBP).
        """
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return self.__binaryData[offsets[5]:offsets[5] + offsets[6]]

    @property
    def sourceCode(self) -> str:
        """Returns the source code of the pattern in this Pixelblaze Binary Pattern (PBP).

        Returns:
            str: The source code of the pattern as a JSON-encoded string.
        """
        # Calculate the offset for this component.
        offsets = struct.unpack('<9I', self.__binaryData[:36])
        return _LZstring.decompress(self.__binaryData[offsets[7]:offsets[7] + offsets[8]])

    # Class methods:
    def toFile(self, fileName: str = None):
        """Saves this Pixelblaze Binary Pattern (PBP) to a file on disk.

        Args:
            fileName (str, optional): If provided, A name for the Pixelblaze Binary Pattern file to be created; otherwise, the name is derived from the patternId. Defaults to None.
        """
        if fileName is None:
            fileName = pathlib.Path.cwd().joinpath(self.id).with_suffix(".pbp")
        else:
            fileName = pathlib.Path(fileName).with_suffix(".pbp")
        with open(fileName, "wb") as file:
            file.write(self.__binaryData)

    def toIpAddress(self, ipAddress: str, *, proxyUrl: str = None):
        """Uploads this Pixelblaze Binary Pattern (PBP) to a Pixelblaze identified by its IP address.

        Args:
            ipAddress (str): The Pixelblaze's IPv4 address in the usual dotted-quads numeric format (for example, "192.168.4.1").
            proxyUrl (str, optional): The url of a proxy, if required, in the format "protocol://ipAddress:port" (for example, "http://192.168.0.1:8888"). Defaults to None.
        """
        # Make a connection to the Pixelblaze.
        with Pixelblaze(ipAddress, proxyUrl) as pb:
            self.toPixelblaze(pb)

    def toPixelblaze(self, pb: Pixelblaze):
        """Uploads this Pixelblaze Binary Pattern (PBP) to an active Pixelblaze object.

        Args:
            pb (Pixelblaze): An active Pixelblaze object.
        """
        pb.putFile(self.id, self.__binaryData)

    def toEPE(
            self) -> 'EPE':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates a new Electromage Pattern Export (EPE) and initializes it from the contents of this Pixelblaze Binary Pattern (PBP).

        Returns:
            EPE: A new Electromage Pattern Export object.
        """
        epe = {
            'name': self.name,
            'id': self.id,
            'sources': json.loads(self.sourceCode),
            'preview': base64.b64encode(self.jpeg).decode('UTF-8')
        }
        return EPE.fromBytes(json.dumps(epe, indent=2))

    def explode(self, path: str = None):
        """Exports all the components of this Pixelblaze Binary Pattern (PBP) as separate files.

        Args:
            path (str, optional): If provided, a pathname for the folder in which to export the components; otherwise derived from the patternId. Defaults to None.
        """
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


# ----------------------------------------------------------------------------
#
#   ███████╗██████╗ ███████╗
#   ██╔════╝██╔══██╗██╔════╝
#   █████╗  ██████╔╝█████╗
#   ██╔══╝  ██╔═══╝ ██╔══╝
#   ███████╗██║     ███████╗
#   ╚══════╝╚═╝     ╚══════╝
#   ╔═╗┬  ┌─┐┌─┐┌┬┐┬─┐┌─┐┌┬┐┌─┐┌─┐┌─┐  ╔═╗┌─┐┌┬┐┌┬┐┌─┐┬─┐┌┐┌  ╔═╗─┐ ┬┌─┐┌─┐┬─┐┌┬┐
#   ║╣ │  ├┤ │   │ ├┬┘│ ││││├─┤│ ┬├┤   ╠═╝├─┤ │  │ ├┤ ├┬┘│││  ║╣ ┌┴┬┘├─┘│ │├┬┘ │
#   ╚═╝┴─┘└─┘└─┘ ┴ ┴└─└─┘┴ ┴┴ ┴└─┘└─┘  ╩  ┴ ┴ ┴  ┴ └─┘┴└─┘└┘  ╚═╝┴ └─┴  └─┘┴└─ ┴
#
class EPE:
    """This class provides methods for importing, exporting, and manipulating the contents of an Electromage Pattern Export (EPE), as exported from the Patterns list on a Pixelblaze.

    **CREATION**
    - [`fromBytes()`](method-frombytes)
    - [`fromFile()`](method-fromfile)

    **PROPERTIES**
    - [`patternId()`](method-patternid)
    - [`patternName()`](method-patternname)
    - [`sourceCode()`](method-sourcecode)
    - [`previewImage()`](method-previewimage)

    **PERSISTENCE**
    - [`toFile()`](method-tofile)
    - [`explode()`](method-explode)

    Note:
        The constructor is not intended to be called directly; objects are created and returned from the object creation methods described above.
    """
    # Members:
    __textData = None

    # private constructor
    def __init__(self, blob: bytes):
        """Initializes a new Electromage Pattern Export (EPE) object.

        Args:
            blob (bytes): The contents of the Electromage Pattern Export (EPE).

        Note:
            This method is not intended to be called directly; use the static methods `fromBytes()` or `fromFile()` to create and return an Electromage Pattern Export object.
        """
        self.__textData = blob

    # Static methods:
    @staticmethod
    def fromBytes(
            blob: bytes) -> 'EPE':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new Electromage Pattern Export (EPE) whose contents are loaded from a bytes array.

        Args:
            blob (bytes): The data from which to create the Electromage Pattern Export (EPE).

        Returns:
            EPE: A new Electromage Pattern Export (EPE) object.
        """
        return EPE(blob)

    @staticmethod
    def fromFile(
            fileName: str) -> 'EPE':  # 'Quoted' to defer resolution of forward reference; or could use 'from __future__ import annotations'
        """Creates and returns a new portable pattern EPE whose contents are loaded from a file on disk.

        Args:
            fileName (str): The name of the file from which to create the Electromage Pattern Export (EPE).

        Returns:
            EPE: A new Electromage Pattern Export (EPE) object.
        """
        with open(fileName, "r") as file:
            return EPE.fromBytes(file.read())

    # Class properties:
    @property
    def patternId(self) -> str:
        """Returns the patternId of the pattern contained in this Electromage Pattern Export (EPE).

        Returns:
            str: The patternId of the pattern contained in this Electromage Pattern Export (EPE).
        """
        return json.loads(self.__textData)['id']

    @property
    def patternName(self) -> str:
        """Returns the human-readable name of the pattern in this Electromage Pattern Export (EPE).

        Returns:
            str: The human-readable name of the pattern contained in this Electromage Pattern Export (EPE).
        """
        return json.loads(self.__textData)['name']

    @property
    def sourceCode(self) -> str:
        """Returns the source code of the pattern contained in this Electromage Pattern Export (EPE).

        Returns:
            str: The sourceCode of the pattern contained in this Electromage Pattern Export (EPE).
        """
        # if @wizard ever implements code sharing this may need to change (remove ['main']?).
        return json.loads(self.__textData)['sources']['main']

    @property
    def previewImage(self) -> bytes:
        """Returns (as bytes) the preview JPEG of the pattern contained in this Electromage Pattern Export (EPE).

        Returns:
            bytes: The preview JPEG of the pattern contained in this Electromage Pattern Export (EPE).
        """
        return json.loads(self.__textData)['preview']

    # Class methods:
    def toFile(self, fileName: str = None):
        """Saves this Electromage Pattern Export (EPE) to a file on disk.

        Args:
            fileName (str, optional): If provided, a name for the file to be created; otherwise derived from the patternId. Defaults to None.
        """
        if fileName is None:
            fileName = pathlib.Path.cwd().joinpath(self.patternId).with_suffix(".epe")
        with open(fileName, "w") as file:
            file.write(self.__textData)

    def explode(self, path: str):
        """Exports the components of this Electromage Pattern Export (EPE) to separate files.

        Args:
            path (str): If provided, a pathname for the folder in which to export the components; otherwise derived from the patternId. Defaults to None.
        """
        # Get a Path to help with creating filenames.
        if path is None: path = pathlib.Path.cwd().joinpath(self.patternId)
        patternPath = pathlib.Path(path)

        # ...the human-readable name.
        with open(patternPath.with_suffix('.metadata'), 'w') as outfile:
            outfile.write(self.patternName)

        # ...the preview image.
        with open(patternPath.with_suffix('.jpg'), 'wb') as outfile:
            outfile.write(self.previewImage)

        # ...the human-readable source code.
        with open(patternPath.with_suffix('.js'), 'w') as outfile:
            outfile.write(self.sourceCode)


# ----------------------------------------------------------------------------

class _LZstring:
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

        val = compressed[0]
        position = resetValue
        index = 1

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
            elif c == 2:
                return "".join(result)

            if enlargeIn == 0:
                enlargeIn = math.pow(2, numBits)
                numBits += 1

            if c in dictionary:
                entry = dictionary[c]
            else:
                if c == dictSize:
                    entry = w + w[0]
                else:
                    return None
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
        context_dictionaryToCreate = {}
        context_c = ""
        context_wc = ""
        context_w = ""
        context_enlargeIn = 2  # Compensate for the first entry which should not count
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
                            if context_data_position == bitsPerChar - 1:
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
                        if context_data_position == bitsPerChar - 1:
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


# ----------------------------------------------------------------------------
#
#   ██████╗ ███████╗
#   ██╔══██╗██╔════╝
#   ██████╔╝█████╗  
#   ██╔═══╝ ██╔══╝  
#   ██║     ███████╗
#   ╚═╝     ╚══════╝
#   ╔═╗┬─┐ ┬┌─┐┬  ┌┐ ┬  ┌─┐┌─┐┌─┐  ╔═╗┌┐┌┬ ┬┌┬┐┌─┐┬─┐┌─┐┌┬┐┌─┐┬─┐
#   ╠═╝│┌┴┬┘├┤ │  ├┴┐│  ├─┤┌─┘├┤   ║╣ ││││ ││││├┤ ├┬┘├─┤ │ │ │├┬┘
#   ╩  ┴┴ └─└─┘┴─┘└─┘┴─┘┴ ┴└─┘└─┘  ╚═╝┘└┘└─┘┴ ┴└─┘┴└─┴ ┴ ┴ └─┘┴└─
#
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
        Listens on all available interfaces if hostIP is not specified.
        """
        self.start(hostIP)

    def __del__(self):
        self.stop()

    def _time_in_millis(self):
        """
        Utility Method: Returns last 32 bits of the current time in milliseconds
        """
        return int(round(time.time() * 1000)) % 0xFFFFFFFF

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
                if self.autoSync:  # send
                    self._send_timesync(now, pkt[1], pkt[2], addr)

            elif pkt[0] == self.TIMESYNC_PACKET:  # always defer to other time sources
                if self.autoSync:
                    self.disableTimesync()

    def getPixelblazeList(self):
        dev = []
        for record in self.devices.values():
            dev.append(record["address"][0])  # just the ip
        return dev

