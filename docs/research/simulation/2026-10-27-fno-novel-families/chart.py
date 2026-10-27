"""Standalone plotting process: isolated dependencies; never imports the replay."""
from pathlib import Path
import json
import sys
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P/'_local/plot-packages'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

r=json.loads((P/'chart-data.json').read_text())
fig,(ax,below)=plt.subplots(2,1,figsize=(12,7),gridspec_kw={'height_ratios':[2.1,1]},sharex=True)
colors=['#596779','#087e8b','#c56833']
for label,values,unresolved,c in zip(r['labels'],r['daily'],r['unresolved'],colors):
    running=0.;curve=[]
    for v in values:running+=v;curve.append(running)
    short=label.split()[0] if label!='Shipped control' else label
    ax.plot(curve,label=f'{short} ({unresolved} unresolved)',linewidth=2.2,color=c)
for i in range(1,len(r['daily'])):
    difference=[a-b for a,b in zip(r['daily'][i],r['daily'][0])]
    below.plot(difference,color=colors[i],alpha=.85,label=r['labels'][i].split()[0],linewidth=1.4)
for a in (ax,below):
    a.axhline(0,color='#7b8794',linewidth=.8);a.grid(axis='y',alpha=.18)
    a.spines[['top','right']].set_visible(False)
split=next(i for i,d in enumerate(r['days']) if d>='2026-10-12')-.5
ax.axvline(split,color='#a67c39',linestyle='--',alpha=.8)
ax.text(split+.3,ax.get_ylim()[1]*.88,'Later diagnostic\nALSO PREVIOUSLY SEEN',fontsize=9,color='#80612e')
ax.set_ylabel('Cumulative modeled priced-close P&L (INR)')
below.set_ylabel('Daily difference\nversus shipped (INR)')
ax.legend(loc='upper left',frameon=False,fontsize=9)
step=4;below.set_xticks(list(range(0,len(r['days']),step)),[d[5:] for d in r['days'][::step]],rotation=30)
fig.suptitle('New F&O entry families: exploratory replay, not validated profit',fontsize=16,x=.07,ha='left')
fig.text(.07,.012,'29 archived sessions · missing Sep 18 · unresolved positions excluded · sampled quotes and recording gaps · no live deployment',fontsize=9,color='#596779')
fig.tight_layout(rect=(.02,.045,.99,.94))
fig.savefig(P/'research-results.png',dpi=160)
fig.savefig(P/'research-results.svg')
