// Extract only the pure balance parser; never load gateway credentials/services.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'node-gateway/server/services/executor.js'), 'utf8');
const fragment = source.slice(source.indexOf('function usableEntryMargin('), source.indexOf('async function preflightEntryMargin('));
const context = {};
vm.createContext(context);
vm.runInContext(fragment, context);
const samples = [
  {case: 'cash_exceeds_live_balance', input: {equity: {available: {cash: 245431.6, live_balance: 99725.05}}}},
  {case: 'zero_cash_positive_live', input: {equity: {available: {cash: 0, live_balance: 5000}}}},
  {case: 'null_cash_positive_live', input: {equity: {available: {cash: null, live_balance: 5000}}}}
].map(x => ({...x, selected: context.usableEntryMargin(x.input)}));
fs.writeFileSync(path.join(__dirname, 'margin-probe-results.json'), JSON.stringify(samples, null, 2) + '\n');
console.log(JSON.stringify(samples, null, 2));
