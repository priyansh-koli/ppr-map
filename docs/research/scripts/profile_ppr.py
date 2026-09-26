"""Phase 0 profiling of PPR-ALL.csv (stdlib only).

Usage: python profile_ppr.py path/to/PPR-ALL.csv
Output is recorded in docs/research/ppr-data-profile.md. Throwaway research code, not part of the pipeline.
"""
import csv, re, collections, sys, statistics
path = sys.argv[1]
raw = open(path,'rb').read()
print("bytes 0x80 count:", raw.count(b'\x80'), " 0xA4:", raw.count(b'\xa4'), " CRLF:", raw.count(b'\r\n'))
try:
    raw.decode('utf-8'); print("valid utf-8: yes")
except UnicodeDecodeError as e: print("valid utf-8: no ->", e)
txt = raw.decode('cp1252')
nonascii = collections.Counter(c for c in txt if ord(c)>127)
print("non-ascii chars:", nonascii.most_common(25))
rows = list(csv.reader(txt.splitlines()))
hdr, rows = rows[0], rows[1:]
print("header:", hdr); print("rows:", len(rows))
print("field-count dist:", collections.Counter(len(r) for r in rows))
D,A,C,E,P,NFMP,VAT,DESC,SIZE = range(9)
from datetime import datetime
dates=[]; bad_dates=0
for r in rows:
    try: dates.append(datetime.strptime(r[D],'%d/%m/%Y'))
    except: bad_dates+=1
print("date range:", min(dates).date(), max(dates).date(), "bad:", bad_dates)
yc = collections.Counter(d.year for d in dates); print("per year:", sorted(yc.items()))
prices=[]; badp=collections.Counter()
for r in rows:
    m = re.fullmatch(r'€([\d,]+\.\d{2})', r[P])
    if m: prices.append(float(m.group(1).replace(',','')))
    else: badp[r[P][:20]]+=1
print("price parse ok:", len(prices), "bad samples:", badp.most_common(5))
ps=sorted(prices); n=len(ps)
print("price min/p1/median/p99/max:", ps[0], ps[n//100], ps[n//2], ps[99*n//100], ps[-1])
print("price < 10k:", sum(p<10000 for p in ps), " > 5M:", sum(p>5_000_000 for p in ps), " > 20M:", sum(p>20_000_000 for p in ps))
print("county:", collections.Counter(r[C] for r in rows).most_common())
print("NFMP:", collections.Counter(r[NFMP] for r in rows)); print("VAT:", collections.Counter(r[VAT] for r in rows))
print("DESC:", collections.Counter(r[DESC] for r in rows).most_common())
print("SIZE:", collections.Counter(r[SIZE] for r in rows).most_common())
ec=[r[E] for r in rows]
print("eircode filled:", sum(bool(x.strip()) for x in ec), "of", len(ec))
recent=[r for r,d in zip(rows,dates) if d.year>=2024]
print("eircode filled 2024+:", sum(bool(r[E].strip()) for r in recent), "of", len(recent))
for y in range(2010,2027):
    yr=[r for r,d in zip(rows,dates) if d.year==y]
    if yr: print(" eircode", y, round(100*sum(bool(r[E].strip()) for r in yr)/len(yr),1), "%")
valid=re.compile(r'^[AC-FHKNPRTV-Y]\d{2}|D6W[0-9AC-FHKNPRTV-Y]{4}$')
print("eircode formats:", collections.Counter(re.sub(r'[A-Z]','A',re.sub(r'\d','9',x)) for x in ec if x.strip()).most_common(8))
# address characteristics
print("upper-case addresses:", sum(r[A].isupper() for r in rows))
print("addr with 'Co.':", sum(bool(re.search(r'\bco\.?\s', r[A], re.I)) for r in rows))
# duplicates
key=lambda r:(r[D],r[A].lower(),r[P])
dupc=collections.Counter(key(r) for r in rows)
print("exact duplicate rows:", sum(v-1 for v in dupc.values() if v>1))
# same date+price groups (bulk sales)
g=collections.Counter((r[D],r[P]) for r in rows)
big=[(k,v) for k,v in g.items() if v>=5]
print("date+price groups >=5 rows:", len(big), "rows in them:", sum(v for k,v in big)); print(sorted(big,key=lambda x:-x[1])[:5])
norm=lambda a: re.sub(r'[^a-z0-9]','',a.lower())
ac=collections.Counter(norm(r[A]) for r in rows)
print("distinct normalised addresses:", len(ac), " with >1 sale:", sum(1 for v in ac.values() if v>1))
print("sample addresses:"); import random; random.seed(1)
for r in random.sample(rows,12): print("  ",r[A],"|",r[C],"|",r[E])


# ---- part 2: cross-tabs and address quality ----
rows=[r for r in csv.reader(open(path,encoding="cp1252",newline=""))][1:]
print("desc x VAT:", collections.Counter(('New' if ('New' in r[7] or 'Nua' in r[7]) else 'SH', 'VATx='+r[6]) for r in rows))
print("NFMP by year:", sorted(collections.Counter(r[0][-4:] for r in rows if r[5]=='Yes').items()))
print("size filled by desc:", collections.Counter(('New' if ('New' in r[7] or 'Nua' in r[7]) else 'SH', bool(r[8])) for r in rows))
print("size filled by year:", sorted(collections.Counter(r[0][-4:] for r in rows if r[8]).items()))
d=[r for r in rows if r[2]=='Dublin']
pd=collections.Counter()
for r in d:
    m=re.search(r'dublin\s*(\d{1,2}w?)\b', r[1], re.I)
    pd['D'+m.group(1).upper() if m else 'none']+=1
print("Dublin postal district in address:", pd.most_common(8), "none share:", round(pd['none']/len(d),3))
print("Dublin eircode filled:", sum(bool(r[3]) for r in d), len(d))
print("apartment-like (apt/apartment/unit/flat):", sum(bool(re.search(r'\b(apt|apartment|unit|flat)\b', r[1], re.I)) for r in rows))
print("address with no digit:", sum(not re.search(r'\d', r[1]) for r in rows))
print("eircode appears in multiple distinct-normalised addresses (shared/wrong):")
em=collections.defaultdict(set)
for r in rows:
    if r[3]: em[r[3]].add(re.sub(r'[^a-z0-9]','',r[1].lower()))
print("  eircodes:", len(em), " with >1 addr variant:", sum(len(v)>1 for v in em.values()))
print("  sample:", [ (k,list(v)[:3]) for k,v in list(em.items()) if len(v)>2][:3])
print("county mismatch sample (address says other county):")
cn=['Dublin','Cork','Kildare','Galway','Meath','Limerick','Wexford','Wicklow','Louth','Waterford','Kerry','Tipperary','Donegal','Mayo','Clare','Westmeath','Laois','Kilkenny','Cavan','Sligo','Roscommon','Offaly','Carlow','Leitrim','Longford','Monaghan']
mm=0
for r in rows:
    m=re.search(r'\bco\.?\s*('+'|'.join(cn)+r')\b', r[1], re.I)
    if m and m.group(1).lower()!=r[2].lower(): mm+=1
print("  'Co. X' in address != County column:", mm)
