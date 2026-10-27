const assert=require('node:assert/strict');
const replay=require('./fund_replay.js');
const values=[
 {t:1,as_of:'2026-10-26T09:31:00+08:00',main:1,xl:.6,lg:.4,md:-.5,sm:-.5},
 {t:60,as_of:'2026-10-26T10:30:00+08:00',main:4,xl:2.5,lg:1.5,md:-2,sm:-2},
 {t:127,as_of:'2026-10-26T13:07:00+08:00',main:7,xl:4,lg:3,md:-4,sm:-3}
];
const board={id:'BK1',as_of:'2026-10-26T13:05:51+08:00',latest:{main:99,xl:59,lg:40,md:-49,sm:-50},values};
const points=replay.prepare(board);
assert.equal(replay.at(points,60).main,4,'Historical cursor must not read latest quote 99');
assert.equal(replay.at(points,80).main,4,'Missing minute uses the latest observed record before the cursor');
assert.equal(replay.at(points,0).main,null,'Before the first observation is missing, not zero');
assert.equal(replay.at(points,127).main,7);
assert.deepEqual(replay.through(points,60).map(v=>v.t),[1,60]);
assert.deepEqual(['09:30','11:30','13:00','15:00'].map(hm=>replay.minuteOf('2026-10-26T'+hm+':00+08:00')),[0,120,120,240]);
assert.equal(replay.minuteOf('bad timestamp'),null);
const quote=replay.prepare({...board,values:[]});
assert.equal(quote[0].kind,'quote');
assert.equal(replay.at(quote,125,true).main,null,'13:05:51 quote cannot fill 13:05 history');
assert.equal(replay.at(quote,126,true).main,99);
const lateQuote=replay.prepare({...board,as_of:'2026-10-26T16:10:00+08:00',values:[]});
assert.equal(replay.at(lateQuote,240,false).main,99,'Latest closing quote may be provided after close');
assert.equal(replay.at(lateQuote,240,true).main,null,'After-close quote is not a known 15:00 observation');
assert.equal(replay.limit([{fundPoints:points}]),127);
assert.equal(replay.prepare({...board,values:[{...values[0],as_of:'2026-10-23T09:31:00+08:00'}]})[0].kind,'quote','Previous-day trace must not be shown as today');
assert.equal(replay.prepare({as_of:null,latest:{main:7},values:[]}).length,0);
const appended=replay.prepare({...board,values:values.slice(0,2)});
assert.equal(replay.at(appended,100,true).main,4);
assert.equal(replay.at(appended,126,true).main,99,'A newer actual quote is available after its own timestamp');
const samples=replay.prepare({...board,values:[{...values[0],kind:'quote',rawMinute:1}]});
assert.equal(samples[0].kind,'quote');
assert.deepEqual(replay.segments(points).map(v=>v.length),[1,1,1],'Do not connect missing minutes');
assert.deepEqual(replay.segments([{...values[0]},{...values[0],t:2},{...values[0],t:3,kind:'quote'},{...values[0],t:4}]).map(v=>v.length),[4],'Adjacent observed points do not split a board into separate curves');
const interleaved=replay.prepare({...board,values:[...values,{...values[0],t:1.9,kind:'quote',rawMinute:1.9,as_of:'2026-10-26T09:31:54+08:00'}]});
assert.equal(interleaved.filter(v=>v.kind==='quote').length,0,'Minute trajectory takes priority over overlapping quote observations');
const lunch=replay.prepare({...board,as_of:'2026-10-26T12:20:00+08:00',values:[{...values[0],t:120,as_of:'2026-10-26T11:30:00+08:00'}]});
assert.equal(lunch.length,1,'A lunch timestamp must not create a second trajectory or extend morning trading time');
const jitter=[{t:122,as_of:'2026-10-26T13:02:00+08:00',main:1,kind:'series'}, {t:123.55,as_of:'2026-10-26T13:03:33+08:00',main:2,kind:'quote'}];
assert.equal(replay.segments(jitter).length,1,'Adjacent trading minutes remain connected when the actual quote carries seconds');
assert.equal(replay.segments([{t:122,main:1},{t:124.01,main:2}]).length,2,'A missing whole trading minute still leaves a gap');
const hole=replay.prepare({as_of:'2026-10-26T09:33:00+08:00',values:[{t:1,main:1,as_of:'2026-10-26T09:31:00+08:00'},{t:3,main:3,as_of:'2026-10-26T09:33:00+08:00'},{t:2.5,main:2,as_of:'2026-10-26T09:32:30+08:00',kind:'quote'}]});
assert.deepEqual(hole.map(r=>r.main),[1,2,3],'Keep real quote observations in minute gaps, in time order');
assert.equal(replay.segments(hole).length,1);
console.log('Fund replay: all checks passed');
