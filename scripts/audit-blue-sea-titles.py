#!/usr/bin/env python3
"""Read-only title/SEO parity audit between Blue Sea legacy and Astro sitemap URLs.
No WordPress writes, no search engine queries, no URL modifications.
"""
import collections
import concurrent.futures
import difflib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

SOURCE = 'https://xuongmunonbaohiem.com'
TARGET = 'https://xuongmunonbaohiem.io.vn'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; BlueSea-SEO-TitleParityAudit/1.0)'}
OUTPUT = Path('reports/blue-sea-title-parity')
OUTPUT.mkdir(parents=True, exist_ok=True)

def get_url(url, max_bytes=800000):
    req = urllib.request.Request(url, headers=UA)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=35) as res:
            content = res.read(max_bytes)
            return dict(ok=True, status=res.status, url=res.url,
                        content=content.decode('utf-8', 'replace'),
                        elapsed=round(time.monotonic() - started, 2))
    except urllib.error.HTTPError as error:
        return dict(ok=False, status=error.code, url=error.url,
                    error=str(error.reason), elapsed=round(time.monotonic() - started, 2))
    except Exception as error:
        return dict(ok=False, status=None, url=url,
                    error=type(error).__name__+': '+str(error)[:90],
                    elapsed=round(time.monotonic()-started, 2))

def key(path):
    return path.rstrip('/') or '/'

def sitemap_paths(site):
    xml = get_url(site+'/sitemap.xml', 4000000)
    if not xml['ok']:
        raise RuntimeError('sitemap not accessible: '+site)
    root = ET.fromstring(xml['content'])
    urls = [e.text.strip() for e in root.iter()
            if e.tag.rsplit('}', 1)[-1] == 'loc' and e.text]
    paths = {key(urllib.parse.urlsplit(u).path): u for u in urls
             if urllib.parse.urlsplit(u).hostname == urllib.parse.urlsplit(site).hostname}
    return paths

class SEOParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_bits=[]
        self.title_on=False
        self.meta={}
        self.h1_count=0
        self.h1_bits=[]
        self.h1_on=False
        self.canonical=''
    def handle_starttag(self, tag, attrs):
        attr=dict(attrs)
        if tag=='title': self.title_on=True
        if tag=='h1': self.h1_count+=1;self.h1_on=True
        if tag=='meta':
            name=(attr.get('name') or attr.get('property') or '').lower()
            if name in ['description', 'robots', 'og:title', 'twitter:title']:
                self.meta[name]=attr.get('content','')
        if tag=='link' and 'canonical' in (attr.get('rel') or '').lower().split():
            self.canonical=attr.get('href','')
    def handle_endtag(self, tag):
        if tag=='title': self.title_on=False
        if tag=='h1': self.h1_on=False
    def handle_data(self, s):
        if self.title_on:self.title_bits.append(s)
        if self.h1_on:self.h1_bits.append(s)

def scrape(url):
    result = get_url(url)
    if not result['ok']:
        return {k:v for k,v in result.items() if k!='content'}
    page = SEOParser()
    try:
        page.feed(result['content'])
    except Exception as error:
        return {'status': result['status'], 'error': type(error).__name__}
    return dict(status=result['status'], url=result['url'],
        title=' '.join(html.unescape(''.join(page.title_bits)).split()),
        h1=' '.join(html.unescape(''.join(page.h1_bits)).split())[:190],
        h1_count=page.h1_count,
        description=page.meta.get('description',''),
        og_title=page.meta.get('og:title',''),
        canonical=page.canonical,
        elapsed=result['elapsed'])

legacy = sitemap_paths(SOURCE)
astro = sitemap_paths(TARGET)
astro_set=set(astro)
def candidates(old):
    stem=old[:-5] if old.endswith('.html') else old
    slug=stem.split('/')[-1]
    options=[
        old, stem,
        '/san-pham/'+slug,
        '/'+slug,
    ]
    if old.startswith('/thong-tin-chinh-sach/'):
        options.insert(0,old.replace('/thong-tin-chinh-sach','',1))
    if old.startswith('/mau-non-khac/'):
        options.insert(0,'/san-pham/'+slug)
    if old.endswith('/non-bao-hiem-vespa-2'):
        options.insert(0,'/san-pham/non-bao-hiem-vespa')
    if old.endswith('/non-bao-hiem-vespa-special-2'):
        options.insert(0,'/san-pham/non-bao-hiem-vespa-special')
    return list(dict.fromkeys(key(x) for x in options))

