"""Synthetic data only: GTIN identity, quarantine, pack capacity, branch separation."""
import sys, unittest, copy, tempfile, json, subprocess
from unittest.mock import patch
from datetime import timedelta
from israeli_prices import PromoFile,Promotion,PromotionItem
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import sync_stores as ss
import fetch_prices as fp
from israeli_prices import PriceItem,FileRef,FileType

def barcode(first12='729123456789'):
    return first12+str((-sum(int(x)*(1 if i%2==0 else 3) for i,x in enumerate(first12)))%10)
CODE=barcode();NAME='אורז בסמטי 1 ק"ג'
def make_item(code=CODE,name=NAME,price='12.9',weighted=False,qty='1'):
    return PriceItem(item_code=code,name=name,price=Decimal(price),unit_qty='ק"ג',quantity=Decimal(qty),is_weighted=weighted)
def feed(items):return {'ref':FileRef(chain='super-yuda',name='pricefull-SYNTHETIC-201.gz',file_type=FileType.PRICE_FULL,url='https://invalid.test',store_id='201',published_at=datetime.now(timezone.utc)),'items':items,'sha256':'a'*64,'retrieved_at':datetime.now(timezone.utc).isoformat()}

class StoreSync(unittest.TestCase):
    def setUp(self):
        self.pin={'item_code':CODE,'pinned_name':NAME,'selected_by':'assistant'}
        self.maps={'pins':{'Rice':{'rami-levy':self.pin}}}
        self.old={'ingredients':{'rice':{'ingredient_name':'Rice','rami-levy':{'item_code':CODE,'nameHe':NAME,'gtin':ss.safe_gtin(CODE),'packQty':1000,'packUnit':'g','isWeighted':False}}}}
        self.store={'store_id':'201','name':'TEST BRANCH','kind':'physical','address':'TEST ADDRESS'}
    def build(self,items,maps=None,q=None):
        maps=maps or self.maps;q=q or set();can=ss.canonical_products(self.old,maps,q)
        return ss.prices_for_store('super-yuda',self.store,feed(items),maps,can,q)
    def test_valid_gtin_padding(self):self.assertEqual(ss.safe_gtin(CODE),'0'+CODE)
    def test_bad_checksum_rejected(self):self.assertIsNone(ss.safe_gtin(CODE[:-1]+str((int(CODE[-1])+1)%10)))
    def test_chain_internal_short_code_rejected(self):self.assertIsNone(ss.safe_gtin('1234'))
    def test_weighted_not_cross_matched(self):self.assertIsNone(ss.safe_gtin(CODE,True));d,_=self.build([make_item(weighted=True)]);self.assertFalse(d['ingredients'])
    def test_restricted_distribution_not_cross_matched(self):self.assertIsNone(ss.safe_gtin(barcode('231234567890')))
    def test_exact_match_moves_pin_once(self):
        d,p=self.build([make_item()]);self.assertFalse(p);e=d['ingredients']['rice']['super-yuda::201'];self.assertEqual(e['matchMethod'],'exact-gtin');self.assertEqual(e['packQty'],1000);self.assertEqual(e['selectionSource'],'assistant');self.assertEqual(d['metadata']['chains']['super-yuda::201']['store_id'],'201')
    def test_schema3_source_can_seed(self):
        self.old['ingredients']['rice']['rami-levy::039']=self.old['ingredients']['rice'].pop('rami-levy');d,_=self.build([make_item()]);self.assertTrue(d['ingredients'])
    def test_same_name_different_barcode_no_match(self):d,_=self.build([make_item(code=barcode('729123456788'))]);self.assertFalse(d['ingredients'])
    def test_same_barcode_different_name_no_match(self):d,_=self.build([make_item(name='פסטה 1 ק"ג')]);self.assertFalse(d['ingredients'])
    def test_same_barcode_wrong_size_no_match(self):d,_=self.build([make_item(name='אורז בסמטי 2 ק"ג',qty='2')]);self.assertFalse(d['ingredients'])
    def test_duplicate_barcode_ambiguous_no_match(self):d,_=self.build([make_item(),make_item()]);self.assertFalse(d['ingredients'])
    def test_quarantined_source_cannot_seed(self):d,_=self.build([make_item()],q={('rice','rami-levy',CODE)});self.assertFalse(d['ingredients'])
    def test_quarantined_target_cannot_price(self):d,_=self.build([make_item()],q={('rice','super-yuda',CODE)});self.assertFalse(d['ingredients'])
    def test_unselected_cannot_seed(self):self.pin.pop('selected_by');d,_=self.build([make_item()]);self.assertFalse(d['ingredients'])
    def test_user_selection_stays_user_selection(self):self.pin.pop('selected_by');self.pin['approved_by_user']=True;d,_=self.build([make_item()]);self.assertEqual(d['ingredients']['rice']['super-yuda::201']['selectionSource'],'user')
    def test_unknown_pack_is_unpriced(self):d,_=self.build([PriceItem(item_code=CODE,name='אורז בסמטי',price=Decimal('2'),quantity=None,unit_qty=None)]);self.assertFalse(d['ingredients'])
    def test_nonpositive_price_unpriced(self):d,_=self.build([make_item(price='0')]);self.assertFalse(d['ingredients'])
    def test_different_branches_never_share_source(self):
        d,_=self.build([make_item()]);self.store['store_id']='202';d2,_=self.build([make_item(price='19')]);self.assertEqual(d['ingredients']['rice']['super-yuda::201']['packPrice'],12.9);self.assertEqual(d2['ingredients']['rice']['super-yuda::202']['packPrice'],19)
    def test_preserves_source_timestamp(self):
        f=feed([make_item()]);f['ref'].published_at=datetime(2020,1,1,tzinfo=timezone.utc);d,_=ss.prices_for_store('super-yuda',self.store,f,self.maps,ss.canonical_products(self.old,self.maps,set()),set());self.assertTrue(d['metadata']['chains']['super-yuda::201']['published_at'].startswith('2020-01-01'))
    def test_drained_capacity_does_not_become_gross(self):
        self.maps['capacity_basis']={'ingredients':['Rice']};d,_=self.build([make_item()]);self.assertNotIn('super-yuda::201',d['ingredients'].get('rice',{}))
    def test_chain_local_pin_keeps_manual_code(self):
        self.maps['pins']['Rice']['super-yuda']={'item_code':'1234','pinned_name':NAME,'selected_by':'assistant'};d,_=self.build([make_item(code='1234')]);self.assertEqual(d['ingredients']['rice']['super-yuda::201']['matchMethod'],'chain-local-pin')
    def test_seed_name_drift_rejected(self):self.old['ingredients']['rice']['rami-levy']['nameHe']='unrelated product';d,_=self.build([make_item()]);self.assertFalse(d['ingredients'])

