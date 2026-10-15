#!/usr/bin/env python3
"""Unit tests for the sensor board UDP protocol (`SensorPacket`, `SensorSender`).

No Pixelblaze required: these check the bytes on the wire against the layout
documented by the sensor board firmware (simap/pixelblaze_sensor_board) and
implemented by zranger1/SoundServerFX and hkolbeck/pixelblaze-rs.

    python3 -m pytest pixelblaze/test_sensor_packet.py
"""

import socket
import struct

import pytest

from pixelblaze.pixelblaze import SensorPacket, SensorSender


def test_frame_size_and_header():
    """The header is <type=50, senderId, senderTime, expansionType=1, 3 pad bytes>."""
    packet = SensorPacket.pack(senderId=0x11223344, senderTime=0x55667788)

    assert len(packet) == 104
    packetType, senderId, senderTime = struct.unpack_from("<III", packet, 0)
    assert packetType == 50
    assert senderId == 0x11223344
    assert senderTime == 0x55667788
    assert packet[12] == 1                  # expansion type: an SB1.0 sensor board
    assert packet[13:16] == b"\x00\x00\x00"  # padding


def test_field_offsets_are_little_endian_uint16s():
    """Each reading lands at the offset the firmware reads it from."""
    packet = SensorPacket.pack(
        frequencyData=[0.0] * 31 + [0.5],
        energyAverage=0.25,
        maxFrequencyMagnitude=0.125,
        maxFrequency=440,
        accelerometer=[0.0, 0.0, -1.0],
        light=0.5,
        analogInputs=[0.0, 0.0, 0.0, 0.0, 0.25],
    )

    assert struct.unpack_from("<H", packet, 16 + 31 * 2)[0] == 32768  # frequencyData[31]
    assert struct.unpack_from("<H", packet, 80)[0] == 16384           # energyAverage
    assert struct.unpack_from("<H", packet, 82)[0] == 8192            # maxFrequencyMagnitude
    assert struct.unpack_from("<H", packet, 84)[0] == 440             # maxFrequency, in Hz
    assert struct.unpack_from("<h", packet, 86 + 2 * 2)[0] == -32768  # accelerometer[2]
    assert struct.unpack_from("<H", packet, 92)[0] == 32768           # light
    assert struct.unpack_from("<H", packet, 94 + 4 * 2)[0] == 16384   # analogInputs[4]


def test_omitted_readings_are_zero():
    """A frame with only audio reports zero for everything else, as a dark, still board would."""
    decoded = SensorPacket.unpack(SensorPacket.pack(energyAverage=0.5))

    assert decoded["energyAverage"] == 0.5
    assert decoded["frequencyData"] == [0.0] * 32
    assert decoded["accelerometer"] == [0.0, 0.0, 0.0]
    assert decoded["light"] == 0.0
    assert decoded["analogInputs"] == [0.0] * 5


def test_round_trip_preserves_readings():
    """Values representable in 16 bits survive pack/unpack exactly."""
    bins = [i / 64 for i in range(32)]
    decoded = SensorPacket.unpack(SensorPacket.pack(
        frequencyData=bins,
        energyAverage=0.0625,
        maxFrequency=1170,
        maxFrequencyMagnitude=0.75,
        accelerometer=[0.5, -0.5, 0.25],
        light=0.125,
        analogInputs=[0.1875, 0.0, 0.5, 0.25, 0.75],
        senderId=99,
        senderTime=1234,
    ))

    assert decoded["frequencyData"] == bins
    assert decoded["energyAverage"] == 0.0625
    assert decoded["maxFrequency"] == 1170.0
    assert decoded["maxFrequencyMagnitude"] == 0.75
    assert decoded["accelerometer"] == [0.5, -0.5, 0.25]
    assert decoded["light"] == 0.125
    assert decoded["analogInputs"] == [0.1875, 0.0, 0.5, 0.25, 0.75]
    assert decoded["senderId"] == 99
    assert decoded["senderTime"] == 1234


def test_out_of_range_readings_saturate():
    """Loud frames clamp instead of wrapping around to silence."""
    packet = SensorPacket.pack(
        frequencyData=[9.0] * 32,
        energyAverage=-3.0,
        maxFrequency=999999,
        accelerometer=[7.0, -7.0, 0.0],
    )

    assert struct.unpack_from("<H", packet, 16)[0] == 65535
    assert struct.unpack_from("<H", packet, 80)[0] == 0
    assert struct.unpack_from("<H", packet, 84)[0] == 65535
    assert struct.unpack_from("<hh", packet, 86) == (32767, -32768)


def test_wrong_length_sequences_are_rejected():
    """A short frequencyData array is a bug, not a frame to pad out and send."""
    with pytest.raises(ValueError, match="frequencyData must have exactly 32"):
        SensorPacket.pack(frequencyData=[0.1] * 31)
    with pytest.raises(ValueError, match="accelerometer must have exactly 3"):
        SensorPacket.pack(accelerometer=[0.0, 0.0])
    with pytest.raises(ValueError, match="analogInputs must have exactly 5"):
        SensorPacket.pack(analogInputs=[0.0] * 6)


def test_unpack_rejects_foreign_datagrams():
    """Beacons and truncated frames raise rather than decoding into garbage readings."""
    with pytest.raises(ValueError, match="104-byte sensor packet"):
        SensorPacket.unpack(struct.pack("<LLL", 42, 1, 2))

    beacon = struct.pack("<IIIB3x", 42, 1, 2, 1) + bytes(88)
    with pytest.raises(ValueError, match="packet type 50"):
        SensorPacket.unpack(beacon)

    unknownExpansion = struct.pack("<IIIB3x", 50, 1, 2, 2) + bytes(88)
    with pytest.raises(ValueError, match="expansion type 1"):
        SensorPacket.unpack(unknownExpansion)


def test_sender_delivers_a_frame_to_every_target():
    """Two targets get the same datagram, and it decodes back to what was sent."""
    receivers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
    try:
        for receiver in receivers:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(5)
        ports = [receiver.getsockname()[1] for receiver in receivers]

        # One SensorSender can only aim at one port, so send from two.
        senders = [SensorSender(["127.0.0.1"], port=port, senderId=4242) for port in ports]
        try:
            for sender in senders:
                sender.send(energyAverage=0.5, maxFrequency=880)
        finally:
            for sender in senders:
                sender.close()

        for receiver in receivers:
            decoded = SensorPacket.unpack(receiver.recv(256))
            assert decoded["senderId"] == 4242
            assert decoded["energyAverage"] == 0.5
            assert decoded["maxFrequency"] == 880.0
    finally:
        for receiver in receivers:
            receiver.close()


def test_sender_requires_a_target():
    with pytest.raises(ValueError, match="at least one target"):
        SensorSender([])


def test_sender_leaves_a_borrowed_socket_open():
    """A caller that supplies its own socket keeps ownership of it."""
    borrowed = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender = SensorSender(["127.0.0.1"], sock=borrowed)
        sender.close()
        borrowed.getsockname()  # raises OSError if close() closed it
    finally:
        borrowed.close()
