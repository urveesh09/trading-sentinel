// Pure-source extraction only; no gateway startup, credentials or broker calls.
const fs = require('fs'), path = require('path'), vm = require('vm');
const source = fs.readFileSync(path.resolve(__dirname,'../../node-gateway/server/services/executor.js'),'utf8');
const fragment = source.slice(source.indexOf('function finiteNonNegative('),source.indexOf('async function preflightEntryMargin('));
const box={};vm.createContext(box);vm.runInContext(fragment,box);
const results=[-1000,null,'invalid',0,5000].map(live=>({live_balance:live,cash:100000,selected:box.usableEntryMargin({equity:{enabled:true,available:{live_balance:live,cash:100000}}})}));
fs.writeFileSync(path.join(__dirname,'margin-results.json'),JSON.stringify(results,null,2)+'\n');console.log(JSON.stringify(results,null,2));
