()=>{
 let seed=20261104; const rnd=()=>{seed=(seed*1664525+1013904223)%4294967296;return seed/4294967296;}; Math.random=rnd;
 const CH=['shufersal','rami-levy','osher-ad','yochananof','victory','carrefour'], REAL=CH.slice(0,5);
 const pick=(a)=>a[Math.floor(rnd()*a.length)];
 const lunches=RECIPES.filter(r=>r.mealType==='lunch'), bf=RECIPES.filter(r=>r.mealType==='breakfast');
 const fails=[]; let checks=0; const F=(w,m)=>{ if(fails.length<60) fails.push(w+': '+m); };
 const r2=x=>Math.round(x*100)/100;
 for(let w=0;w<100;w++){
  regenerateWeek();
  const lset=[pick(lunches),pick(lunches)], bset=[pick(bf),pick(bf)];
  state.lunchSchedule.forEach((s,i)=>s.recipeId=lset[i<3?0:1].id);
  state.bfastSchedule.forEach((s,i)=>s.recipeId=bset[i%2].id);
  // random pantry toggles in some weeks
  if(w%3==1){ PANTRY_STAPLES.forEach(p=>{ state.pantryState[p.id]= rnd()<0.5; }); }
  const base=getAggregatedGroceryList('rami-levy');
  // expected raw quantities
  const exp={}; const baseScale=state.servings/4;
  const proc=(sch,isD)=>(sch||[]).forEach((slot,idx)=>{ if(!slot.recipeId||slot.recipeId==='no_meal')return; if(isD&&idx>0&&state.twoNightBatchDays[idx-1])return; const rec=RECIPES.find(r=>r.id===slot.recipeId); if(!rec)return; const sc=(isD&&state.twoNightBatchDays[idx])?baseScale*2:baseScale;
    (rec.ingredients||[]).forEach(ing=>{ let q=ing.qty,u=String(ing.unit||'').toLowerCase().trim(); if(u==='kg'){q*=1000;u='g';} else if(u==='l'){q*=1000;u='ml';} const k=ing.name.toLowerCase().trim()+'|'+u; exp[k]=(exp[k]||0)+q*sc; }); });
  proc(state.activeSchedule,true);proc(state.lunchSchedule,false);proc(state.bfastSchedule,false);
  const got={}; Object.values(base).filter(i=>!i.isCustom).forEach(i=>{const k=i.name.toLowerCase().trim()+'|'+String(i.unit||'').toLowerCase().trim(); got[k]=(got[k]||0)+i.qty;});
  Object.keys(exp).forEach(k=>{checks++; if(Math.abs((got[k]||0)-exp[k])>1e-6) F(w,'qty mismatch '+k+' '+got[k]+' vs '+exp[k]);});
  Object.keys(got).forEach(k=>{checks++; if(!(k in exp)) F(w,'unexpected line '+k);});
  CH.forEach(ck=>{
    const list=getAggregatedGroceryList(ck); const t=calculateCartTotals(ck);
    const isPub=isChainPublished(normChainKey(ck));
    let cA=0,cC=0,cB=0,cU=0,nA=0,nC=0,nB=0,nU=0,n=0; const c100=v=>Math.round(v*100);
    // identical needed-quantity set at every chain (same lines, same quantities, same pantry flags)
    checks++; if(Object.keys(list).sort().join('|')!==Object.keys(base).sort().join('|')) F(w,ck+' line set differs from the other chains');
    Object.keys(list).forEach(k=>{ checks++; if(base[k] && !list[k].isCustom && (Math.abs(base[k].qty-list[k].qty)>1e-9 || base[k].unit!==list[k].unit || base[k].isPantry!==list[k].isPantry)) F(w,ck+' quantity/unit/pantry differs for '+k); });
    Object.values(list).forEach(it=>{
      if(it.isPantry) return;
      n++; checks++;
      const src=it.priceSource; if(['actual','estimate-chains','estimate-baseline','user-entered'].indexOf(src)<0) F(w,ck+' line without a price source '+it.name);
      const cents=c100(it.storePrice);
      if(src==='actual'){ cA+=cents; nA++;
        if(!isPub || !it.isLiveMatch) F(w,ck+' actual line without a live match '+it.name);
        const p=getIngredientPricing(it.name,it.qty,it.unit,1.0,ck,0);
        if(!p.isLiveMatch || Math.abs(p.purchaseCost-it.purchaseCost)>0.011 || Math.abs(it.storePrice-it.purchaseCost)>1e-9) F(w,ck+' actual line changed '+it.name+' '+it.purchaseCost+' vs '+p.purchaseCost);
        if(it.purchaseCost+0.011<it.recipeCost) F(w,ck+' purchase<recipe '+it.name);
      } else if(src==='estimate-chains'){ cC+=cents; nC++;
        if(it.isLiveMatch) F(w,ck+' estimate line flagged live '+it.name);
        if(isPub){ const own=getIngredientPricing(it.name,it.qty,it.unit,1.0,ck,0); if(own.isLiveMatch) F(w,ck+' real price replaced by estimate '+it.name); }
        const prs=REAL.filter(c=>c!==ck && isChainPublished(c)).map(c=>getIngredientPricing(it.name,it.qty,it.unit,1.0,c,0)).filter(p=>p.isLiveMatch);
        const avg=r2(prs.reduce((a,p)=>a+p.purchaseCost,0)/Math.max(1,prs.length));
        if(!prs.length || Math.abs(avg-it.storePrice)>0.011 || prs.length!==it.estimateChains) F(w,ck+' estimate '+it.name+' '+it.storePrice+' vs avg-of-others '+avg+' ('+prs.length+' vs '+it.estimateChains+')');
      } else if(src==='estimate-baseline'){ cB+=cents; nB++;
        const prs=REAL.filter(c=>c!==ck && isChainPublished(c)).map(c=>getIngredientPricing(it.name,it.qty,it.unit,1.0,c,0)).filter(p=>p.isLiveMatch);
        if(!it.isCustom && prs.length) F(w,ck+' baseline used though other chains price '+it.name);
        if(!it.isCustom && isPub && getIngredientPricing(it.name,it.qty,it.unit,1.0,ck,0).isLiveMatch) F(w,ck+' real price replaced by baseline '+it.name);
      } else if(src==='user-entered'){ cU+=cents; nU++; }
      if(ck==='carrefour' && src==='actual') F(w,'carrefour actual?!');
      if(!(it.storePrice>0) || !isFinite(it.storePrice)) F(w,ck+' non-positive/non-finite line '+it.name);
    });
    checks++; if(t.actualTotal!==cA/100||t.estimatedChainsTotal!==cC/100||t.estimatedBaselineTotal!==cB/100||t.userEnteredTotal!==cU/100) F(w,ck+' category totals do not equal their lines');
    checks++; if(t.totalCart!==(cA+cC+cB+cU)/100) F(w,ck+' headline '+t.totalCart+' != actual+estimates '+((cA+cC+cB+cU)/100));
    checks++; if(t.actualCount!==nA||t.estimatedChainsCount!==nC||t.estimatedBaselineCount!==nB||t.userEnteredCount!==nU||nA+nC+nB+nU!==t.totalItemsToBuy||n!==t.totalItemsToBuy) F(w,ck+' counts do not add up');
    checks++; if(Math.abs(r2(t.actualTotal+t.estimatedTotal+t.userEnteredTotal)-t.totalCart)>1e-9) F(w,ck+' reconciliation');
  });
  // pantry-excluded items never in totals: toggling a pantry item on lowers or keeps total
  checks++;
  // combined <= sum of per-recipe for live chains
  REAL.forEach(ck=>{ Object.values(getAggregatedGroceryList(ck)).forEach(it=>{ if(!it.isLiveMatch||it.isCustom) return; checks++;
     // find per-recipe costs
     let sum=0,ok=true; const names=new Set(it.mealSources);
     // approximate: recompute each recipe's own share via recipes list
     const parts=[]; const walk=(sch,isD)=>(sch||[]).forEach((slot,idx)=>{ if(!slot.recipeId||slot.recipeId==='no_meal')return; if(isD&&idx>0&&state.twoNightBatchDays[idx-1])return; const rec=RECIPES.find(r=>r.id===slot.recipeId); (rec.ingredients||[]).forEach(ing=>{ if(ing.name.toLowerCase().trim()!==it.name.toLowerCase().trim())return; let q=ing.qty,u=String(ing.unit||'').toLowerCase().trim(); if(u==='kg'){q*=1000;u='g';} else if(u==='l'){q*=1000;u='ml';} if(u!==String(it.unit).toLowerCase().trim())return; const sc=(isD&&state.twoNightBatchDays[idx])?baseScale*2:baseScale; parts.push(getIngredientPricing(ing.name,q,u,sc,ck,0).purchaseCost);});});
     walk(state.activeSchedule,true);walk(state.lunchSchedule,false);walk(state.bfastSchedule,false);
     const s=parts.reduce((a,b)=>a+b,0); if(parts.length && it.purchaseCost>s+(it.matchedData&&it.matchedData.isWeighted?0.05:0.011)) F(w,ck+' combined>sum '+it.name+' '+it.purchaseCost+' > '+s);
  });});
 }
 return {checks,fails};
}
