"""Two fixed early-review refinements; native exits always remain available."""
import math
def choose(mode,eligible,age,structure=None,level=None,direction='LONG'):
    if mode not in ('BASE','STALL30','DELAY45','STRUCT30'):raise ValueError('unknown review mode')
    if mode=='BASE' or not eligible or not math.isfinite(age) or not 30<=age<60:return 60.,'BASE60'
    if mode=='STALL30':return 30.,'STALL30'
    if mode=='DELAY45':return (45.,'DELAY45') if age>=45 else (60.,'BASE60')
    if not structure or not structure.get('fresh') or level is None or not math.isfinite(level):return 60.,'BASE60'
    close=structure.get('close')
    if close is None or not math.isfinite(close) or direction not in ('LONG','SHORT'):return 60.,'BASE60'
    lost=close<level if direction=='LONG' else close>level
    return (30.,'STRUCT30') if lost else (60.,'BASE60')
