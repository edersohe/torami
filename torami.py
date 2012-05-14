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

    try:
        res = json.dumps(data)
        res = res.replace('\\r\\n', '", "')
        res = res.replace(': ', '": "')
        res = json.loads('{' + res + '}')
    except:
        res = {'RawData': data}

    return res


class Event(object):
    """This class help to create python objects and convert to
    dictionary or json object for best manipulation from event dict"""

    def __init__(self, ami_id, dictionary):
        """Initialize asterisk events object"""
        self._dictionary = dictionary
        self._ami_id = ami_id
        self._dictionary_mapping = {}
        for key in self._dictionary:
            self._dictionary_mapping[self._uncamel(key)] = key

    @property
    def json(self):
        """Convert and return events dict to json object"""

        return json.dumps(self._dictionary)

    @property
    def dict(self):
        """Return de originally dict"""

        return self._dictionary

    @staticmethod
    def _uncamel(key):
        """This method help to create object python from dict events
        follow the standard method names"""

        key = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', key)
        key = re.sub('([a-z0-9])([A-Z])', r'\1_\2', key).lower()
        return key

    @property
    def ami_id(self):
        """Return the asterisk id (file descriptor socket)"""
        return self._ami_id

    def __getattr__(self, name):
        """Return the attributte from originally events dict"""
        try:
            return self._dictionary[self._dictionary_mapping[name]]
        except KeyError:
            raise AttributeError, name + ' ' + self.json


class Manager(iostream.IOStream):
    """This class help to crete object that comunicate with asterisk
    manager and hadle streams, reponses, execute actions and execute
    callbacks"""

    def __init__(self, address, **kwargs):
        """Initialize connecction to asterisk manager
            port, username, secret, events, regexp, debug, callback,
            'ami_id'
        """
        port = kwargs.get('port', 5038)
        sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self._responses = {}
        self._events = kwargs.get('events', {})
        self._regexp = {}
        self._re_actionid = re.compile('ActionID: [a-zA-Z0-9_-]+')
        self._re_event = re.compile('Event: [a-zA-Z0-9_-]+')
        self._callback = kwargs.get('callback')
        self._username = kwargs.get('username', '')
        self._secret = kwargs.get('secret', '')
        self._ami_id = kwargs.get('ami_id', address)

        regexp = kwargs.get('regexp', {})

        for k, v in regexp.iteritems():
            self._regexp[re.compile(k)] = v

        self._debug = kwargs.get('debug', False)

        if 'port' in kwargs: del kwargs['port']
        if 'username' in kwargs: del kwargs['username']
        if 'secret' in kwargs: del kwargs['secret']
        if 'events' in kwargs: del kwargs['events']
        if 'regexp' in kwargs: del kwargs['regexp']
        if 'debug' in kwargs: del kwargs['debug']
        if 'callback' in kwargs: del kwargs['callback']
        if 'ami_id' in kwargs: del kwargs['ami_id']

        iostream.IOStream.__init__(self, sck, **kwargs)
        self.connect((address, port), self._on_connect)

    def _on_connect(self):
        if self._events != {}:
            self.action('login', username=self._username, secret=self._secret,
                callback=self._callback)
        else:
            self.action('login', username=self._username, secret=self._secret,
                events='off', callback=self._callback)
        self.read_until(EOL, self._setup)

    @property
    def ami_id(self):
        """Return the asterisk name"""
        return self._ami_id

    def _setup(self, data):
        """The first time that stablish connection this method is calling
        for challenge messages with the asterisk manager protocol"""

        data = data[27:]
        self._filter(data)
        self.read_until(EOL, self._read_events)

    def _filter(self, data):
        """ filter events or actionids and execute callback """

        data = data.split(EOL)

        while len(data) > 0 and data[-1].strip() in ('', None, [], '\r\n'):
            data.pop()

        for i in xrange(0, len(data)):
            if 'ActionID: ' in data[i]:
                actionid = self._re_actionid.search(data[i]).group()[10:]
                if actionid in self._responses:
                    data[i], kwargs = self._parser(self._responses[actionid],
                        data[i])
                    self._run_callback(self._responses[actionid]['callback'],
                        self, data[i], **kwargs)
                    del self._responses[actionid]
            elif 'Event: ' in data[i]:
                event = self._re_event.search(data[i]).group()[7:]
                if event in self._events:
                    data[i], kwargs = self._parser(self._events[event],
                        data[i])
                    self._run_callback(self._events[event]['callback'],
                        self, data[i], **kwargs)
            else:
                for r, d in self._regexp.iteritems():
                    s = r.search(data[i])
                    if s:
                        data[i], kwargs = self._parser(d, data[i])
                        self._run_callback(d['callback'], self, data[i],
                            **kwargs)
                        break

            if self._debug:
                print 'DEBUG:info:_filter\r\n', data[i]
                print

    def _parser(self, dictionary, data):
        if 'parser' in dictionary:
            data = Event(self._ami_id, dictionary['parser'](data))
        else:
            data = Event(self._ami_id, default_parser(data))
        if  'kwargs' in dictionary:
            kwargs = dictionary['kwargs']
        else:
            kwargs = {}

        return data, kwargs

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

        if 'variable' in kwargs:
            for k, v in kwargs['variable'].iteritems():
                cmd += 'variable: ' + k + '=' + v + '\r\n'

        cmd += 'actionid: ' + actionid + EOL

        if callback is not None:
            cbt = type(callback).__name__
            if cbt == 'function':
                self._responses[actionid] = {'callback': callback}
            elif cbt == 'dict' and 'callback' in callback:
                self._responses[actionid] = {'callback': callback['callback']}
                if 'parser' in callback:
                    self._responses[actionid]['parser'] = callback['parser']
                if 'kwargs' in callback:
                    self._responses[actionid]['kwargs'] = callback['kwargs']

        if self._debug:
            print 'Command to execute:\r\n\r\n', cmd[:-2]

        self.io_loop.add_callback(lambda: self.write(cmd))

    def _read_events(self, data=""):
        """Intermediate method is calling after setup and recursive method"""

        self._filter(data)
        self.read_until(EOL, self._read_events)


class Collection(object):
    """This class help to handle multiple connections of asterisk manager
    like collection of objects"""

    def __init__(self, hosts=None, defaults=None):
        """Initialize collection"""

        self._manager = {}
        self._defaults = defaults if isinstance(defaults, dict) else {}

        if isinstance(hosts, list):
            for i in xrange(0, len(hosts)):
                self.add(hosts[i])
        elif isinstance(hosts, dict):
            for k, v in hosts.iteritems():
                self.add(k, **v)

    def add(self, address, **kwargs):
        """Add manager to collection"""

        defaults = self._defaults.copy()
        defaults.update(kwargs)
        tmp = Manager(address, **defaults)
        self._manager[tmp.ami_id] = tmp
        return self._manager[tmp.ami_id]

    def remove(self, ami_id, callback=None):
        """Remove manager from collection"""

        if ami_id in self._manager:
            self._manager[ami_id].action('logoff', callback=callback)
            del self._manager[ami_id]

    def get(self, ami_id):
        """Get the manager by asterisk id (file descriptor socket) """

        if ami_id in self._manager:
            return self._manager[ami_id]
        return None

    def action(self, ami_id, name, **kwargs):
        """ Execute action for manager with ami_id """
        self._manager[ami_id].action(name, **kwargs)

    def action_for_all(self, name, **kwargs):
        """Execute action for all managers in collection"""

        for k in self._manager.keys():
            self._manager[k].action(name, **kwargs)
