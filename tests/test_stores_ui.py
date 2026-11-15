"""Local Chrome end-to-end checks. Uses shipped real snapshots; never modifies a retailer cart."""
import http.server,json,shutil,socketserver,threading,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=Path('/downloads/gb-store-review');OUT.mkdir(exist_ok=True)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*a,**k):super().__init__(*a,directory=str(ROOT),**k)
    def log_message(self,*a):pass
srv=socketserver.TCPServer(('127.0.0.1',0),H);threading.Thread(target=srv.serve_forever,daemon=True).start()
checks=0;fail=[]
def check(label,condition,details=None):
    global checks
    checks+=1;print(('PASS ' if condition else 'FAIL ')+label+((' '+str(details)) if not condition else ''))
    if not condition:fail.append(label)
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),args=['--no-sandbox'])
    for tag,width in [('desktop',1280),('mobile',390),('small',320)]:
        pg=b.new_page(viewport={'width':width,'height':900 if width>400 else 844});errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
        pg.goto('http://127.0.0.1:%d/index.html'%srv.server_address[1]);pg.wait_for_function("state.livePricesLoaded && Object.keys(STORE_DIRECTORY.stores).length>500")
        pg.evaluate("switchTab('Cart')")
        result=pg.evaluate("({schema:state.livePrices.metadata.version,stores:Object.keys(STORE_DIRECTORY.stores).length,snapshots:PRICE_CHAINS.length,chains:Object.keys(STORE_DIRECTORY.chains).length})")
        check(tag+' schema 3 and expanded directory',result['schema']=='3' and result['stores']>1000 and result['snapshots']==12 and result['chains']>6,result)
        check(tag+' legacy IDs resolve to exact online branches',pg.evaluate("normChainKey('rami-levy')==='rami-levy::039' && normChainKey('rami_levy')==='rami-levy::039' && normChainKey('shufersal')==='shufersal::413'"))
        # Save the exact feed-backed result rendered in both list and detail views.
        pg.evaluate("chooseDirectoryStore('shufersal::413');document.getElementById('storeDeals').scrollIntoView({block:'start'});scrollBy(0,-120)")
        if pg.locator('#storeDeals details').count():pg.locator('#storeDeals details').first.locator('summary').first.click()
        pg.screenshot(path=str(OUT/(tag+'-offer-conditions.png')))
        pg.evaluate("chooseDirectoryStore('super-bareket::009');document.getElementById('supermarketPriceGrid').scrollIntoView({block:'start'});scrollBy(0,-120)")
        pg.screenshot(path=str(OUT/(tag+'-branch-comparison.png')))
        # Schema-3 rejection tests use local copies and never change the shipped data.
        validation=pg.evaluate("""(()=>{const d=state.livePrices,clone=()=>JSON.parse(JSON.stringify(d)),k=PRICE_CHAINS[0],ing=Object.keys(d.ingredients).find(i=>d.ingredients[i][k]);const tests=[];
          let x=clone();x.metadata.chains[k].store_id='99999';tests.push(!validatePricesFile(x).ok);
          x=clone();x.metadata.chains[k].chain='wrong-chain';tests.push(!validatePricesFile(x).ok);
          x=clone();x.ingredients[ing][k].packPrice=-1;tests.push(!validatePricesFile(x).ok);
          x=clone();x.ingredients[ing][k].packPrice='12.9';tests.push(!validatePricesFile(x).ok);
          x=clone();x.ingredients[ing][k].packQty=0;tests.push(!validatePricesFile(x).ok);
          x=clone();x.ingredients[ing][k].packUnit='mystery';tests.push(!validatePricesFile(x).ok);
          x=clone();x.metadata.version='999';tests.push(!validatePricesFile(x).ok);
          x=clone();delete x.metadata.chains[k];tests.push(!validatePricesFile(x).ok);
          return tests;})()""")
        check(tag+' rejects invalid schema/store/price/pack/source values',len(validation)==8 and all(validation),validation)
        # The 48-hour window also expires during an already-open session.
        gate=pg.evaluate("""(()=>{const k=PRICE_CHAINS.find(k=>isChainPublished(k)),m=state.livePrices.metadata.chains[k],old=m.published_at;
          m.published_at=new Date(Date.now()-49*3600000).toISOString();const stale=!isChainPublished(k);m.published_at=new Date(Date.now()+2*3600000).toISOString();const future=!isChainPublished(k);m.published_at=old;return stale&&future;})()""")
        check(tag+' stale/future source cannot remain actual in open session',gate)
        check(tag+' default cards are exactly online plus Givat Shmuel',pg.evaluate("JSON.stringify(comparedStoreConfigs().map(s=>normChainKey(s.id)).sort())===JSON.stringify(STORE_DIRECTORY.default_compare_stores.slice().sort())"))
        # Nov 15 batch: Settings tab label, footnotes, picker selection model, pharmacy exclusion, card naming, pantry density, full macros coverage.
        check(tag+' Supermarkets tab is now Settings',pg.evaluate("document.getElementById('tabBtnPreferences').innerText.includes('Settings')"))
        check(tag+' feed info sits in cart footnotes',pg.evaluate("!!document.getElementById('cartFootnotes') && document.getElementById('cartFootnotes').contains(document.getElementById('feedStatusBadge')) && document.getElementById('cartFootnotes').contains(document.getElementById('planCoverageBadge')) && !document.getElementById('livePriceToolbar')"))
        check(tag+' complete-cart basis note is a footnote',pg.evaluate("(document.getElementById('cartBasisNote')||{}).textContent?.includes('Complete cart at every store')===true"))
        check(tag+' one checkbox per connected non-pharmacy store',pg.evaluate("document.querySelectorAll('#connectedStoreChecks input').length===12"))
        check(tag+' every comparison card shows chain - branch (place)',pg.evaluate("[...document.querySelectorAll('#supermarketPriceGrid > div')].map(d=>d.querySelector('span.break-words')).filter(Boolean).every(s=>s.textContent.includes(' - ')&&s.textContent.includes('('))"))
        check(tag+' directory marks pharmacy branches',pg.evaluate("Object.values(STORE_DIRECTORY.stores).some(s=>s.kind==='pharmacy')"))
        pg.fill('#branchSearch','גבעת שמואל')
        check(tag+' Givat Shmuel search shows supermarkets only',pg.evaluate("[...document.querySelectorAll('#branchResults button')].length===4 && ![...document.querySelectorAll('#branchResults button')].some(b=>/BE |Be פארם/.test(b.textContent))"))
        pg.fill('#branchSearch','')
        r=pg.evaluate("""(()=>{const before=document.querySelectorAll('#supermarketPriceGrid > div').length;
          const lab=[...document.querySelectorAll('#connectedStoreChecks label')].find(l=>l.textContent.includes('טיב טעם'));lab.querySelector('input').click();
          const after=document.querySelectorAll('#supermarketPriceGrid > div').length;
          const lab2=[...document.querySelectorAll('#connectedStoreChecks label')].find(l=>l.textContent.includes('טיב טעם'));lab2.querySelector('input').click();
          const restored=document.querySelectorAll('#supermarketPriceGrid > div').length;
          return {before,after,restored};})()""")
        check(tag+' store checkbox hides and restores its card',r['before']==12 and r['after']==11 and r['restored']==12,r)
        # Near-me is async now (real geolocation with Givat Shmuel fallback). Stub a denial so the
        # fallback resolves immediately: selection must equal the Givat Shmuel physical branches.
        pg.evaluate("navigator.geolocation={getCurrentPosition:(ok,err)=>err({code:1,message:'denied'})}")
        pg.evaluate("document.getElementById('btnCompareNearMe').click()")
        pg.wait_for_function("document.getElementById('btnCompareNearMe').textContent!=='Locating...'", timeout=15000)
        r=pg.evaluate("""(()=>{const near=getCompareSelection().slice().sort();
          document.getElementById('btnCompareOnline').click();const online=getCompareSelection().slice().sort();
          document.getElementById('btnCompareAll').click();const all=getCompareSelection().length;
          return {near,online,all};})()""")
        # Online quick select: every directory store of kind 'online' (grew with the national directory).
        check(tag+' near me / online / all quick select',r['near']==['fresh-market::047','rami-levy::712','super-bareket::009','super-bareket::065'] and r['online']==sorted(['keshet-teamim::116','keshet-teamim::120','rami-levy::039','shufersal::413','shuk-hayir::304','shuk-hayir::305','shuk-hayir::309','shuk-hayir::311','shuk-hayir::312','shuk-hayir::319','super-sapir::034','tiv-taam::502','tiv-taam::503','tiv-taam::512','tiv-taam::514','tiv-taam::515','tiv-taam::519']) and r['all']==12,r)
        check(tag+' selection restored to all connected',pg.evaluate("comparedStoreConfigs().length===12"))
        pg.evaluate("switchTab('Pantry')")
        check(tag+' pantry staples are compact multi-column on phone',pg.evaluate("document.getElementById('pantryGridContainer').className.includes('grid-cols-2') && document.querySelector('#pantryGridContainer > div').className.includes('flex items-center')"))
        check(tag+' all recipe ingredients have nutrition coverage',pg.evaluate("RECIPES.every(r=>{const m=computeRecipeMacros(r.id);return m && m.missing.length===0;})"))
        pg.evaluate("switchTab('Cart')")
        # Specific local branches from two chains outside the old six.
        for key in ['rami-levy::712','fresh-market::047','super-bareket::009','super-bareket::065','osher-ad::032','yochananof::015','tiv-taam::025','super-yuda::241','shefa-birkat-hashem::023']:
            pg.evaluate('(k)=>chooseDirectoryStore(k)',key)
            st=pg.evaluate("({key:normChainKey(state.currentStore),actual:calculateCartTotals().actualCount,online:!document.getElementById('btnOpenOnlineCartModal').hidden,links:[...document.querySelectorAll('#groceryAislesContainer a')].filter(a=>a.textContent.includes('Online')).length,offers:activeStoreOffers(normChainKey(state.currentStore)).length})")
            check(tag+' physical branch isolation '+key,st['key']==key and not st['online'] and st['links']==0,st)
            check(tag+' connected physical branch has actual products '+key,st['actual']>0,st)
            pg.evaluate('openOnlineCartModal()');check(tag+' physical direct modal call blocked '+key,not pg.locator('#onlineCartModal').is_visible())
        # Local/online filtering is genuine and searchable.
        pg.select_option('#branchChainFilter','super-bareket');pg.select_option('#branchKindFilter','physical');pg.fill('#branchSearch','הזיתים')
        check(tag+' search by branch address/name',pg.locator('#branchResults button').count()==1 and pg.locator('#branchResults').inner_text().find('009')>=0)
        # A directory-only store never borrows another branch price as an actual line.
        missing=pg.evaluate("Object.keys(STORE_DIRECTORY.stores).find(k=>!state.livePrices.metadata.chains[k] && STORE_DIRECTORY.stores[k].kind==='physical')")
        pg.evaluate('(k)=>chooseDirectoryStore(k)',missing)
        check(tag+' directory-only branch is explicit estimates',pg.evaluate("calculateCartTotals().actualCount===0 && !isChainPublished(normChainKey(state.currentStore)) && document.getElementById('storeDeals').innerText.includes('unavailable')"))
        # Online remains a real separate branch, not a global online switch over physical prices.
        for key in ['shufersal::413','rami-levy::039']:
            pg.evaluate('(k)=>chooseDirectoryStore(k)',key)
            check(tag+' online branch launch available '+key,pg.locator('#btnOpenOnlineCartModal').is_visible())
            pg.click('#btnOpenOnlineCartModal');check(tag+' online branch modal usable '+key,pg.locator('#onlineCartModal').is_visible())
            check(tag+' online destination belongs to selected store '+key,pg.evaluate("document.getElementById('btnLaunchOnlineStore').href===SUPERMARKETS[state.currentStore].onlineUrl"))
            pg.evaluate('closeOnlineCartModal()')
        # Future/expired/stale promo files do not claim current deals.
        r=pg.evaluate("""(()=>{const k=normChainKey(state.currentStore),backup=state.livePrices.promotions[k],fresh=state.chainFresh[k],now=Date.now();
          const offer={promotion_id:'SYNTHETIC',start_time:new Date(now-1000).toISOString(),end_time:new Date(now+10000).toISOString(),items:[]};
          const a={status:'ok',published_at:new Date(now).toISOString(),offers:[offer]};state.livePrices.promotions[k]=a;
          const active=activeStoreOffers(k).length;a.offers=[{...offer,end_time:new Date(now-1).toISOString()}];const expired=activeStoreOffers(k).length;
          a.offers=[{...offer,start_time:new Date(now+1000).toISOString()}];const future=activeStoreOffers(k).length;
          a.offers=[offer];a.published_at=new Date(now-49*3600000).toISOString();const stale=activeStoreOffers(k).length;
          a.published_at=new Date(now).toISOString();state.chainFresh[k]=false;const noPriceSource=activeStoreOffers(k).length;
          state.livePrices.promotions[k]=backup;state.chainFresh[k]=fresh;return {active,expired,future,stale,noPriceSource};})()""")
        check(tag+' promotion validity and store freshness gates',r=={'active':1,'expired':0,'future':0,'stale':0,'noPriceSource':0},r)
        # Promo rendering is informational; it must not silently deduct club/coupon offers.
        r=pg.evaluate("""(()=>{const before=calculateCartTotals().totalCart;renderStoreDeals();const after=calculateCartTotals().totalCart;return {before,after,text:document.getElementById('storeDeals').innerText};})()""")
        check(tag+' deals never silently alter basket',r['before']==r['after'] and 'not automatically deducted' in r['text'])
        # Merchant tabs change both selected store and the priced basket source.
        pg.evaluate("chooseDirectoryStore('shufersal::413');openOnlineCartModal();state.onlineStoreSelected='rami_levy';renderOnlineCartContent()")
        check(tag+' online modal switch uses the requested online retailer',pg.evaluate("document.getElementById('btnLaunchOnlineStore').href===SUPERMARKETS.rami_levy.onlineUrl"))
        pg.evaluate('closeOnlineCartModal()')
        # Save/restore selected non-default branch and its comparison card.
        pg.evaluate("chooseDirectoryStore('super-bareket::009')");pg.reload();pg.wait_for_function("state.livePricesLoaded && SUPERMARKETS[state.currentStore]?.priceKey==='super-bareket::009'")
        check(tag+' branch choice survives reload',pg.evaluate("normChainKey(state.currentStore)==='super-bareket::009' && !document.getElementById('btnOpenOnlineCartModal').isConnected===false && document.getElementById('btnOpenOnlineCartModal').hidden"))
        pg.evaluate("switchTab('Cart'); document.getElementById('branchPicker').scrollIntoView({block:'start'});scrollBy(0,-120)")
        pg.screenshot(path=str(OUT/(tag+'-stores.png')))
        check(tag+' no horizontal page overflow',pg.evaluate('document.documentElement.scrollWidth<=innerWidth'),pg.evaluate('({scroll:document.documentElement.scrollWidth,width:innerWidth})'))
        # Check every displayed element, not just the page width.
        over=pg.evaluate("[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();let a=e.parentElement;while(a){const st=getComputedStyle(a);if(['auto','scroll'].includes(st.overflowX)&&a.scrollWidth>a.clientWidth+1)return false;a=a.parentElement;}return r.width>0&&r.height>0&&getComputedStyle(e).position!=='fixed'&&(r.right>innerWidth+2 || r.left < -2)}).slice(0,15).map(e=>e.id||e.className)")
        check(tag+' no element escapes viewport',not over,over)
        pg.evaluate("chooseDirectoryStore('shufersal::413');document.getElementById('storeDeals').scrollIntoView({block:'start'});scrollBy(0,-120)")
        pg.screenshot(path=str(OUT/(tag+'-deals.png')))
        check(tag+' no JavaScript errors',not errors,errors)
        pg.close()
    b.close()
srv.shutdown();print('STORE UI CHECKS',checks,'FAILURES',len(fail));sys.exit(bool(fail))
