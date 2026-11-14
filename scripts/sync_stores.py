#!/usr/bin/env python3
"""Store-specific snapshots for static hosting. No browser-time retailer requests.
Only configured stores are polled; catalog-only stores are explicitly unpriced.
All network workers have a wall-clock deadline. Existing timestamps survive failures.
"""
import argparse, copy, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
import fetch_prices as fp
from israeli_prices import list_chains, get_stores, FileType, get_adapter, list_files, parse, to_gtin14
ROOT=Path(__file__).resolve().parents[1]

def read(path, default=None):
    try:return json.loads(Path(path).read_text())
    except FileNotFoundError:return default

def store_key(chain, sid):return chain+'::'+str(sid).zfill(3)

def safe_gtin(code, weighted=False):
    if weighted:return None
    gt=to_gtin14(str(code))
    if not gt:return None
    # GS1 restricted distribution / variable-measure prefixes are not cross-retailer identities.
    base=gt.lstrip('0')
    if len(base)==13 and base[:2] in {str(n) for n in range(20,30)}:return None
    return gt

def canonical_products(old, mappings, quarantine):
    """Only previously selected, validated exact products may seed cross-store matching.
    An explicit canonical mapping may narrow an ingredient to one barcode later.
    Conflicting brand choices remain separate exact alternatives, never fuzzy equivalents.
    """
    out={}
    for ing, per in mappings['pins'].items():
        entries=(old.get('ingredients',{}).get(ing.lower().strip()) or {})
        for chain,pin in per.items():
            if not (pin.get('approved_by_user') is True or pin.get('selected_by')=='assistant'):continue
            code=str(pin.get('item_code','')); e=entries.get(chain)
            if not e: # schema 3 carries original default branch entries by store key
                cfg=fp.CHAINS.get(chain)
                if cfg:e=entries.get(store_key(chain,cfg['store_id']))
            if not e or str(e.get('item_code'))!=code:continue
            if (ing.lower().strip(),chain,code) in quarantine:continue
            gt=safe_gtin(code,e.get('isWeighted'))
            if not gt or not fp.same_product_name(e.get('nameHe'),pin.get('pinned_name')):continue
            # The validated pack basis, including drained size, travels only with this exact GTIN.
            out.setdefault(ing,[]).append({'gtin':gt,'source_chain':chain,'entry':e,'pin':pin})
    for ing, arr in out.items():
        arr.sort(key=lambda x:(not bool(x['pin'].get('approved_by_user')),x['source_chain']))
    return out

def prices_for_store(chain, store, feed, mappings, canonical, quarantine):
    key=store_key(chain,store['store_id']); local={}; origins={}
    by_gt={}
    for it in feed['items']:
        gt=safe_gtin(it.item_code,it.is_weighted)
        if gt:by_gt.setdefault(gt,[]).append(it)
    for ing,per in mappings['pins'].items():
        explicit=per.get(chain)
        # Chain-local codes are permitted only within their own chain. Names and packs still validate.
        if explicit and (explicit.get('approved_by_user') or explicit.get('selected_by')=='assistant'):
            if (ing.lower().strip(),chain,str(explicit.get('item_code'))) not in quarantine:
                local.setdefault(ing,{})[key]=copy.deepcopy(explicit)
        if key in local.get(ing,{}):continue
        for seed in canonical.get(ing,[]):
            matches=by_gt.get(seed['gtin'],[])
            if len(matches)!=1:continue # ambiguous feed duplicates do not choose silently
            it=matches[0]
            if (ing.lower().strip(),chain,str(it.item_code)) in quarantine:continue
            pk=fp.derive_pack(it); src=seed['entry']
            if not pk or pk['unit']!=src['packUnit'] or abs(pk['qty']-src.get('grossPackQty',src['packQty']))>1e-6:continue
            if not fp.same_product_name(it.name,src['nameHe']):continue
            pin=copy.deepcopy(seed['pin']);pin['item_code']=str(it.item_code);pin['pinned_name']=it.name
            # Overrides from another chain are not generalized to a new feed.
            pin.pop('pack_override',None)
            local.setdefault(ing,{})[key]=pin;origins[ing]=(seed['source_chain'],seed['gtin']);break
    fp.CHAINS[key]={'store_id':store['store_id'],'store_name':store['name']}
    fp.QUARANTINED={(i,key,c) for i,ch,c in quarantine if ch==chain}
    data,warnings=fp.build_prices({key:feed},local)
    cap=(mappings.get('capacity_basis') or {}).get('ingredients') or []
    warnings+=fp.apply_capacity_basis(data,local,cap)
    for ing,e in data['ingredients'].items():
        item=e.get(key)
        if item and e['ingredient_name'] in origins:
            ch,gt=origins[e['ingredient_name']];item['matchMethod']='exact-gtin';item['matchedFromChain']=ch
        elif item:item['matchMethod']='chain-local-pin'
    m=data['metadata']['chains'][key];m.update(chain=chain,store_id=store['store_id'],store_name=store['name'],kind=store['kind'],address=store.get('address'),city=store.get('city'))
    return data,warnings

