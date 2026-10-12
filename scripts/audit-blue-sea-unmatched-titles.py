#!/usr/bin/env python3
"""Read-only follow-through on URLs without exact sitemap pairing in title audit."""
import concurrent.futures,html,json,urllib.request,urllib.parse,urllib.error,xml.etree.ElementTree as ET,collections,time
from html.parser import HTMLParser
def fetch(url):
    start=time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 ESC-Title-UnmatchedAudit/1.0'}),timeout=25) as r:
            return {'status':r.status,'final':r.url,'body':r.read(250000).decode('utf8','replace'),'time':round(time.monotonic()-start,2)}
    except urllib.error.HTTPError as e:
        return {'status':e.code,'final':e.url,'error':str(e.reason)}
    except Exception as e:
        return {'error':type(e).__name__+': '+str(e)[:80]}
class Title(HTMLParser):
    def __init__(self):super().__init__();self.on=False;self.text=[]
    def handle_starttag(self,t,a):
        if t=='title':self.on=True
    def handle_endtag(self,t):
        if t=='title':self.on=False
    def handle_data(self,t):
        if self.on:self.text.append(t)
def title(response):
    if not response.get('body'):return ''
    parser=Title()
    parser.feed(response['body'])
    return html.unescape(' '.join(''.join(parser.text).split()))
def listing(root):
    data=ET.fromstring(fetch(root+'/sitemap.xml')['body'])
    return {urllib.parse.urlsplit(item.text).path.rstrip('/') or '/' for item in data.iter() if item.tag.rsplit('}',1)[-1]=='loc' and item.text}
old=listing('https://xuongmunonbaohiem.com')
new=listing('https://xuongmunonbaohiem.io.vn')
def candidates(oldpath):
    stem=oldpath[:-5] if oldpath.endswith('.html') else oldpath
    slug=stem.split('/')[-1]
    options=[oldpath,stem,'/san-pham/'+slug,'/'+slug]
    if oldpath.startswith('/thong-tin-chinh-sach/'):
        options.insert(0,oldpath.replace('/thong-tin-chinh-sach','',1))
    if oldpath.startswith('/mau-non-khac/'):
        options.insert(0,'/san-pham/'+slug)
    if oldpath.endswith('/non-bao-hiem-vespa-2'):options.insert(0,'/san-pham/non-bao-hiem-vespa')
    if oldpath.endswith('/non-bao-hiem-vespa-special-2'):options.insert(0,'/san-pham/non-bao-hiem-vespa-special')
    return {s.rstrip('/') or '/' for s in options}
missing=sorted(path for path in old if not (candidates(path)&new))
def check(path):
    original=fetch('https://xuongmunonbaohiem.com'+path)
    astro=fetch('https://xuongmunonbaohiem.io.vn'+path)
    loc=urllib.parse.urlsplit(astro.get('final',''))
    targetpath=loc.path.rstrip('/') or '/'
    source_title=title(original)
    new_title=title(astro)
    return {'originalPath':path,'originalTitle':source_title,'astroHTTP':astro.get('status'),
            'astroFinalPath':targetpath,'astroTitle':new_title,
            'inAstroSitemap':targetpath in new,
            'redirected':targetpath != path,
            'equivalenceUnverified':source_title.lower().strip()!=new_title.lower().strip(),
            'error':astro.get('error')}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    results=list(pool.map(check,missing))
for row in results:print('UNMAPPED_TITLE_DETAIL='+json.dumps(row,ensure_ascii=False),flush=True)
categories=collections.Counter(str(x.get('astroHTTP')) for x in results)
print('UNMAPPED_TITLE_SUMMARY='+json.dumps({
    'checked':len(results),'statuses':dict(categories),
    'reachable':sum(x['astroHTTP']==200 for x in results),
    'redirectedAndReached200':sum(x['astroHTTP']==200 and x['redirected'] for x in results),
    'remaining404':[x['originalPath'] for x in results if x['astroHTTP']==404]
},ensure_ascii=False),flush=True)
