"""SN413 A follow-up (disclosed, Nov 17, after the first scoring): MIDCPNIFTY had no observations because the official
index file names it "Nifty Midcap Select" (the script had "NIFTY Midcap Select"). The same score for MIDCPNIFTY with the
right name, plus NIFTYNXT50 ("Nifty Next 50") from the auditor's screen; written to results-sn413a-followup.json. The
first results (BANKNIFTY / FINNIFTY / NIFTY) are unchanged.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn413a  # noqa: E402

sn413a.INDEX = {"MIDCPNIFTY": "Nifty Midcap Select", "NIFTYNXT50": "Nifty Next 50"}
sn413a.OUT = HERE / "results-sn413a-followup.json"

if __name__ == "__main__":
    sn413a.score()
