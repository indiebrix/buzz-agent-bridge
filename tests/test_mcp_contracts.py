"""MCP 2.0 / OpenAI Events contract checks, without an account or remote callback."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import threading
import unittest

from buzz_agent_bridge.events import Events, NAME, VERSION
from buzz_agent_bridge.http import ProtectedStore, RPC
from buzz_agent_bridge.crypto import AEADCodec
from buzz_agent_bridge.transports import WebhookTransport
from buzz_agent_bridge.core.broker import NotReady
from buzz_agent_bridge.tools import JobTools
from test_buzz_durable_jobs import Fixture, CHANNEL, NOW


class MCPContracts(Fixture, unittest.TestCase):
    def setUp(self):
        self.setup_fixture()
        self.calls=[]
        self.store=ProtectedStore(Path(self.temp.name)/'subscriptions',self.codec.seal,self.codec.open)
        self.keys=[bytes(range(32)), bytes(reversed(range(32)))]
        self.registration=Events(self.store, lambda p,c:self.allowed and p=='dot' and c==CHANNEL,
                           self.post, lambda:self.clock, self.agent.pubkey)
        self.wake=WebhookTransport(self.store,self.post,self.registration.authorize,
                                   lambda:self.clock,threading.RLock())
        self.rpc=RPC(self.registration,JobTools(self.broker))
        self.params={'name':NAME,'arguments':{'channel':CHANNEL},
            'delivery':{'mode':'webhook','url':'https://callback.example.invalid/events',
                        'secret':'whsec_'+base64.b64encode(self.keys[0]).decode()}}
    def tearDown(self):
        self.store.close()
        self.teardown_fixture()
    def post(self,url,body,headers):
        self.calls.append((body,headers))
        value=json.loads(body)
        return 200, {'challenge':value['challenge']} if value.get('type')=='verification' else {}
    def call(self,method,params):
        return self.rpc('dot',{'jsonrpc':'2.0','id':1,'method':method,'params':params})
    def assert_signed(self,body,headers,keys):
        signed=headers['webhook-id'].encode()+b'.'+headers['webhook-timestamp'].encode()+b'.'+body
        expected={'v1,'+base64.b64encode(hmac.new(k,signed,hashlib.sha256).digest()).decode() for k in keys}
        self.assertEqual(set(headers['webhook-signature'].split(' ')),expected)

    def test_discovery_and_five_tool_schemas_equal_baseline_snapshot(self):
        expected=json.loads((Path(__file__).parent/'fixtures/public-contract.json').read_text())
        self.assertEqual(self.call('server/discover',{})['result'],expected['discovery'])
        self.assertEqual(self.call('events/list',{})['result'],expected['events'])
        self.assertEqual(self.call('tools/list',{})['result'],expected['tools'])

    def test_refresh_cache_restart_rotation_and_expiry(self):
        result=self.call('events/subscribe',self.params)['result']
        self.assert_signed(*self.calls[0], [self.keys[0]])
        self.assertEqual(self.call('events/subscribe',self.params)['result']['id'],result['id'])
        self.assertEqual(len(self.calls),1)
        self.store.close()
        self.store=ProtectedStore(Path(self.temp.name)/'subscriptions',self.codec.seal,self.codec.open)
        self.registration.store=self.store; self.wake.subscriptions=self.store
        self.call('events/subscribe',self.params)
        self.assertEqual(len(self.calls),1)  # Persisted verification cache is bounded.
        self.params['delivery']['secret']='whsec_'+base64.b64encode(self.keys[1]).decode()
        self.assertEqual(self.call('events/subscribe',self.params)['result']['id'],result['id'])
        self.assertEqual(len(self.calls),2)
        self.assert_signed(*self.calls[1], [self.keys[1]])
        ident=self.admit()
        self.broker.drain_one('wake',self.wake)
        body,headers=self.calls[-1]
        self.assert_signed(body,headers,self.keys)
        payload=json.loads(body)
        self.assertEqual(headers['webhook-id'],payload['eventId'])
        self.assertEqual(payload['name'],NAME)
        self.assertEqual(headers['X-MCP-Subscription-Id'],result['id'])
        self.assertEqual(set(payload),{'eventId','name','timestamp','data','cursor'})
        self.assertEqual(self.broker.status('dot',[ident])['jobs'][0]['execution'],'accepted')
        self.clock+=301
        another=self.admit([self.event(2)])
        self.broker.drain_one('wake',self.wake)
        self.assert_signed(*self.calls[-1],[self.keys[1]])
        self.clock+=3600
        pending=self.admit([self.event(3)])
        count=len(self.calls)
        self.assertEqual(self.broker.drain_one('wake',self.wake),{'state':'pending'})
        self.assertEqual(len(self.calls),count)

    def test_callback_failure_scope_and_unsubscribe_are_fail_closed(self):
        self.registration.post=lambda *_:(200,{'challenge':'wrong'})
        failed=self.call('events/subscribe',self.params)['error']
        self.assertEqual((failed['code'],failed['data']['reason']),(-32015,'challenge_failed'))
        self.assertEqual(len(self.store),0)
        self.registration.post=self.post
        self.call('events/subscribe',self.params)
        self.allowed=False
        self.assertEqual(self.call('events/subscribe',self.params)['error']['code'],-32001)
        self.allowed=True
        stop={**self.params,'delivery':{k:v for k,v in self.params['delivery'].items() if k!='secret'}}
        self.assertEqual(self.call('events/unsubscribe',stop)['result'],{})
        self.assertEqual(self.call('events/unsubscribe',stop)['result'],{})
        self.assertEqual(len(self.store),0)


if __name__=='__main__': unittest.main()
