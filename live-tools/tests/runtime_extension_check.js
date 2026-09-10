const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
function context() {
  const acks = [];
  const c = {
    api_get: (p, k) => [p, k], API_FALLBACK_HANDLERS: {},
    ensureInitialized: () => true,
    LiveAPI: function() { this.id = 42; },
    getScalar: (api, prop) => ({file_path:'/tmp/synthetic.als', name:'Synthetic'})[prop],
    ackWithRequest: (...args) => acks.push(args),
    liveApiValueToJson: JSON.stringify,
    Dict: function(name) { this.stringify = () => JSON.stringify({display_name:'Ext. In', identifier:name}); }
  };
  vm.createContext(c); vm.runInContext(source,c); return {c, acks};
}
const {c,acks}=context();
c.api_get('live_set','eidetic_runtime','request-1');
assert.equal(acks[0][0],'api_get');
const identity=JSON.parse(acks[0][1][2]);
assert.equal(identity.set_path,'/tmp/synthetic.als');
assert.equal(identity.set_id,42);
assert.equal(acks[0][2],'request-1');
const first=identity.instance_id;
c.api_get('live_set','eidetic_runtime','request-2');
assert.equal(JSON.parse(acks[1][1][2]).instance_id,first);
const second=context(); second.c.api_get('live_set','eidetic_runtime','next-load');
assert.notEqual(JSON.parse(second.acks[0][1][2]).instance_id,first);
assert.equal(JSON.parse(c.liveApiValueToJson(['dictionary','u123'],'route')).display_name,'Ext. In');
assert.equal(c.liveApiValueToJson([120],'tempo'),'[120]');
console.log('extension identity, reload, dictionary conversion passed');
