# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from irc3.testing import BotTestCase
from irc3.compat import asyncio
from irc3.dcc.client import DCCSend
from irc3.dcc.optim import DCCSend as DCCSendOptim
from irc3.plugins.dcc import dcc_command
from irc3 import dcc_event
import tempfile
import shutil
import os

log = {'in': [], 'out': []}


def get_extra_info(*args):
    return ('127.0.0.1', 4567)


@dcc_event('(?P<data>.*)')
def log_in(bot, client=None, data=None):
    log['in'].append((client, data))


@dcc_event('(?P<data>.*)', iotype='out')
def log_out(bot, client=None, data=None):
    log['out'].append((client, data))


@dcc_command
def syn(bot, mask, client, args):
    """Ok

        %%syn
    """
    client.send_line('ack')


def chat_ready(client):
    client = client.result()
    client.actions(client.mask)
    client.send('\x01ACTION syn\x01')
    client.send('\x01ACTION help\x01')
    client.loop.call_later(.1, client.idle_timeout_reached)


class TestChat(BotTestCase):

    loop = asyncio.new_event_loop()
    config = dict(loop=loop,
                  includes=['irc3.plugins.dcc'],
                  dcc={'ip': '127.0.0.1'})
    mask = 'gawel@gawel!bearstech.com'

    def callDCCFTU(self, *args, **kwargs):
        self.bot = self.callFTU()
        self.bot.protocol.transport.get_extra_info = get_extra_info
        self.bot.dcc_manager.connection_made()
        self.bot.dispatch(':%s PRIVMSG irc3 :!chat' % self.mask)
        self.future = asyncio.Future(loop=self.loop)
        self.loop.call_later(.1, self.created)

    def created(self):
        print(self.bot.dcc_manager.connections['chat'])
        servers = self.bot.dcc_manager.connections['chat']['masks'][self.mask]
        self.server = list(servers.values())[0]
        print(self.server)
        self.client = self.bot.dcc_manager.create(
            'chat', 'gawel', host='127.0.0.1', port=self.server.port)
        self.client.ready.add_done_callback(chat_ready)
        self.client.closed.add_done_callback(self.future.set_result)

    def test_create(self):
        self.callDCCFTU('chat', 'gawel')
        self.bot.include('irc3.plugins.dcc')
        self.bot.include(__name__)
        self.loop.run_until_complete(self.future)
        proto = self.client
        assert proto.transport is not None
        info = self.bot.dcc_manager.connections['chat']['masks']['gawel']
        assert proto not in info.values()
        assert proto.started.result() is proto
        assert proto.closed.done()

        assert len(log['in']) == 5
        assert len(log['out']) == 6


class DCCTestCase(BotTestCase):

    loop = asyncio.new_event_loop()
    config = dict(loop=loop)

    def callDCCFTU(self, *args, **kwargs):
        bot = self.callFTU()
        self.future = asyncio.Future(loop=self.loop)
        bot.protocol.transport.get_extra_info = get_extra_info
        self.manager = manager = bot.dcc_manager
        manager.connection_made()
        self.server = manager.create(*args, **kwargs)
        self.server.ready.add_done_callback(self.created)

    def createFiles(self):
        self.wd = tempfile.mkdtemp(prefix='irc3dcc')
        self.addCleanup(shutil.rmtree, self.wd)
        self.dst = os.path.join(self.wd, 'dst')
        self.src = os.path.join(self.wd, 'src')
        with open(self.src, 'wb') as fd:
            fd.write(('start%ssend' % ('---' * (1024 * 1024))).encode('ascii'))

    def assertFileSent(self):
        getsize = os.path.getsize
        assert getsize(self.dst), getsize(self.src)
        assert getsize(self.dst), getsize(self.src)
        with open(self.src, 'rb') as fd:
            src = fd.read()
        with open(self.dst, 'rb') as fd:
            dest = fd.read()
        assert src == dest


class TestSend(DCCTestCase):

    send_class = DCCSend

    def created(self, f):
        self.client = self.manager.create(
            'get', 'gawel',
            host='127.0.0.1', port=self.server.port,
            idle_timeout=10, filepath=self.dst)
        self.client.closed.add_done_callback(self.future.set_result)

    def test_create(self):
        self.createFiles()
        self.callDCCFTU(self.send_class, 'gawel', filepath=self.src)
        self.loop.run_until_complete(self.future)
        proto = self.client
        assert proto.transport is not None
        info = self.manager.connections['get']['masks']['gawel']
        assert proto not in info.values()
        assert proto.started.result() is proto
        assert proto.closed.done()
        self.assertFileSent()


class TestSendOptim(TestSend):

    send_class = DCCSendOptim


class TestResume(DCCTestCase):

    send_class = DCCSend

    def created(self, f):
        with open(self.dst, 'wb') as fd:
            with open(self.src, 'rb') as fdd:
                fd.write(fdd.read(1345))
        self.client = self.manager.create(
            'get', 'gawel',
            host='127.0.0.1', port=self.server.port,
            idle_timeout=10, filepath=self.dst)
        self.client.resume = True
        self.manager.resume('gawel', self.server.filename_safe,
                            self.server.port, self.client.offset)
        self.client.closed.add_done_callback(self.future.set_result)

    def test_create(self):
        self.createFiles()
        self.callDCCFTU(self.send_class, 'gawel', filepath=self.src)
        self.loop.run_until_complete(self.future)
        proto = self.client
        assert proto.transport is not None
        info = self.manager.connections['get']['masks']['gawel']
        assert proto not in info.values()
        assert proto.started.result() is proto
        assert proto.closed.done()
        self.assertFileSent()


class TestResumeOptim(TestResume):

    send_class = DCCSendOptim


class TestSendWithLimit(DCCTestCase):

    send_class = DCCSend

    def created(self, f):
        self.client = self.manager.create(
            'get', 'gawel',
            host='127.0.0.1', port=self.server.port,
            idle_timeout=10, filepath=self.dst)
        self.client.closed.add_done_callback(self.future.set_result)

    def test_create(self):
        self.createFiles()
        self.callDCCFTU(self.send_class, 'gawel',
                        filepath=self.src, limit_rate=64)
        self.loop.run_until_complete(self.future)
        proto = self.client
        assert proto.transport is not None
        info = self.manager.connections['get']['masks']['gawel']
        assert proto not in info.values()
        assert proto.started.result() is proto
        assert proto.closed.done()
        self.assertFileSent()


class TestSendWithLimitOptim(TestSendWithLimit):

    send_class = DCCSendOptim