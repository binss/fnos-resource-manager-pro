import assert from 'node:assert/strict';
const {readNasFan,setNasFanMode,useClient}=await import(process.env.FAN_CONTRACT);
let mode=2, supported=true, failWrite=false, ignoreWrite=false, calls=[], noSystemRpm=false;
const ok=data=>({result:'succ',data});
useClient({sysinfo:{
 getTrimMachineFeature:async()=>ok({cpuFanControl:supported,sysFanControl:false}),
 getFanMode:async()=>ok({mode}),
 setFanMode:async data=>{calls.push(data);if(failWrite)return {result:'fail',errno:1};if(!ignoreWrite)mode=data.mode;return ok({});}
},resmo:{sysFan:async()=>ok({fanSpeed:noSystemRpm?[]:[1450,1700,-1]}),cpu:async()=>ok({cpu:{fan:{fanSpeed:2500}}})}});
assert.deepEqual(await readNasFan(),{supported:true,mode:2,rpm:[1450,1700]});
for(const value of [1,2,3]){assert.equal((await setNasFanMode(value)).mode,value);assert.deepEqual(calls.at(-1),{mode:value});}
for(const value of [0,4,'2',null,true,1.5])await assert.rejects(setNasFanMode(value));
supported=false;assert.deepEqual(await readNasFan(),{supported:false,mode:null,rpm:[]});
const before=calls.length;await assert.rejects(setNasFanMode(2));assert.equal(calls.length,before);
supported=true;failWrite=true;await assert.rejects(setNasFanMode(2));
failWrite=false;ignoreWrite=true;mode=1;await assert.rejects(setNasFanMode(2));
console.log('Native fan protocol tests passed: supported/unsupported, modes 1/2/3, exact payload, invalid input, write failure, readback mismatch.');

noSystemRpm=true;assert.deepEqual((await readNasFan()).rpm,[2500]);
