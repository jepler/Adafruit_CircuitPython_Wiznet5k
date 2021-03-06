# The MIT License (MIT)
#
# Copyright (c) 2019 ladyada for Adafruit Industries
# Modified by Brent Rubell for Adafruit Industries, 2020
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""
`adafruit_wiznet5k_socket`
================================================================================

A socket compatible interface with the Wiznet5k module.

* Author(s): ladyada, Brent Rubell

"""
import gc
import time
from micropython import const
from adafruit_wiznet5k import adafruit_wiznet5k

_the_interface = None  # pylint: disable=invalid-name


def set_interface(iface):
    """Helper to set the global internet interface."""
    global _the_interface  # pylint: disable=global-statement, invalid-name
    _the_interface = iface


def htonl(x):
    """Convert 32-bit positive integers from host to network byte order."""
    return (
        ((x) << 24 & 0xFF000000)
        | ((x) << 8 & 0x00FF0000)
        | ((x) >> 8 & 0x0000FF00)
        | ((x) >> 24 & 0x000000FF)
    )


def htons(x):
    """Convert 16-bit positive integers from host to network byte order."""
    return (((x) << 8) & 0xFF00) | (((x) >> 8) & 0xFF)


# pylint: disable=bad-whitespace
SOCK_STREAM = const(0x21)  # TCP
TCP_MODE = 80
SOCK_DGRAM = const(0x02)  # UDP
AF_INET = const(3)
NO_SOCKET_AVAIL = const(255)
# pylint: enable=bad-whitespace

# keep track of sockets we allocate
SOCKETS = []

# pylint: disable=too-many-arguments, unused-argument
def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
    """Translate the host/port argument into a sequence of 5-tuples that
    contain all the necessary arguments for creating a socket connected to that service.

    """
    if not isinstance(port, int):
        raise RuntimeError("Port must be an integer")
    return [(AF_INET, socktype, proto, "", (gethostbyname(host), port))]


def gethostbyname(hostname):
    """Translate a host name to IPv4 address format. The IPv4 address
    is returned as a string.
    :param str hostname: Desired hostname.
    """
    addr = _the_interface.get_host_by_name(hostname)
    addr = "{}.{}.{}.{}".format(addr[0], addr[1], addr[2], addr[3])
    return addr


# pylint: disable=invalid-name
class socket:
    """A simplified implementation of the Python 'socket' class
    for connecting to a Wiznet5k module.
    :param int family: Socket address (and protocol) family.
    :param int type: Socket type.

    """

    # pylint: disable=redefined-builtin,unused-argument
    def __init__(
        self, family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None, socknum=None
    ):
        if family != AF_INET:
            raise RuntimeError("Only AF_INET family supported by W5K modules.")
        self._sock_type = type
        self._buffer = b""
        self._timeout = 0

        self._socknum = _the_interface.get_socket(SOCKETS)
        SOCKETS.append(self._socknum)
        self.settimeout(self._timeout)

    @property
    def socknum(self):
        """Returns the socket object's socket number."""
        return self._socknum

    @property
    def connected(self):
        """Returns whether or not we are connected to the socket."""
        if self.socknum >= _the_interface.max_sockets:
            return 0
        status = _the_interface.socket_status(self.socknum)[0]
        if (
            status == adafruit_wiznet5k.SNSR_SOCK_CLOSE_WAIT
            and self.available()[0] == 0
        ):
            result = False
        result = status not in (
            adafruit_wiznet5k.SNSR_SOCK_CLOSED,
            adafruit_wiznet5k.SNSR_SOCK_LISTEN,
            adafruit_wiznet5k.SNSR_SOCK_CLOSE_WAIT,
            adafruit_wiznet5k.SNSR_SOCK_FIN_WAIT,
        )
        if not result:
            self.close()
            return result
        return result

    def getpeername(self):
        """Return the remote address to which the socket is connected."""
        return _the_interface.remote_ip(self.socknum)

    def inet_aton(self, ip_string):
        """Convert an IPv4 address from dotted-quad string format.
        :param str ip_string: IP Address, as a dotted-quad string.

        """
        self._buffer = b""
        self._buffer = [int(item) for item in ip_string.split(".")]
        self._buffer = bytearray(self._buffer)
        return self._buffer

    def connect(self, address, conntype=None):
        """Connect to a remote socket at address. (The format of address depends
        on the address family — see above.)
        :param tuple address: Remote socket as a (host, port) tuple.

        """
        assert (
            conntype != 0x03
        ), "Error: SSL/TLS is not currently supported by CircuitPython."
        host, port = address

        if hasattr(host, "split"):
            host = tuple(map(int, host.split(".")))
        if not _the_interface.socket_connect(
            self.socknum, host, port, conn_mode=self._sock_type
        ):
            raise RuntimeError("Failed to connect to host", host)
        self._buffer = b""

    def send(self, data):
        """Send data to the socket. The socket must be connected to
        a remote socket.
        :param bytearray data: Desired data to send to the socket.

        """
        _the_interface.socket_write(self.socknum, data)
        gc.collect()

    def recv(self, bufsize=0):  # pylint: disable=too-many-branches
        """Reads some bytes from the connected remote address.
        :param int bufsize: Maximum number of bytes to receive.
        """
        # print("Socket read", bufsize)
        if bufsize == 0:
            # read everything on the socket
            while True:
                if self._sock_type == SOCK_STREAM:
                    avail = self.available()
                elif self._sock_type == SOCK_DGRAM:
                    avail = _the_interface.udp_remaining()
                if avail:
                    if self._sock_type == SOCK_STREAM:
                        self._buffer += _the_interface.socket_read(self.socknum, avail)[
                            1
                        ]
                    elif self._sock_type == SOCK_DGRAM:
                        self._buffer += _the_interface.read_udp(self.socknum, avail)[1]
                else:
                    break
            gc.collect()
            ret = self._buffer
            self._buffer = b""
            gc.collect()
            return ret
        stamp = time.monotonic()

        to_read = bufsize - len(self._buffer)
        received = []
        while to_read > 0:
            # print("Bytes to read:", to_read)
            if self._sock_type == SOCK_STREAM:
                avail = self.available()
            elif self._sock_type == SOCK_DGRAM:
                avail = _the_interface.udp_remaining()
            if avail:
                stamp = time.monotonic()
                if self._sock_type == SOCK_STREAM:
                    recv = _the_interface.socket_read(
                        self.socknum, min(to_read, avail)
                    )[1]
                elif self._sock_type == SOCK_DGRAM:
                    recv = _the_interface.read_udp(self.socknum, min(to_read, avail))[1]
                recv = bytes(recv)
                received.append(recv)
                to_read -= len(recv)
                gc.collect()
            if self._timeout > 0 and time.monotonic() - stamp > self._timeout:
                break
        self._buffer += b"".join(received)

        ret = None
        if len(self._buffer) == bufsize:
            ret = self._buffer
            self._buffer = b""
        else:
            ret = self._buffer[:bufsize]
            self._buffer = self._buffer[bufsize:]
        gc.collect()
        return ret

    def readline(self):
        """Attempt to return as many bytes as we can up to \
        but not including '\r\n'.

        """
        stamp = time.monotonic()
        while b"\r\n" not in self._buffer:
            if self._sock_type == SOCK_STREAM:
                avail = self.available()
                if avail:
                    self._buffer += _the_interface.socket_read(self.socknum, avail)[1]
            elif self._sock_type == SOCK_DGRAM:
                avail = _the_interface.udp_remaining()
                if avail:
                    self._buffer += _the_interface.read_udp(self.socknum, avail)
            elif self._timeout > 0 and time.monotonic() - stamp > self._timeout:
                self.close()
                raise RuntimeError("Didn't receive response, failing out...")
        firstline, self._buffer = self._buffer.split(b"\r\n", 1)
        gc.collect()
        return firstline

    def disconnect(self):
        """Disconnects a TCP socket."""
        assert self._sock_type == SOCK_STREAM, "Socket must be a TCP socket."
        _the_interface.socket_disconnect(self.socknum)

    def close(self):
        """Closes the socket."""
        _the_interface.socket_close(self.socknum)
        SOCKETS.remove(self.socknum)

    def available(self):
        """Returns how many bytes of data are available to be read from the socket.

        """
        return _the_interface.socket_available(self.socknum, self._sock_type)

    def settimeout(self, value):
        """Sets socket read timeout.
        :param int value: Socket read timeout, in seconds.

        """
        if value < 0:
            raise Exception("Timeout period should be non-negative.")
        self._timeout = value

    def gettimeout(self):
        """Return the timeout in seconds (float) associated
        with socket operations, or None if no timeout is set.

        """
        return self._timeout
