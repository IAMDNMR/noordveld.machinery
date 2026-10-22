import {chromium} from 'playwright-core';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.STUDIO_URL || 'http://127.0.0.1:5192';
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) throw new Error('Loopback Studio required');
if (!process.env.STUDIO_FIXTURE) throw new Error('Set STUDIO_FIXTURE to an exported synthetic src/definition.json');
async function login(id){const r=await page.request.post(base+'/api/v1/auth/login',{data:{user_id:id}});assert.equal(r.status(),200)}
await login('studio-alice');
const def=JSON.parse(await readFile(process.env.STUDIO_FIXTURE,'utf8'));
def.id='app_browser_review_'+Date.now();def.metadata.name=def.id;def.approvals=[];
const created=await page.request.post(base+'/api/v1/design-studio/projects',{data:def});assert.equal(created.status(),200,await created.text());
async function open(){await page.goto(base+'/workspace');await page.locator('li').filter({has:page.getByText(def.id,{exact:true})}).getByRole('link',{name:'Open project',exact:true}).click();await page.getByLabel('Project save status').filter({hasText:'Saved'}).waitFor()}
await open();
await page.getByRole('button',{name:'show processes',exact:true}).click();await page.getByRole('heading',{name:'Design evidence'}).waitFor();
await page.getByRole('navigation',{name:'Design journey'}).getByRole('button',{name:'Business Process',exact:true}).click();
await page.getByRole('button',{name:'Fit to screen',exact:true}).click();
await page.screenshot({path:process.env.TEMP+'/studio-redesigned-process.png',fullPage:true});
await page.getByRole('button',{name:'Select step Dispatch shipment',exact:true}).click();
await page.getByRole('tab',{name:'Properties',exact:true}).waitFor();
assert.equal(await page.getByRole('tab',{name:'Properties',exact:true}).getAttribute('aria-selected'),'true');
await page.setViewportSize({width:390,height:844});
await page.screenshot({path:process.env.TEMP+'/studio-redesigned-mobile.png',fullPage:true});
assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile viewport must not overflow');
await page.setViewportSize({width:1600,height:1000});
await login('studio-bob');await open();
await page.getByRole('button',{name:'Review & approvals',exact:true}).click();
await page.getByRole('button',{name:'Refresh status',exact:true}).click();
for(const scope of ['process','design']) {
 const check=page.getByLabel('Acknowledge '+scope+' warnings');
 await page.getByRole('button',{name:new RegExp('Approve '+scope+' at revision')}).waitFor();
 if(await check.count()) await check.check();
 await page.getByRole('button',{name:new RegExp('Approve '+scope+' at revision')}).click();
 await page.getByRole('button',{name:scope[0].toUpperCase()+scope.slice(1)+' approved',exact:true}).waitFor();
}
await login('studio-alice');await open();
await page.getByRole('navigation',{name:'Design journey'}).getByRole('button',{name:'Generate Application',exact:true}).click();
await page.getByRole('button',{name:'Compile saved revision'}).click();
const link=page.getByRole('link',{name:'Download generated application (ZIP)'});await link.waitFor();
const r=await page.request.get(new URL(await link.getAttribute('href'),base).href);assert.equal(r.status(),200);assert.ok((await r.body()).length>10000);
await page.screenshot({path:process.env.TEMP+'/studio-compiled-review.png',fullPage:true});
assert.deepEqual(errors,[]);console.log(JSON.stringify({status:'passed',journey:'workspace open → saved assistant → independent approval → compile → ZIP download',pageErrors:errors.length}));
await browser.close();



