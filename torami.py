"""The first aproach to asterisk manager"""

from tornado import iostream
#import logging
import socket
import json
import re
from uuid import uuid1
import re

EOL = '\r\n\r\n'


def transform(data):
    """Transform stream strings in dictionary python for best
    manipulation of streams"""

    data = data.split(EOL)
    res = []

    for i in range(0, len(data)):
        if data[i].strip() in ('', None, [], '\r\n'):
            continue
        raw_data = data[i]
        data[i] = json.dumps(data[i])
        data[i] = data[i].replace('\\r\\n', '", "')
        data[i] = data[i].replace(': ', '": "')
        try:
            res.append(json.loads('{' + data[i] + '}'))
        except:
            res.append({'RawData': raw_data})

    return res


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

    @property
    def json(self):
        """Convert and return events dict to json object"""

        return json.dumps(self._event)

    @property
    def dict(self):
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
            raise AttributeError, name + ' ' + self.json


class Manager(iostream.IOStream):
    """This class help to crete object that comunicate with asterisk
    manager and hadle streams, reponses, execute actions and execute
    callbacks"""

    def __init__(self, address, port, events=None, raw_data=None,
            debug=False, **kwargs):
        """Initialize connecction to asterisk manager"""

        sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self._responses = {}
        self._events = events if events  else {}
        self._raw_data = {}

        raw_data = raw_data if raw_data else {}

        for k, v in raw_data.iteritems():
            self._raw_data[re.compile(k)] = v

        self._debug = debug

        iostream.IOStream.__init__(self, sck, **kwargs)
        self.connect((address, port), self._on_connect)
        self._aid = self.socket.fileno()

    def _on_connect(self):
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

    def _transform(self, data):

        data = transform(data)

        if self._debug:
            print 'After transform: \r\n\r\n', data, '\r\n'

        return data

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
            elif 'RawData' in item and 'ActionID' in item['RawData']:
                regexp = re.compile('ActionID: [a-z0-9_-]+')
                actionid = regexp.search(item['RawData']).group()[10:]
                if actionid in self._responses.keys():
                    self._run_callback(self._responses[actionid],
                        Event(self.aid, item))
                    del self._responses[actionid]
            elif 'RawData' in item:
                pass

    def action(self, name, **kwargs):
        """This generic method execute actions and add action_id when detect
        response of the action_id execute callback if this is set"""

        callback = None
        actionid = name + '-' + str(uuid1())

        if 'callback' in kwargs:
            callback = kwargs['callback']
            del kwargs['callback']

        if 'actionid' in kwargs:
            actionid = kwargs['actionid']
            del kwargs['actionid']

        cmd = 'action: ' + name + '\r\n'

        for k, v in kwargs.iteritems():
            cmd += k + ': ' + v + '\r\n'

        cmd += 'actionid: ' + actionid + EOL

        self.write(cmd)

        if callback is not None:
            self._responses[actionid] = callback

        if self._debug:
            print 'Command to execute:\r\n\r\n', cmd[:-2]

        return actionid

    def _read_events(self, data=""):
        """Intermediate method is calling after setup and recursive method"""

        self._filter(self._transform(data))
        self.read_until(EOL, self._read_events)


class Collection(object):
    """This class help to handle multiple connections of asterisk manager
    like collection of objects"""

    def __init__(self):
        """Initialize collection"""

        self._manager = {}

    def add(self, address, port, events=None, debug=False, **kwargs):
        """Add manager to collection"""

        if not events:
            events = {}
        tmp = Manager(address, port, events, debug, **kwargs)
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