class PromoSync(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.ref=FileRef(chain='super-yuda',name='promofull-SYNTHETIC-201.gz',file_type=FileType.PROMO_FULL,url='https://invalid.test/promo.gz',store_id='201',published_at=self.now)
        self.offer=Promotion(promotion_id='TEST',description='SYNTHETIC club offer',start_time=self.now-timedelta(hours=1),end_time=self.now+timedelta(hours=1),club_id='TEST CLUB',is_coupon=True,min_qty=Decimal('2'),min_purchase_amount=Decimal('50'),items=[PromotionItem(item_code=CODE,discounted_price=Decimal('8.9'),min_qty=Decimal('2')),PromotionItem(item_code='not-mapped')])
    def call(self,pf):
        with patch.object(ss,'list_files',return_value=[self.ref]),patch.object(ss,'get_adapter') as a,patch.object(ss,'parse',return_value=pf):
            a.return_value.download.return_value=b'SYNTHETIC PROMO BYTES'
            return ss.fetch_promos('super-yuda','201',{CODE})
    def test_keeps_conditions_and_only_relevant_products(self):
        d=self.call(PromoFile(store_id='201',promotions=[self.offer]));p=d['offers'][0]
        self.assertEqual(p['club_id'],'TEST CLUB');self.assertTrue(p['is_coupon']);self.assertEqual(p['min_purchase_amount'],'50');self.assertEqual(p['min_qty'],'2');self.assertEqual(len(p['items']),1);self.assertEqual(p['offer_group_item_count'],2);self.assertIn('+00:00',p['end_time']);self.assertEqual(d['source_url'],self.ref.url)
    def test_wrong_store_not_accepted(self):
        with self.assertRaisesRegex(ValueError,'store identity'):self.call(PromoFile(store_id='202',promotions=[self.offer]))
    def test_wrong_retailer_not_accepted(self):
        with self.assertRaisesRegex(ValueError,'retailer identity'):self.call(PromoFile(store_id='201',chain_id='WRONG',promotions=[self.offer]))
    def test_expired_future_undated_no_offers(self):
        cases=[self.offer.model_copy(update={'end_time':self.now-timedelta(seconds=2)}),self.offer.model_copy(update={'start_time':self.now+timedelta(days=1)}),self.offer.model_copy(update={'end_time':None})]
        self.assertEqual(self.call(PromoFile(store_id='201',promotions=cases))['offers'],[])
    def test_other_product_offer_not_matched(self):
        self.offer.items=[PromotionItem(item_code='OTHER')];self.assertEqual(self.call(PromoFile(store_id='201',promotions=[self.offer]))['offers'],[])
    def test_promo_listing_must_match_store(self):
        self.ref.store_id='202'
        with self.assertRaisesRegex(ValueError,'No dated'):self.call(PromoFile(store_id='201',promotions=[self.offer]))
    def test_listing_without_source_date_not_current(self):
        self.ref.published_at=None
        with self.assertRaisesRegex(ValueError,'No dated'):self.call(PromoFile(store_id='201',promotions=[self.offer]))

class FailureSafety(unittest.TestCase):
    def test_download_failure_preserves_original_date_and_quarantine(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            data={'metadata':{'version':'2.1','chains':{'rami-levy':{'store_id':'039','store_name':'TEST','published_at':'2020-01-01T00:00:00Z','priced_count':2,'source_file':'OLD'}}},'ingredients':{'rice':{'ingredient_name':'Rice','rami-levy':{'item_code':CODE,'packPrice':5,'packQty':1000,'packUnit':'g'}},'bad':{'ingredient_name':'Bad','rami-levy':{'item_code':'123','packPrice':5,'packQty':1000,'packUnit':'g'}}}}
            for name,d in [('prices.json',data),('mappings.json',{'pins':{},'conversions':{}}),('stores.json',{'stores':{'rami-levy::039':{'chain':'rami-levy','kind':'online','store_id':'039','name':'TEST'}}}),('store_config.json',{'refresh_stores':['rami-levy::039'],'workers':1,'store_timeout_seconds':1}),('quarantine.json',{'items':[{'ingredient':'Bad','chain':'rami-levy','item_code':'123'}]})]:
                (root/name).write_text(json.dumps(d))
            with patch.object(ss,'ROOT',root),patch.object(ss.subprocess,'run',side_effect=subprocess.TimeoutExpired('synthetic',1)):
                rc=ss.run()
            new=json.loads((root/'prices.json').read_text());self.assertEqual(rc,1);self.assertEqual(new['metadata']['chains']['rami-levy::039']['priced_count'],1);self.assertEqual(new['metadata']['chains']['rami-levy::039']['published_at'],'2020-01-01T00:00:00Z');self.assertIn('rami-levy::039',new['ingredients']['rice']);self.assertNotIn('rami-levy::039',new['ingredients']['bad']);self.assertEqual(new['sync_status']['rami-levy::039']['status'],'failed')
    def test_nonfinite_feed_numbers_are_never_prices(self):
        for v in ['NaN','Infinity','-Infinity']:self.assertIsNone(fp.dnum(v))

if __name__=='__main__':unittest.main()
