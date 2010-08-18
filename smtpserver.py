#
# Implementation of simple nonblocking smtp server with tornado
# very much of this code is taken from tornado httpserver.py
#

import errno
import logging
import os
import socket
import time
import email

from tornado import ioloop
from tornado import iostream

try:
    import fcntl
except ImportError:
    if os.name == 'nt':
        import win32_support as fcntl
    else:
        raise

try:
    import multiprocessing
except ImportError:
    multiprocessing = None

def _cpu_count():
    if multiprocessing is not None:
        try:
            return multiprocessing.cpu_count()
        except NotImplementedError:
            pass
    try:
        return os.sysconf("SC_NPROCESSORS_CONF")
    except ValueError:
        pass
    logging.error("Could not detect number of processors; "
                  "running with one process")
    return 1

class SMTPServer(object):
    def __init__(self, request_callback, io_loop=None):
        self.request_callback = request_callback
        self.io_loop = io_loop
        self._socket = None
        self._started = False

    def listen(self, port, address=""):
        self.bind(port,address)
        self.start(1)

    def bind(self, port, address=""):
        assert not self._socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        flags = fcntl.fcntl(self._socket.fileno(), fcntl.F_GETFD)
        flags |= fcntl.FD_CLOEXEC
        fcntl.fcntl(self._socket.fileno(), fcntl.F_SETFD, flags)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setblocking(0)
        self._socket.bind((address, port))
        self._socket.listen(128)

    def start(self, num_processes=1):
        """Starts this server in the IOLoop.

        By default, we run the server in this process and do not fork any
        additional child process.

        If num_processes is None or <= 0, we detect the number of cores
        available on this machine and fork that number of child
        processes. If num_processes is given and > 1, we fork that
        specific number of sub-processes.

        Since we use processes and not threads, there is no shared memory
        between any server code.
        """
        assert not self._started
        self._started = True
        if num_processes is None or num_processes <= 0:
            num_processes = _cpu_count()
        if num_processes > 1 and ioloop.IOLoop.initialized():
            logging.error("Cannot run in multiple processes: IOLoop instance "
                          "has already been initialized. You cannot call "
                          "IOLoop.instance() before calling start()")
            num_processes = 1
        if num_processes > 1:
            logging.info("Pre-forking %d server processes", num_processes)
            for i in range(num_processes):
                if os.fork() == 0:
                    self.io_loop = ioloop.IOLoop.instance()
                    self.io_loop.add_handler(
                        self._socket.fileno(), self._handle_events,
                        ioloop.IOLoop.READ)
                    return
            os.waitpid(-1, 0)
        else:
            if not self.io_loop:
                self.io_loop = ioloop.IOLoop.instance()
            self.io_loop.add_handler(self._socket.fileno(),
                                     self._handle_events,
                                     ioloop.IOLoop.READ)

    def stop(self):
        self.io_loop.remove_handler(self._socket.fileno())
        self._socket.close()

    def _handle_events(self, fd, events):
        while True:
            try:
                connection, address = self._socket.accept()
            except socket.error, e:
                if e[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                    return
                raise
            try:
                stream = iostream.IOStream(connection, io_loop=self.io_loop)
                SMTPConnection(stream, address, self.request_callback)
            except:
                logging.error("Error in connection callback", exc_info=True)

class SMTPConnection(object):
    def __init__(self, stream, address, request_callback):
        self.stream = stream
        self.address = address
        self.request_callback = request_callback
        self.stream.write("220 myserver Tornado Simple Mail Transfer Service Ready\r\n")
        self.stream.read_until("\r\n", self._parse_req)

    def write(self, chunk):
        assert self._request, "Request closed"
        if not self.stream.closed():
            self.stream.write(chunk, self._on_write_complete)

    def finish(self):
        assert self._request, "Request closed"
        self._request_finished = True
        if not self.stream.writing():
            self._finish_request()

    def _parse_req(self, data):
        if data.find("HELO") > -1 or data.find("EHLO") > -1:
            self.stream.write("250 myserver\r\n")
            self.stream.read_until('\r\n', self._parse_req)
        elif data.find("MAIL FROM") > -1:
            tokens = data.split(':')
            self.from_email = tokens[1]
            self.stream.write("200 Ok\r\n")
            self.stream.read_until("\r\n", self._parse_req)
        elif data.find("RCPT TO") > -1:
            tokens = data.split(':')
            self.to_email = tokens[1]
            self.stream.write("200 Ok\r\n")
            self.stream.read_until("\r\n", self._parse_req)
        elif data.find("DATA") > -1:
            self.stream.write("354 End data with <CR><LF>.<CR><LF>\r\n")
            self.stream.read_until("\r\n.\r\n", self._parse_msg)
        else:
            self.stream.read_until('\r\n', self._parse_req)

    def _parse_msg(self, data):
        msg = email.message_from_string(data)
        self.stream.write("250 Ok\r\n")
        self.stream.read_until('\r\n', self._parse_req)
