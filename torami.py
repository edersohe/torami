"""The first aproach to asterisk manager"""

from tornado import iostream
import logging
import socket
import json
import re
from uuid import uuid1
import re

EOL = '\r\n\r\n'


def default_parser(data):
    """Parse stream strings in dictionary python for best
    manipulation of streams"""

    try :
        res = json.dumps(data)
        res = res.replace('\\r\\n', '", "')
        res = res.replace(': ', '": "')
        res = json.loads('{' + res + '}')
    except:
        res = { 'RawData': data }

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
        self._re_actionid = re.compile('ActionID: [a-zA-Z0-9_-]+')
        self._re_event = re.compile('Event: [a-zA-Z0-9_-]+')

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
        self._filter(data)
        self.read_until(EOL, self._read_events)

    def _filter(self, data):
        """ filter events or actionids and execute callback """

        data = data.split(EOL)

        while len(data)>0 and data[-1].strip() in ('', None, [], '\r\n'):
            data.pop()

        for i in xrange(0,len(data)):
            if 'ActionID: ' in data[i]:
                actionid = self._re_actionid.search(data[i]).group()[10:]
                if self._responses.has_key(actionid):
                    data[i] = self._parser(self._aid,
                        self._responses[actionid], data[i])
                    self._run_callback(self._responses[actionid]['callback'],
                        data[i])
                    del self._responses[actionid]
            elif 'Event: ' in data[i]:
                event = self._re_event.search(data[i]).group()[7:]
                if self._events.has_key(event):
                    data[i] = self._parser(self._aid, self._events[event],
                        data[i])
                    self._run_callback(self._events[event]['callback'],
                        data[i])
            else:
                for r,d in self._raw_data.iteritems():
                    s = r.search(data[i])
                    if s:
                        data[i] = self._parser(self._aid, d, data[i])
                        self._run_callback(d['callback'], data[i])
                        break

            if self._debug:
                print 'DEBUG:info:_filter\r\n', data[i]
                print

    def _parser(self, aid, dictionary, data):
        if 'parser' in dictionary:
            data = Event(aid, dictionary['parser'](data))
        else:
            data = Event(aid, default_parser(data))

        return data

    def action(self, name, **kwargs):
        """This generic method execute actions and add action_id when detect
        response of the action_id execute callback if this is set and parse
        reponse"""

        callback = None
        actionid = name + '-' + str(uuid1())
        parser = None

        if 'callback' in kwargs:
            callback = kwargs['callback']
            del kwargs['callback']

        if 'actionid' in kwargs:
            actionid = kwargs['actionid']
            del kwargs['actionid']

        if 'parser' in kwargs:
            parser = kwargs['parser']
            del kwargs['parser']

        cmd = 'action: ' + name + '\r\n'

        for k, v in kwargs.iteritems():
            cmd += k + ': ' + v + '\r\n'

        cmd += 'actionid: ' + actionid + EOL

        self.write(cmd)

        if callback is not None:
            self._responses[actionid] = { 'callback': callback }

        if parser is not None:
            self._responses[actionid]['parser'] = parser

        if self._debug:
            print 'Command to execute:\r\n\r\n', cmd[:-2]

        return actionid

    def _read_events(self, data=""):
        """Intermediate method is calling after setup and recursive method"""

        self._filter(data)
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
