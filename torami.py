"""The first aproach to asterisk manager"""

from tornado import iostream
#import logging
import socket
import json
import re
from uuid import uuid1
import actions

EOL = '\r\n\r\n'


class Event(object):
    """This class help to create python objects and convert to
    dictionary or json object for best manipulation from event dict"""

    def __init__(self, aid, event):
        """Initialize asterisk events object"""
        self._event = event
        self._aid = aid
        self._event_mapping = {}
        for key in self._event:
            self._event_mapping[self._uncamel(key)] = key

    def to_json(self):
        """Convert and return events dict to json object"""

        return json.dumps(self._event)

    def to_dict(self):
        """Return de originally dict"""

        return self._event

    @staticmethod
    def _uncamel(key):
        """This method help to create object python from dict events
        follow the standard method names"""

        key = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', key)
        key = re.sub('([a-z0-9])([A-Z])', r'\1_\2', key).lower()
        return key

    @property
    def aid(self):
        """Return the asterisk id (file descriptor socket)"""
        return self._aid

    def __getattr__(self, name):
        """Return the attributte from originally events dict"""
        try:
            return self._event[self._event_mapping[name]]
        except KeyError:
            raise AttributeError, name + ' ' + self.to_json()


class Manager(iostream.IOStream):
    """This class help to crete object that comunicate with asterisk
    manager and hadle streams, reponses, execute actions and execute
    callbacks"""

    def __init__(self, address, port, events=None, verbose=0, **kwargs):
        """Initialize connecction to asterisk manager"""

        sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sck.connect((address, port))
        self._responses = {}
        self._events = events if events  else {}
        self._aid = sck.fileno()
        self._verbose = verbose

        iostream.IOStream.__init__(self, sck, **kwargs)
        self.read_until(EOL, self._setup)

    @property
    def aid(self):
        """Return the asterisk id (file descriptor socket)"""

        return self._aid

    def _setup(self, data):
        """The first time that stablish connection this method is calling
        for challenge messages with the asterisk manager protocol"""

        data = data[27:]
        self._filter(self._transform(data))
        self.read_until(EOL, self._read_events)

    @staticmethod
    def _transform(data):
        """Transform stream strings in dictionary python for best
        manipulation of streams"""

        data = data.split(EOL)
        while data[-1] == '':
            data.pop()
        data = json.dumps(data)
        data = data.replace('", "', '"}, {"')
        data = data.replace('["', '{"')
        data = data.replace('"]', '"}')
        data = data.replace('\\r\\n', '", "')
        data = data.replace(': ', '": "')
        return json.loads('[' + data + ']')

    def _filter(self, data):
        """Filter dictionary event if have ActionID or Event filter
        is initialized"""

        for item in data:
            if 'Event' in item and item['Event'] in self._events.keys():
                self._run_callback(self._events[item['Event']],
                    Event(self.aid, item))
            elif 'Response' in item and 'ActionID' in item:
                if item['ActionID'] in self._responses.keys():
                    self._run_callback(self._responses[item['ActionID']],
                        Event(self.aid, item))
                    del self._responses[item['ActionID']]

    def action(self, *args, **kwargs):
        """This generic method execute streams from ACTIONS dictionary
        and replace dynamic and positional parameters (%s) and add
        action_id when detect response of the action_id execute callback if
        this is set"""

        if 'actionid' in kwargs:
            actionid = args[0] + '-' + kwargs['actionid']
        else:
            actionid = args[0] + '-' + str(uuid1())

        if 'template' in kwargs:
            template = kwargs['template']
        else:
            template = getattr(actions, args[0].upper())

        if template != '':
            action = 'action: %s\r\n%s\r\nactionid: %s\r\n\r\n' % (
                         args[0], template, actionid)
        else:
            action = 'action: %s\r\nactionid: %s\r\n\r\n' % (
                         args[0], actionid)

        self.write(action % args[1:])

        if 'callback' in kwargs and kwargs['callback'] is not None:
            self._responses[actionid] = kwargs['callback']

        return actionid

    def _read_events(self, data):
        """Intermediate method is calling after setup and recursive method"""

        self._filter(self._transform(data))
        self.read_until(EOL, self._read_events)


class Collection(object):
    """This class help to handle multiple connections of asterisk manager
    like collection of objects"""

    def __init__(self):
        """Initialize collection"""

        self._manager = {}

    def add(self, address, port, events=None, verbose=0, **kwargs):
        """Add manager to collection"""

        if not events:
            events = {}
        tmp = Manager(address, port, events, verbose, **kwargs)
        self._manager[tmp.aid] = tmp
        return tmp.aid

    def remove(self, aid, callback=None):
        """Remove manager from collection"""

        if aid in self._manager:
            self._manager[aid].action('logoff', callback=callback)
            del self._manager[aid]

    def get(self, aid):
        """Get the manager by asterisk id (file descriptor socket) """

        return self._manager[aid]