matched={}
for old in legacy:
    options=candidates(old)
    matching=[p for p in options if p in astro_set]
    if matching:
        # Prefer exact, then mapped original preserving relative location.
        matched[old]=matching[0]

# Fetch all published source URL pages and only the mapped target pages
jobs={}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for path,u in legacy.items():
        jobs[('original',path)]=pool.submit(scrape,u)
    for p in set(matched.values()):
        jobs[('astro',p)]=pool.submit(scrape,astro[p])
    rows=[]
    for old,old_url in legacy.items():
        origin=jobs[('original',old)].result()
        new=matched.get(old)
        current=jobs[('astro',new)].result() if new else None
        source_title=origin.get('title','')
        new_title=current.get('title','') if current else ''
        generic = bool(re.match(r'^(?:sản phẩm|tin tức|trang chủ|bài viết)\s*[-|:]\s*blue sea$', new_title, re.I))
        if not new:
            category='unmapped'
        elif origin.get('status')!=200 or current.get('status')!=200:
            category='fetch-error'
        elif not new_title:
            category='empty'
        elif source_title==new_title:
            category='exact'
        elif generic:
            category='generic'
        elif ''.join(source_title.lower().split()) == ''.join(new_title.lower().split()):
            category='case-or-space-only'
        elif source_title.lower().replace(' - blue sea','').strip() == new_title.lower().replace(' - blue sea','').strip():
            category='minor-brand-difference'
        else:
            category='different'
        rows.append(dict(source_path=old,target_path=new,
                         original=origin,astro=current,category=category,
                         source_length=len(source_title),target_length=len(new_title)))

counts=collections.Counter(r['category'] for r in rows)
title_counts=collections.Counter(r['astro']['title'] for r in rows if r['astro'] and r['astro'].get('title'))
duplicates={title:n for title,n in title_counts.items() if n>1}
critical=[
    r for r in rows if r['category'] in ('generic','empty','different','fetch-error')
]
# Large source/target mismatch caused by 2 different products with same generic title is an actionable issue.
summary={'sitemap_original_unique':len(legacy),'sitemap_astro_unique':len(astro),
         'paired':len(matched),'unmatched':len(legacy)-len(matched),
         'categories':dict(counts),
         'duplicate_target_titles':dict(title_counts.most_common(14)),
         'critical_examples':[
             dict(path=r['source_path'],target=r['target_path'],
                  old=r['original'].get('title',''),
                  new=r['astro'].get('title','') if r['astro'] else None,
                  issue=r['category'])
             for r in critical[:55]],
         'unmapped_sample':[r['source_path'] for r in rows if r['category']=='unmapped'][:40] }
(OUTPUT/'details.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
(OUTPUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
print('TITLE_AUDIT_SUMMARY='+json.dumps({k:v for k,v in summary.items() if k not in ('critical_examples','unmapped_sample')},ensure_ascii=False),flush=True)
for r in critical:
    print('TITLE_DIFF='+json.dumps({'path':r['source_path'],'target':r['target_path'],
       'source_title':r['original'].get('title',''), 'astro_title':r['astro'].get('title','') if r['astro'] else None,
       'issue':r['category']},ensure_ascii=False),flush=True)
for r in rows:
    if r['category']=='unmapped':
        print('TITLE_UNMAPPED='+json.dumps({'path':r['source_path'],'title':r['original'].get('title','')},ensure_ascii=False),flush=True)
if os.getenv('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf8') as out:
        out.write(f"## Blue Sea HTML Title Audit ({len(rows)} source URLs)\n\n")
        out.write(f"Paired **{len(matched)}** pages; unmatched **{len(rows)-len(matched)}**.\n\n")
        for name,count in counts.most_common():
            out.write(f"- {name}: {count}\n")
        out.write('\n| Old path | Astro path | Original title | Astro title | Issue |\n|---|---|---|---|---|\n')
        for r in critical[:75]:
            def safe(s):return (s or '').replace('|','/').replace('\n',' ')[:115]
            out.write('| '+safe(r['source_path'])+' | '+safe(r['target_path'])+' | '+safe(r['original'].get('title'))+' | '+safe(r['astro'].get('title') if r['astro'] else '')+' | '+r['category']+' |\n')
