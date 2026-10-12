import test from "node:test";
import assert from "node:assert/strict";
import { applyVerifiedH1ToCaches } from "./refresh-product-h1-cache.mjs";

function fixture() {
  const list=Array.from({length:160},(_,i)=>({
    id:54000+i, slug:"helm-"+i, title:"Helm "+i,
    seo_h1:"Helm "+i+" - Original Blue Sea H1"
  }));
  return {
    manifest:{counts:{import_seo_h1:160},products:list},
    wp:list.map(({id,slug,seo_h1})=>({id,slug,seo_h1})),
    raw:list.map(({id,slug})=>({id,slug,seo_h1:"",price:300000,acf:{}})),
    processed:{version:1,routeSignature:"unchanged",products:list.map(({id,slug})=>({
      _id:String(id),slug:{vi:slug},itemSeoH1:{vi:""},itemName:{vi:"Helm"},itemPrice:{vi:300000},
      itemImage:{vi:{src:"/image.webp"}}
    }))}
  };
}

test("refreshes all verified H1 strings without modifying product names, images, prices, routes",()=>{
  const x=fixture();
  const oldImage=JSON.stringify(x.processed.products[0].itemImage);
  const oldPrice=x.raw[0].price;
  const r=applyVerifiedH1ToCaches(x.manifest,x.wp,x.raw,x.processed);
  assert.deepEqual(r,{validated:160,changed:160});
  assert.equal(x.raw[0].seo_h1,x.manifest.products[0].seo_h1);
  assert.equal(x.processed.products[0].itemSeoH1.vi,x.manifest.products[0].seo_h1);
  assert.equal(JSON.stringify(x.processed.products[0].itemImage),oldImage);
  assert.equal(x.raw[0].price,oldPrice);
  assert.equal(x.processed.routeSignature,"unchanged");
  assert.deepEqual(applyVerifiedH1ToCaches(x.manifest,x.wp,x.raw,x.processed),{validated:160,changed:0});
});

test("an unexpected WordPress value fails before modifying any cache",()=>{
  const x=fixture();x.wp[159].seo_h1="old bad value";
  assert.throws(()=>applyVerifiedH1ToCaches(x.manifest,x.wp,x.raw,x.processed),/differs/);
  assert.equal(x.raw[0].seo_h1,"");
  assert.equal(x.processed.products[0].itemSeoH1.vi,"");
});

test("a stale slug or missing cache product prevents writes",()=>{
  const x=fixture();x.processed.products[159].slug.vi="wrong";
  assert.throws(()=>applyVerifiedH1ToCaches(x.manifest,x.wp,x.raw,x.processed),/slug differs/);
  assert.equal(x.raw[0].seo_h1,"");
});

test("rejects processed-cache version mismatch instead of corrupting product JSON",()=>{
  const x=fixture();x.processed.version=5;
  assert.throws(()=>applyVerifiedH1ToCaches(x.manifest,x.wp,x.raw,x.processed),/Valid raw and processed/);
});
