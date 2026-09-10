/* Small DOM harness around the shipped script: playback isolation and batch UI. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(id) { this.id=id; this.listeners={}; this.dataset={}; this.attributes={}; this.children=[]; this.value=''; this.hidden=false; this.disabled=false; this.paused=true; this.readyState=0; this.currentTime=0; this.volume=1; this.loop=true; this.clientWidth=400; this.classList={toggle(){}}; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  async emit(name, event={}) { if (this.disabled) return; for (const callback of this.listeners[name] || []) await callback({target:this, preventDefault(){}, ...event}); }
  click() { return this.emit('click'); }
  setAttribute(key,value) { this.attributes[key]=value; }
  getAttribute(key) { return this.attributes[key]; }
  removeAttribute(key) { delete this.attributes[key]; if (key==='src') this.src=''; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children=[...children]; }
  closest() { return null; }
  remove() {}
  pause() { this.paused=true; }
  load() {}
  async play() { this.paused=false; plays++; }
  getContext() { return {setTransform(){}, clearRect(){}, fillRect(){}}; }
}
const ids = [...fs.readFileSync(process.argv[3], 'utf8').matchAll(/id="([^"]+)"/g)].map(match=>match[1]);
const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
elements['playback-mode'].value='browser';
let plays=0, disconnected=true, posts=[];
const sources=[{id:'a'.repeat(64),name:'First.wav',duration_s:1,kind:'PERC candidate',waveform:[.1]}, {id:'b'.repeat(64),name:'Last.wav',duration_s:1,kind:'VOCAL candidate',waveform:[.1]}];
const decisions = {[sources[0].id]:'keep',[sources[1].id]:'unreviewed'};
const saved={decisions,counts:{total:2,keep:1,skip:0,unreviewed:1}};
const document={getElementById:id=>elements[id],querySelector:()=>({content:'token'}), querySelectorAll:()=>[],createElement:()=>new Element('generated'), addEventListener(){}, documentElement:{},body:new Element('body')};
async function fetch(url, options) {
  let result;
  if (options?.body) posts.push([url,JSON.parse(options.body)]);
  if(url==='/api/sources') result={sources:[sources[0]],batch_index:0,batch_count:2};
  else if(url==='/api/shortlist') result=saved;
  else if(url==='/api/shortlist/status') result={available:false,reason:'No index'};
  else if(url==='/api/batch') result={sources:[sources[1]],batch_index:1,batch_count:2};
  else if(url==='/api/live/status') {
    if(disconnected) return {ok:false,status:409,headers:{get:()=> 'application/json'},json:async()=>({error:'Disconnected bridge'})};
    result={attached:false,identity:{set_name:'Test',set_path:'/tmp/Test.als'},tempo:127};
  } else throw new Error('Unexpected endpoint '+url);
  return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>result};
}
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),{document,window:{devicePixelRatio:1,addEventListener(){},setInterval(){}},getComputedStyle:()=>({getPropertyValue:()=> '#000'}),fetch,console,setTimeout,URL});
const settle=()=>new Promise(resolve=>setTimeout(resolve,0));
(async()=>{
  await settle(); await settle();
  assert.equal(elements.player.src,'/source/'+sources[0].id);
  await elements.play.click(); assert.equal(plays,1);
  elements['playback-mode'].value='live'; await elements['playback-mode'].emit('change');
  assert.equal(elements.player.src,''); assert.equal(elements.player.paused,true);
  assert.equal(elements['playback-mode'].value,'live');
  assert.match(elements.status.textContent,/Disconnected/);
  await elements.play.click(); assert.equal(plays,1,'disconnection must never fall back to browser audio');
  await elements['batch-next'].click(); await settle();
  assert.match(elements['batch-label'].textContent,/2 \/ 2/);
  assert.equal(elements.player.src,'','navigation in Live must not load browser audio');
  await elements.kept.click(); await settle();
  assert.match(elements.empty.textContent,/other batches/);
  assert.match(elements.kept.textContent,/0; 1 total/);
  elements['playback-mode'].value='browser'; await elements['playback-mode'].emit('change');
  await elements.all.click(); await settle();
  assert.equal(elements.player.src,'/source/'+sources[1].id);
  assert.equal(plays,1,'explicit mode switch and navigation must not autoplay');
  assert.deepEqual(posts.filter(([url])=>url==='/api/batch').map(([,body])=>body.batch_index),[1]);
  console.log('Browser playback isolation and batch navigation passed');
})().catch(error=>{ console.error(error);process.exitCode=1; });