def fetch_promos(chain, sid, codes):
    refs=list_files(chain,file_type=FileType.PROMO_FULL,store_id=sid,limit=20)
    refs=[r for r in refs if r.file_type==FileType.PROMO_FULL and str(r.store_id).lstrip('0')==str(sid).lstrip('0') and r.published_at]
    if not refs:raise ValueError('No dated, store-specific PromoFull file')
    ref=max(refs,key=lambda r:r.published_at);raw=get_adapter(chain).download(ref);pf=parse(raw)
    expected=next((c.chain_id for c in list_chains() if c.slug==chain),None)
    if ref.chain!=chain or (expected and pf.chain_id and str(pf.chain_id)!=expected):raise ValueError('Promo retailer identity mismatch')
    if str(pf.store_id).lstrip('0')!=str(sid).lstrip('0'):raise ValueError('Promo store identity mismatch')
    now=datetime.now(timezone.utc);out=[]
    for p in pf.promotions:
        def aware(d):return d.replace(tzinfo=ZoneInfo('Asia/Jerusalem')) if d and not d.tzinfo else d
        start,end=aware(p.start_time),aware(p.end_time)
        # Missing validity bounds are unknown, not an active offer.
        if not start or not end or not start<=now<=end:continue
        relevant=[i for i in p.items if str(i.item_code) in codes]
        if not relevant:continue
        offer=p.model_dump(mode='json');offer['items']=[i.model_dump(mode='json') for i in relevant];offer['start_time']=start.isoformat();offer['end_time']=end.isoformat();offer['offer_group_item_count']=len(p.items);out.append(offer)
    return {'status':'ok','source_file':ref.name,'source_url':ref.url,'published_at':fp.iso_with_tz(ref.published_at),'retrieved_at':now.isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),'offers':out}

def worker(chain,sid,path):
    store=read(ROOT/'stores.json')['stores'][store_key(chain,sid)]
    old=read(ROOT/'prices.json',{});reference=read(ROOT/'data/matching_reference.json',{});
    for ing,e in reference.get('ingredients',{}).items():
        target=old.setdefault('ingredients',{}).setdefault(ing,{'ingredient_name':e['ingredient_name']})
        for key,item in e.items():target.setdefault(key,item)
    maps=read(ROOT/'mappings.json');q=fp.load_quarantine(str(ROOT/'quarantine.json'))
    canonical=canonical_products(old,maps,q)
    feed=fp.fetch_chain(chain,sid,retries=1)
    data,warnings=prices_for_store(chain,store,feed,maps,canonical,q)
    codes={e[store_key(chain,sid)]['item_code'] for e in data['ingredients'].values() if store_key(chain,sid) in e}
    try:promo=fetch_promos(chain,sid,codes)
    except Exception as e:promo={'status':'unavailable','reason':str(e),'offers':[]}
    data['promotions']={store_key(chain,sid):promo};data['warnings']=warnings
    fp.atomic_write(path,data)

def catalog(use_cached=False):
    prev=read(ROOT/'stores.json',{});stores={};statuses={}
    for c in list_chains(implemented_only=True):
        if c.sector!='supermarket':continue
        cache=ROOT/'data/directories'/f'{c.slug}.json';cache.parent.mkdir(parents=True,exist_ok=True)
        try:
            if use_cached:
                obj=read(cache)
                if obj is None:raise ValueError('Live discovery failed; no verified directory')
                rows=obj['stores']
            else:
                result=subprocess.run([sys.executable,__file__,'--directory-worker',c.slug,str(cache)],capture_output=True,text=True,timeout=75)
                if result.returncode:raise RuntimeError(result.stderr[-500:])
                rows=read(cache)['stores']
            statuses[c.slug]={'name':c.name,'nameHe':c.name_he,'status':'ok','source':c.portal_url}
            counts={}
            for s in rows:counts[s['store_id']]=counts.get(s['store_id'],0)+1
            for s in rows:
                if counts[s['store_id']]>1:continue # ambiguous identity needs sub-chain support first
                name=s.get('name') or c.name_he;online=s.get('store_type')==2 or any(w in name.lower() for w in ['online','אונליין','אינטרנט'])
                key=store_key(c.slug,s['store_id'])
                city=s.get('city') or '';city_code=city if city.isdigit() else None;city='גבעת שמואל' if city=='681' else ('' if city.isdigit() else city) # verified city 681 from explicit local branch records
                stores[key]={'key':key,'chain':c.slug,'chain_name':c.name,'chain_name_he':c.name_he,'store_id':s['store_id'],'name':name,'address':s.get('address') or '', 'city':city,'kind':'online' if online else 'physical','directory_source':c.portal_url,'city_code':city_code}
                if c.slug=='shufersal' and s.get('sub_chain_name')=='Be':stores[key].update(chain_name='Be pharmacy (Shufersal feed)',chain_name_he='Be פארם')
        except Exception as e:
            statuses[c.slug]={'name':c.name,'nameHe':c.name_he,'status':'unavailable','reason':str(e),'source':c.portal_url}
            for k,s in prev.get('stores',{}).items():
                if s['chain']==c.slug:stores[k]=s
    # Retain the established Victory online catalog as an explicitly stale/unavailable source.
    stores['victory::2331']={'key':'victory::2331','chain':'victory','chain_name':'Victory','chain_name_he':'ויקטורי','store_id':'2331','name':'ויקטורי אונליין','kind':'online','address':'','city':'','directory_source':'https://www.victoryonline.co.il/'}
    obj={'version':'1','default_compare_stores':read(ROOT/'store_config.json',{}).get('default_compare_stores',[]),'checked_at':datetime.now(timezone.utc).isoformat(),'stores':stores,'chains':statuses}
    fp.atomic_write(str(ROOT/'stores.json'),obj);return obj

