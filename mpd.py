# Python MPD client library
# Copyright (C) 2008  J. Alexander Treuman <jat@spatialrift.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# import socket
from twisted.internet import protocol, reactor, defer
from twisted.protocols import basic

HELLO_PREFIX = "OK MPD "
ERROR_PREFIX = "ACK "
SUCCESS = "OK"
NEXT = "list_OK"


class MPDError(Exception):
    pass

class ConnectionError(MPDError):
    pass

class ProtocolError(MPDError):
    pass

class CommandError(MPDError):
    pass

class CommandListError(MPDError):
    pass

class MPDProtocol(basic.LineReceiver):

    delimiter = "\n"
    
    def __init__(self):
        self.iterate = True
        self.reset()
        self.state = []
        self.commands = {
            # Status Commands
            "clearerror":       self.parse_nothing,
            "currentsong":      self.parse_object,
            "idle":             self.parse_list,
            "noidle":           None,
            "status":           self.parse_object,
            "stats":            self.parse_object,
            # Playback Option Commands
            "consume":          self.parse_nothing,
            "crossfade":        self.parse_nothing,
            "random":           self.parse_nothing,
            "repeat":           self.parse_nothing,
            "setvol":           self.parse_nothing,
            "single":           self.parse_nothing,
            "volume":           self.parse_nothing,
            # Playback Control Commands
            "next":             self.parse_nothing,
            "pause":            self.parse_nothing,
            "play":             self.parse_nothing,
            "playid":           self.parse_nothing,
            "previous":         self.parse_nothing,
            "seek":             self.parse_nothing,
            "seekid":           self.parse_nothing,
            "stop":             self.parse_nothing,
            # Playlist Commands
            "add":              self.parse_nothing,
            "addid":            self.parse_item,
            "clear":            self.parse_nothing,
            "delete":           self.parse_nothing,
            "deleteid":         self.parse_nothing,
            "move":             self.parse_nothing,
            "moveid":           self.parse_nothing,
            "playlist":         self.parse_playlist,
            "playlistfind":     self.parse_songs,
            "playlistid":       self.parse_songs,
            "playlistinfo":     self.parse_songs,
            "playlistsearch":   self.parse_songs,
            "plchanges":        self.parse_songs,
            "plchangesposid":   self.parse_changes,
            "shuffle":          self.parse_nothing,
            "swap":             self.parse_nothing,
            "swapid":           self.parse_nothing,
            # Stored Playlist Commands
            "listplaylist":     self.parse_list,
            "listplaylistinfo": self.parse_songs,
            "listplaylists":    self.parse_playlists,
            "load":             self.parse_nothing,
            "playlistadd":      self.parse_nothing,
            "playlistclear":    self.parse_nothing,
            "playlistdelete":   self.parse_nothing,
            "playlistmove":     self.parse_nothing,
            "rename":           self.parse_nothing,
            "rm":               self.parse_nothing,
            "save":             self.parse_nothing,
            # Database Commands
            "count":            self.parse_object,
            "find":             self.parse_songs,
            "list":             self.parse_list,
            "listall":          self.parse_database,
            "listallinfo":      self.parse_database,
            "lsinfo":           self.parse_database,
            "search":           self.parse_songs,
            "update":           self.parse_item,
            # Connection Commands
            "close":            None,
            "kill":             None,
            "password":         self.parse_nothing,
            "ping":             self.parse_nothing,
            # Audio Output Commands
            "disableoutput":    self.parse_nothing,
            "enableoutput":     self.parse_nothing,
            "outputs":          self.parse_outputs,
            # Reflection Commands
            "commands":         self.parse_list,
            "notcommands":      self.parse_list,
            "tagtypes":         self.parse_list,
            "urlhandlers":      self.parse_list,
        }

    def __getattr__(self, attr):
        try:
            parser = self.commands[attr]
        except KeyError:
            raise AttributeError("'%s' object has no attribute '%s'" %
                                 (self.__class__.__name__, attr))
        return lambda *args, **kwargs: self.execute(attr, args, parser, kwargs.get("blocking", False))
    
    def execute(self, command, args, parser, blocking):
        if self.command_list is not None and not callable(parser):
            raise CommandListError("%s not allowed in command list" % command)
        self.write_command(command, args)
        deferred = defer.Deferred()
        self.state.append(deferred)
        if parser is not None:
            deferred.addCallback(parser)
        
        if blocking:
            finished = [None]
            def block_callback(data):
                print data
                finished[0] = data
            deferred.addCallback(block_callback)
            while not finished[0]:
                reactor.iterate(0.5)
            return finished[0]
        else:
            return deferred
    
    def write_command(self, command, args=[]):
        parts = [command]
        parts += ['"%s"' % escape(str(arg)) for arg in args]
        print "sending", parts
        self.sendLine(" ".join(parts))
    
    def parse_pairs(self, lines, separator=": "):
        return (line.split(separator, 1) for line in lines)

    def parse_list(self, lines):
        seen = None
        for key, value in self.parse_pairs(lines):
            if key != seen:
                if seen is not None:
                    raise ProtocolError("Expected key '%s', got '%s'" %
                                        (seen, key))
                seen = key
            yield value

    def parse_playlist(self, lines):
        for key, value in self.read_pairs(lines, ":"):
            yield value

    def parse_objects(self, lines, delimiters=[]):
        obj = {}
        for key, value in self.parse_pairs(lines):
            key = key.lower()
            if key in delimiters and obj:
                yield obj
                obj = {}
            if key in obj:
                if not isinstance(obj[key], list):
                    obj[key] = [obj[key], value]
                else:
                    obj[key].append(value)
            else:
                obj[key] = value
        if obj:
            yield obj

    def parse_object(self, lines):
        objs = list(self.parse_objects(lines))
        if not objs:
            return {}
        return objs[0]

    def parse_item(self, lines):
        pairs = list(self.parse_pairs(lines))
        if len(pairs) != 1:
            return
        return pairs[0][1]
    
    def parse_nothing(self, lines):
        pass
    
    def parse_songs(self, lines):
        return self.parse_objects(lines, ["file"])

    def parse_playlists(self, lines):
        return self.parse_objects(lines, ["playlist"])

    def parse_database(self, lines):
        return self.parse_objects(lines, ["file", "directory", "playlist"])

    def parse_outputs(self, lines):
        return self.parse_objects(lines, ["outputid"])

    def parse_changes(self, lines):
        return self.parse_objects(lines, ["cpos"])

    def command_list_ok_begin(self):
        if self.command_list:
            raise CommandListError("Already in command list")
        self.write_command("command_list_ok_begin")
        self.command_list = True

    def command_list_end(self):
        if self.command_list:
            raise CommandListError("Not in command list")
        self.write_command("command_list_end")
    
    def reset(self):
        self.mpd_version = None
        self.command_list = False
        self.buffer = []
        self.state = []

    def pop_and_call_parser(self):
        parser = self.state.pop(0)
        parser.callback(self.buffer[:])
        self.buffer = []

    def lineReceived(self, line):
        if line.startswith(HELLO_PREFIX):
            self.mpd_version = line[len(HELLO_PREFIX):].strip()
        
        elif line.startswith(ERROR_PREFIX):
            error = line[len(ERROR_PREFIX):].strip()
            raise CommandError(error)
        
        elif self.command_list:
            if line == NEXT:
                self.pop_and_call_parser()
            if line == SUCCESS:
                self.command_list = False
        
        elif line == SUCCESS:
            self.pop_and_call_parser()
        else:
            self.buffer.append(line)

    def connectionMade(self):
        self.factory.connectionMade.callback(self)

class MPDFactory(protocol.ReconnectingClientFactory):
    protocol = MPDProtocol

def escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')    

# vim: set expandtab shiftwidth=4 softtabstop=4 textwidth=79:
