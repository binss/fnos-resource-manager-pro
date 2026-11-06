const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/../packages/resmonpro/app/ui/temperature.html','utf8');
const functions=source.slice(source.indexOf('function smoothPath'),source.indexOf('function chart(){'));
const context={bucketSeconds:60};vm.createContext(context);vm.runInContext(functions,context);
assert.equal(context.smoothPath([],x=>x,y=>y),'');
assert.equal(context.smoothPath([[0,3]],x=>x,y=>y),'M0,3');
for(const ys of [[0,10,11,30],[30,11,10,0],[10,14,12,12]]){
 const path=context.smoothPath(ys.map((y,i)=>[i,y]),x=>x,y=>y);
 assert(!/NaN|Infinity/.test(path));
 [...path.matchAll(/C([^C]+)/g)].forEach((part,i)=>{
  const numbers=part[1].trim().split(/[ ,]+/).map(Number),low=Math.min(ys[i],ys[i+1]),high=Math.max(ys[i],ys[i+1]);
  assert(numbers[1]>=low&&numbers[1]<=high);assert(numbers[3]>=low&&numbers[3]<=high);
 });
}
assert.equal(context.continuousSegments([[0,1],[60000,2],[5000000,3],[5060000,4]]).length,2);
console.log('PASS: shape-preserving interpolation, plateaus, extrema and sampling gaps');
