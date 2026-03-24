import math
import structlog
from typing import List, Dict
from models import Signal
from config import settings

logger = structlog.get_logger()

def filter_and_allocate(signals: List[Dict], open_positions: List[Dict], bankroll: float) -> tuple[List[Signal], List[Dict]]:
    accepted = []
    rejected = []
    
    # Sort: EV > 0, then Score DESC, Vol DESC
    valid_signals = sorted([s for s in signals if s['net_ev'] > 0], 
                           key=lambda x: (x['score'], x['volume_ratio']), reverse=True)
                           
    open_count = len(open_positions)
    remaining_slots = settings.MAX_OPEN_POSITIONS - open_count # [P1]
    
    sector_exposure = {}
    total_risk = 0.0
    for p in open_positions:
        sec = p.get('sector', 'UNKNOWN')
        sector_exposure[sec] = sector_exposure.get(sec, 0) + (p['shares'] * p['entry_price'])
        total_risk += (p['entry_price'] - p['stop_loss_initial']) * p['shares']
        
    for raw_sig in valid_signals:
        if remaining_slots <= 0:
            raw_sig['reject_reason'] = "MAX_POSITIONS_REACHED"
            rejected.append(raw_sig)
            continue
            
        ticker = raw_sig['ticker']
        if any(p['ticker'] == ticker for p in open_positions): # [C8]
            raw_sig['reject_reason'] = "ALREADY_OPEN"
            rejected.append(raw_sig)
            continue
            
        sec = raw_sig.get('sector', 'UNKNOWN')
        current_sec_exposure = sector_exposure.get(sec, 0.0)
        
        # [P4] Correlation proxy
        if sum(1 for p in open_positions if p.get('sector') == sec) >= settings.MAX_CORRELATED_POSITIONS:
            raw_sig['reject_reason'] = "MAX_CORRELATED_SECTOR"
            rejected.append(raw_sig)
            continue

        c = raw_sig['close']
        shares = raw_sig['shares']
        cap_deployed = shares * c
        
        # [P2] Max Capital per Trade
        if cap_deployed > bankroll * settings.MAX_CAPITAL_PER_TRADE_PCT:
            shares = math.floor((bankroll * settings.MAX_CAPITAL_PER_TRADE_PCT) / c)
            if shares == 0:
                raw_sig['reject_reason'] = "P2_SHARES_REDUCED_TO_ZERO"
                rejected.append(raw_sig)
                continue
            raw_sig['shares'] = shares
            raw_sig['capital_deployed'] = shares * c
            raw_sig['capital_at_risk'] = shares * (c - raw_sig['stop_loss'])
            
        # [P3] Max Sector Exposure
        if current_sec_exposure + raw_sig['capital_deployed'] > bankroll * settings.MAX_SECTOR_EXPOSURE_PCT:
            raw_sig['reject_reason'] = "MAX_SECTOR_EXPOSURE"
            rejected.append(raw_sig)
            continue
            
        # [P5] Max Total Capital at Risk
        if total_risk + raw_sig['capital_at_risk'] > bankroll * settings.MAX_TOTAL_RISK_PCT:
            raw_sig['reject_reason'] = "MAX_TOTAL_RISK_BREACHED"
            rejected.append(raw_sig)
            continue

        # Inviolable Rule Check: Must never exceed risk limit
        risk_per_trade = bankroll * settings.RISK_PCT
        assert round(raw_sig['capital_at_risk'], 2) <= round(risk_per_trade + 0.05, 2), "CRITICAL: Capital at risk exceeds risk limit."

        sector_exposure[sec] = sector_exposure.get(sec, 0) + raw_sig['capital_deployed']
        total_risk += raw_sig['capital_at_risk']
        remaining_slots -= 1
        
        raw_sig['portfolio_slot'] = settings.MAX_OPEN_POSITIONS - remaining_slots
        accepted.append(Signal(**raw_sig))
        
    return accepted, rejected
