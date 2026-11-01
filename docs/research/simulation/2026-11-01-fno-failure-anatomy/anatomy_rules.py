"""Two fixed break-even mechanics hypotheses, not a fitted parameter grid."""
import math


def choose(mode, eligible, age, bid, entry_premium, structure=None, level=None, direction='LONG'):
    if mode not in ('PREMIUM_STALL','STRUCT_OR_PREMIUM'):
        raise ValueError('unknown review mode')
    numeric=lambda v:isinstance(v,(int,float)) and math.isfinite(v)
    if not eligible or not numeric(age) or not 30<=age<60:
        return 60.,'NATIVE60'
    if not numeric(bid) or bid<=0 or not numeric(entry_premium) or entry_premium<=0:
        return 60.,'UNAVAILABLE_NATIVE60'
    if direction not in ('LONG','SHORT'):return 60.,'UNAVAILABLE_NATIVE60'
    price_not_gaining=bid<=entry_premium
    lost=False
    if mode=='STRUCT_OR_PREMIUM' and structure and structure.get('fresh') and numeric(level) and numeric(structure.get('close')):
        lost=structure['close']<level if direction=='LONG' else structure['close']>level
    if price_not_gaining or lost:
        return 30.,'PREMIUM_STALL' if price_not_gaining else 'STRUCTURE_STALL'
    return 60.,'PRESERVE_GAINING_PREMIUM'
