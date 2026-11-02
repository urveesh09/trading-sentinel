"""Exact ablations of N03 HORIZON; no new threshold or forecast."""
def choose(mode,combined_minutes):
    if mode not in ('BASE','STALL_ONLY','CONTINUE_ONLY'):raise ValueError('unknown exit mode')
    if combined_minutes not in (30.,60.,90.):raise ValueError('unknown parent clock')
    if mode=='STALL_ONLY' and combined_minutes==30.:return 30.,'STALL30'
    if mode=='CONTINUE_ONLY' and combined_minutes==90.:return 90.,'CONTINUE90'
    return 60.,'BASE60'