def run(only=None):
    cat=read(ROOT/'stores.json');config=read(ROOT/'store_config.json');old=read(ROOT/'prices.json',{})
    out={'metadata':{'version':'3','chains':{},'sync_attempted_at':datetime.now(timezone.utc).isoformat()},'ingredients':{},'conversions':read(ROOT/'mappings.json').get('conversions',{}),'promotions':{},'sync_status':{}}
    # Upgrade the old branch-labeled snapshot without inventing a newer source timestamp.
    oldkeys={'victory':'victory::2331'}
    oldkeys.update({c:store_key(c,s['store_id']) for c,s in fp.CHAINS.items() if '::' not in c})
    for ck,m in old.get('metadata',{}).get('chains',{}).items():
        key=oldkeys.get(ck,ck)
        if key not in config['refresh_stores']:continue
        out['metadata']['chains'][key]=m
        if key in cat['stores']:out['metadata']['chains'][key].update(chain=cat['stores'][key]['chain'],kind=cat['stores'][key]['kind'])
        for ing,e in old.get('ingredients',{}).items():
            if ck in e:out['ingredients'].setdefault(ing,{'ingredient_name':e['ingredient_name']})[key]=e[ck]
        if key in old.get('promotions',{}):out['promotions'][key]=old['promotions'][key]
    selected=only or config['refresh_stores']
    def one(key):
        if key not in cat['stores']:return key,None,'Not in verified directory'
        c=cat['stores'][key];dest=ROOT/'data/stores'/f'{key.replace("::","--")}.json'
        dest.parent.mkdir(parents=True,exist_ok=True)
        try:
            p=subprocess.run([sys.executable,__file__,'--worker',c['chain'],c['store_id'],str(dest)],capture_output=True,text=True,timeout=config.get('store_timeout_seconds',110))
            if p.returncode:raise RuntimeError(p.stderr[-700:])
            return key,read(dest),None
        except Exception as e:return key,None,str(e)
    with ThreadPoolExecutor(max_workers=config.get('workers',3)) as pool:
        for key,data,err in pool.map(one,selected):
            if err:
                out['sync_status'][key]={'status':'failed','reason':err};print(key,'FAILED',err,flush=True);continue
            for ing,e in out['ingredients'].items():e.pop(key,None)
            out['metadata']['chains'].update(data['metadata']['chains'])
            for ing,e in data['ingredients'].items():out['ingredients'].setdefault(ing,{'ingredient_name':e['ingredient_name']}).update(e)
            out['promotions'].update(data['promotions']);out['sync_status'][key]={'status':'ok','warnings':data['warnings']}
            print(key,'OK',data['metadata']['chains'][key]['priced_count'],'priced',data['promotions'][key]['status'],'promos',flush=True)
    # quarantine also applies to preserved data
    quarantine=fp.load_quarantine(str(ROOT/'quarantine.json'))
    for ing,e in out['ingredients'].items():
        for key in list(e):
            if key=='ingredient_name':continue
            chain=key.split('::')[0]
            if (ing,chain,str(e[key]['item_code'])) in quarantine:del e[key]
    for key,meta in out['metadata']['chains'].items():meta['priced_count']=sum(key in e for e in out['ingredients'].values())
    fp.atomic_write(str(ROOT/'prices.json'),out)
    return 1 if selected and all(s['status']=='failed' for s in out['sync_status'].values()) else 0

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--worker',nargs=3);ap.add_argument('--directory-worker',nargs=2);ap.add_argument('--catalog',action='store_true');ap.add_argument('--cached-catalog',action='store_true');ap.add_argument('--stores');a=ap.parse_args()
    if a.directory_worker:
        chain,path=a.directory_worker;sf=get_stores(chain);fp.atomic_write(path,{'chain':next(c.model_dump() for c in list_chains() if c.slug==chain),'stores':[s.model_dump() for s in sf.stores]})
    elif a.worker:worker(*a.worker)
    elif a.catalog or a.cached_catalog:catalog(a.cached_catalog)
    else:sys.exit(run(a.stores.split(',') if a.stores else None))
