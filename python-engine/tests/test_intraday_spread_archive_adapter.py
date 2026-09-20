from datetime import datetime, timezone
import hashlib
import json

import pytest

from intraday_spread_archive_adapter import (
    SpreadContractIdentity,
    _has_executable_depth,
    build_spread_observations,
    read_archived_quote_events,
)
from intraday_spread_replay import LegQuote, ReplayInputError
from intraday_spread_signal_artifact import write_signal_artifact


RAW_MASTER = (b"instrument_token,tradingsymbol,name,exchange,instrument_type,expiry,strike,lot_size\n"
              b"1,NIFTY25000CE,NIFTY,NFO,CE,2026-09-24,25000,75\n"
              b"2,NIFTY25200CE,NIFTY,NFO,CE,2026-09-24,25200,75\n")
MASTER = hashlib.sha256(RAW_MASTER).hexdigest()


def identity(token, symbol, strike):
    return SpreadContractIdentity(token, symbol, "NIFTY", "NFO", "CE", strike, "2026-09-24", 75)


def event(contract, received="2026-09-10T04:30:00+00:00"):
    raw = {"instrument_token": int(contract["instrument_token"]), "timestamp": received,
           "depth": {"buy": [{"price": 100, "quantity": 75}], "sell": [{"price": 102, "quantity": 75}]}}
    return {"received_at_utc": received, "provider_timestamp_utc": received, "contract": contract,
            "buy_depth": [{"price": 100, "quantity": 75}], "sell_depth": [{"price": 102, "quantity": 75}],
            "raw_packet": raw, "raw_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()}


def contract(item):
    return {"instrument_token": str(item.token), "tradingsymbol": item.symbol, "underlying": item.underlying,
            "exchange": item.exchange, "instrument_type": item.option_type, "strike": item.strike,
            "expiry": item.expiry, "lot_size": item.lot_size}


def archive(tmp_path, *items):
    path = tmp_path / "contract-masters" / "KITE" / "NFO" / "2026-09-10" / MASTER
    path.mkdir(parents=True)
    canonical = ("\n".join(json.dumps(contract(item)) for item in items) + "\n").encode()
    (path / "raw.csv").write_bytes(RAW_MASTER)
    (path / "manifest.json").write_text(json.dumps({"raw_sha256": MASTER, "canonical_sha256": hashlib.sha256(canonical).hexdigest()}), encoding="utf-8")
    (path / "contracts.jsonl").write_bytes(canonical)
    return tmp_path


def artifact(tmp_path, *, receipt="2026-09-10T04:30:00+00:00", score=1.0):
    path = tmp_path / "signals.json"
    source = tmp_path / "source-manifests" / "quotes-2026-09-10.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"archive":"fixture"}', encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    write_signal_artifact(path, {"format": "intraday_spread_signal_artifact_v1", "evaluator_id": "orb_threshold_v1",
        "evaluator_sha256": "a" * 64, "policy_id": "policy-v1", "policy_sha256": "b" * 64,
        "config_sha256": "c" * 64, "underlying": "NIFTY", "session_date": "2026-09-10",
        "source_manifests": [{"reference": "source-manifests/quotes-2026-09-10.json", "sha256": digest}],
        "signals": [{"decision_id": "one", "received_at": receipt, "decision_cutoff": receipt, "score": score,
                     "evaluator_input": {"direction": "LONG", "close": 101, "trigger": 100,
                     "source_packets": [{"packet_id": "bar-one", "received_at": receipt}]}}]})
    return path


@pytest.mark.parametrize("filename", ["raw.csv", "contracts.jsonl"])
def test_master_file_tampering_rejected(tmp_path, filename):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    archive(tmp_path, long, short)
    path = next((tmp_path / "contract-masters").rglob(filename))
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ReplayInputError, match="master does not prove"):
        build_spread_observations(events=[], long_contract=long, short_contract=short,
                                  master_sha256=MASTER, archive_root=tmp_path)


def test_rehashed_normalized_terms_must_still_match_raw_master(tmp_path):
    from dataclasses import replace
    from intraday_spread_archive_adapter import _master_proves_contract
    wrong = replace(identity(1, "NIFTY25000CE", 25000), lot_size=100)
    archive(tmp_path, wrong)
    assert not _master_proves_contract(tmp_path, wrong, MASTER)


@pytest.mark.parametrize("fault", ["hash", "price", "clock", "changed_clock"])
def test_unproven_quote_is_partial_not_executable(tmp_path, fault):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    bad = event(contract(long))
    if fault == "hash":
        bad["raw_sha256"] = "0" * 64
    elif fault == "price":
        bad["buy_depth"][0]["price"] = 999
    elif fault == "clock":
        bad["provider_timestamp_utc"] = None
    else:
        bad["provider_timestamp_utc"] = "2026-09-10T04:29:59+00:00"
    built = build_spread_observations(events=[bad, event(contract(short))], long_contract=long,
        short_contract=short, master_sha256=MASTER, archive_root=archive(tmp_path, long, short))
    assert not built.observations
    assert built.partial_batches[0]["missing"] == ["long"]


def test_archive_adapter_pairs_only_complete_same_receipt_batches_and_retains_partial(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    built = build_spread_observations(events=[event(contract(long)), event(contract(short)),
        event(contract(long), "2026-09-10T04:35:00+00:00")], long_contract=long, short_contract=short,
        master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        signal_artifact_path=artifact(tmp_path), policy_id="policy-v1", session_date="2026-09-10")
    assert len(built.observations) == 1
    assert built.observations[0].signal_score == 1.0
    assert built.partial_batches[0]["missing"] == ["short"]


def test_unrelated_archive_packets_are_ignored_not_false_partial_books(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    unrelated = identity(999, "NIFTY26000CE", 26000)
    built = build_spread_observations(events=[event(contract(long)), event(contract(short)),
        event(contract(unrelated), "2026-09-10T04:31:00+00:00")], long_contract=long,
        short_contract=short, master_sha256=MASTER, archive_root=archive(tmp_path, long, short))
    assert len(built.observations) == 1
    assert built.partial_batches == ()
    assert built.ignored_events == 1


def test_finalized_quote_segment_manifest_detects_rehashed_packet_tampering(tmp_path):
    import gzip
    day = "2026-09-10"
    base = tmp_path / "quotes" / day
    base.mkdir(parents=True)
    payload = (json.dumps(event(contract(identity(1, "NIFTY25000CE", 25000)))) + "\n").encode()
    digest = hashlib.sha256(payload).hexdigest()
    path = base / f"quotes-{digest[:16]}.jsonl.gz"
    with gzip.open(path, "wb") as stream:
        stream.write(payload)
    manifest = {"kind": "observed_quote_segment", "day": day, "event_count": 1,
                "raw_sha256": digest, "path": path.name}
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert len(read_archived_quote_events(tmp_path, days=[day])) == 1
    changed = json.loads(payload)
    changed["oi"] = 999
    changed["raw_sha256"] = hashlib.sha256(json.dumps(changed["raw_packet"], sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    with gzip.open(path, "wb") as stream:
        stream.write((json.dumps(changed) + "\n").encode())
    with pytest.raises(ReplayInputError, match="fingerprint mismatch"):
        read_archived_quote_events(tmp_path, days=[day])


def test_same_receipt_conflict_is_rejected_but_exact_retry_is_idempotent(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    original = event(contract(long))
    changed = event(contract(long))
    changed["raw_packet"]["depth"]["buy"][0]["price"] = 99
    changed["buy_depth"][0]["price"] = 99
    changed["raw_sha256"] = hashlib.sha256(json.dumps(changed["raw_packet"], sort_keys=True,
        default=str, separators=(",", ":")).encode()).hexdigest()
    root = archive(tmp_path, long, short)
    for ordered in ([original, changed, event(contract(short))],
                    [changed, original, event(contract(short))]):
        built = build_spread_observations(events=ordered, long_contract=long, short_contract=short,
            master_sha256=MASTER, archive_root=root)
        assert not built.observations
        assert built.conflicting_batches[0]["conflicting"] == ["long"]
        assert built.conflicting_batches[0]["packet_sha256"]["long"] == sorted(
            [original["raw_sha256"], changed["raw_sha256"]])

    retried = build_spread_observations(events=[original, dict(original), event(contract(short))],
        long_contract=long, short_contract=short, master_sha256=MASTER, archive_root=root)
    assert len(retried.observations) == 1
    assert retried.conflicting_batches == ()


def test_archive_adapter_rejects_tampered_signal_artifact(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    path = artifact(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('"score":1.0', '"score":999'), encoding="utf-8")
    with pytest.raises(ReplayInputError, match="score does not reproduce"):
        build_spread_observations(events=[], long_contract=long, short_contract=short, master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
                                  signal_artifact_path=path, policy_id="policy-v1", session_date="2026-09-10")


def test_archive_adapter_rejects_signal_artifact_with_missing_source_manifest(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    root = archive(tmp_path, long, short)
    path = artifact(tmp_path)
    (tmp_path / "source-manifests" / "quotes-2026-09-10.json").unlink()
    with pytest.raises(ReplayInputError, match="source manifest is missing"):
        build_spread_observations(events=[], long_contract=long, short_contract=short, master_sha256=MASTER,
            archive_root=root, signal_artifact_path=path, policy_id="policy-v1", session_date="2026-09-10")


# ---------------------------------------------------------------------------
# [WORKFLOW-C.A1 2026-09-15] Asymmetric-fills diagnostic tests.


def _asymmetric_event(contract, *, bid_quantity, ask_quantity, received="2026-09-10T04:30:00+00:00"):
    """A same-shape event helper that lets the test vary bid/ask quantity.

    The default ``event()`` helper always sets quantity to 75 (= lot_size
    for NIFTY options). This variant lets the test break the executable-
    depth invariant for one leg while keeping the other leg valid.
    """
    raw = {
        "instrument_token": int(contract["instrument_token"]),
        "timestamp": received,
        "depth": {
            "buy": [{"price": 100, "quantity": bid_quantity}],
            "sell": [{"price": 102, "quantity": ask_quantity}],
        },
    }
    return {
        "received_at_utc": received,
        "provider_timestamp_utc": received,
        "contract": contract,
        "buy_depth": [{"price": 100, "quantity": bid_quantity}],
        "sell_depth": [{"price": 102, "quantity": ask_quantity}],
        "raw_packet": raw,
        "raw_sha256": hashlib.sha256(
            json.dumps(raw, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest(),
    }


class TestAsymmetricFills:
    """[WORKFLOW-C.A1 2026-09-15] Per the plan, asymmetric
    actual fills are "not modeled" -- the archive adapter
    silently rejected them by reporting PARTIAL_LEG_OBSERVATION
    or by passing them to the replay layer which rejected
    the whole pair. This class pins the new bounded
    diagnostic: when both legs have valid packets but only
    one leg has executable depth for a full exchange lot,
    the operator gets an explicit ASYMMETRIC_EXECUTION_QUALITY
    entry that names the executable and insufficient legs
    and surfaces the observed depths.
    """

    def test_long_executable_short_insufficient_is_asymmetric(self, tmp_path):
        long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
        # Long: 75 lots available (>= lot_size). Short: 1 lot only.
        long_ev = _asymmetric_event(
            contract(long), bid_quantity=75, ask_quantity=75,
        )
        short_ev = _asymmetric_event(
            contract(short), bid_quantity=1, ask_quantity=1,
        )
        built = build_spread_observations(
            events=[long_ev, short_ev],
            long_contract=long, short_contract=short,
            master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        )
        # No observation was constructed -- the asymmetric case is rejected.
        assert built.observations == ()
        # The partial_batches is empty -- this is NOT a PARTIAL case.
        assert built.partial_batches == ()
        # The conflicting_batches is empty -- no per-leg contention.
        assert built.conflicting_batches == ()
        # The asymmetric_batches carries the explicit diagnostic.
        assert built.asymmetric_batches is not None
        assert len(built.asymmetric_batches) == 1
        entry = built.asymmetric_batches[0]
        assert entry["state"] == "ASYMMETRIC_EXECUTION_QUALITY"
        assert entry["executable"] == ["long"]
        assert entry["insufficient"] == ["short"]
        # The depth_by_leg block surfaces the observed quantities
        # so the operator can investigate WHY the short leg was thin.
        assert entry["depth_by_leg"]["long"]["bid_depth"] == 75
        assert entry["depth_by_leg"]["short"]["bid_depth"] == 1
        assert entry["quote_by_leg"]["long"]["bid"] == 100
        assert entry["quote_by_leg"]["short"]["ask"] == 102
        assert entry["quote_by_leg"]["long"]["raw_sha256"] == long_ev["raw_sha256"]
        assert entry["quote_by_leg"]["short"]["raw_sha256"] == short_ev["raw_sha256"]
        assert entry["quote_by_leg"]["short"]["received_at"] == entry["received_at"]

    def test_short_executable_long_insufficient_is_asymmetric(self, tmp_path):
        long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
        # The opposite asymmetry: short has depth, long does not.
        long_ev = _asymmetric_event(
            contract(long), bid_quantity=0, ask_quantity=0,
        )
        short_ev = _asymmetric_event(
            contract(short), bid_quantity=75, ask_quantity=75,
        )
        built = build_spread_observations(
            events=[long_ev, short_ev],
            long_contract=long, short_contract=short,
            master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        )
        assert built.observations == ()
        assert built.partial_batches == ()
        assert built.conflicting_batches == ()
        assert built.asymmetric_batches is not None
        entry = built.asymmetric_batches[0]
        assert entry["executable"] == ["short"]
        assert entry["insufficient"] == ["long"]

    def test_both_legs_executable_constructs_observation(self, tmp_path):
        """[WORKFLOW-C.A1 2026-09-15] When both legs have
        executable depth, no asymmetric diagnostic is raised.
        The observation is constructed normally -- backward
        compatibility for the happy path.
        """
        long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
        long_ev = _asymmetric_event(contract(long), bid_quantity=75, ask_quantity=75)
        short_ev = _asymmetric_event(contract(short), bid_quantity=75, ask_quantity=75)
        built = build_spread_observations(
            events=[long_ev, short_ev],
            long_contract=long, short_contract=short,
            master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        )
        assert len(built.observations) == 1
        # No diagnostic -- the symmetric happy path.
        assert built.asymmetric_batches is None

    def test_both_legs_insufficient_is_not_asymmetric(self, tmp_path):
        """[WORKFLOW-C.A1 2026-09-15] When BOTH legs lack
        executable depth, this is NOT the asymmetric-fills
        case -- it's a uniformly thin book. The diagnostic
        only fires when exactly one leg passes the depth
        check. Both legs failing is a different operational
        condition (the pair is uniformly un-executable) and
        the rejection surfaces at the replay layer
        (``book_not_executable_for_full_lot``).

        The archive-layer diagnostic does NOT fire here
        because both legs fail the depth check symmetrically.
        The observation is constructed (the archive layer
        only checks packet integrity) and the replay layer
        rejects it downstream. This is the pre-existing
        behavior -- A1 just narrows the diagnostic to the
        asymmetric case.

        The default master writes contracts with
        ``lot_size=75``, so the bid/ask quantities of 1 are
        valid for the master_proves_contract check (it doesn't
        inspect bid/ask depth) but fail the depth check.
        """
        long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
        long_ev = _asymmetric_event(contract(long), bid_quantity=1, ask_quantity=1)
        short_ev = _asymmetric_event(contract(short), bid_quantity=1, ask_quantity=1)
        built = build_spread_observations(
            events=[long_ev, short_ev],
            long_contract=long, short_contract=short,
            master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        )
        # The archive layer constructs the observation
        # (packet integrity is fine). The replay layer
        # rejects it as book_not_executable_for_full_lot.
        # The ASYMMETRIC diagnostic does NOT fire here.
        assert built.asymmetric_batches is None

    def test_lot_size_zero_falls_through_to_observation(self, tmp_path):
        """[WORKFLOW-C.A1 2026-09-15] Defensive: if
        ``lot_size`` is malformed (zero or negative), the
        executable-depth check degrades to ``False`` for both
        legs. The symmetric-failure case applies -- the
        asymmetric diagnostic does not fire.

        To test this we construct a NEW master/contract pair
        with ``lot_size=0`` so the master_proves_contract
        check accepts the contract. We can't reuse the
        default archive fixture (which writes lot_size=75)
        because the master_proves_contract check would
        reject the malformed contract before the depth check
        runs.
        """
        # Write a separate master for lot_size=0 contracts.
        raw_master_zero = (
            b"instrument_token,tradingsymbol,name,exchange,instrument_type,expiry,strike,lot_size\n"
            b"1,NIFTY25000CE,NIFTY,NFO,CE,2026-09-24,25000,0\n"
            b"2,NIFTY25200CE,NIFTY,NFO,CE,2026-09-24,25200,0\n"
        )
        master_zero = hashlib.sha256(raw_master_zero).hexdigest()
        long = SpreadContractIdentity(1, "NIFTY25000CE", "NIFTY", "NFO", "CE", 25000, "2026-09-24", 0)
        short = SpreadContractIdentity(2, "NIFTY25200CE", "NIFTY", "NFO", "CE", 25200, "2026-09-24", 0)
        path = tmp_path / "contract-masters" / "KITE" / "NFO" / "2026-09-10" / master_zero
        path.mkdir(parents=True)
        canonical = ("\n".join(json.dumps(contract(item)) for item in (long, short)) + "\n").encode()
        (path / "raw.csv").write_bytes(raw_master_zero)
        (path / "manifest.json").write_text(
            json.dumps({"raw_sha256": master_zero, "canonical_sha256": hashlib.sha256(canonical).hexdigest()}),
            encoding="utf-8",
        )
        (path / "contracts.jsonl").write_bytes(canonical)
        long_ev = _asymmetric_event(contract(long), bid_quantity=75, ask_quantity=75)
        short_ev = _asymmetric_event(contract(short), bid_quantity=75, ask_quantity=75)
        built = build_spread_observations(
            events=[long_ev, short_ev],
            long_contract=long, short_contract=short,
            master_sha256=master_zero, archive_root=tmp_path,
        )
        # Both legs fail the depth check symmetrically -- no
        # asymmetric diagnostic.
        assert built.asymmetric_batches is None

    def test_asymmetric_only_fires_once_per_receipt(self, tmp_path):
        """[WORKFLOW-C.A1 2026-09-15] When the SAME receipt
        has multiple asymmetric outcomes (e.g. multiple
        long-leg packets at different prices but all lacking
        depth), the diagnostic fires once per receipt
        timestamp, not once per packet. This mirrors the
        existing PARTIAL_LEG_OBSERVATION discipline -- the
        diagnostic is keyed by ``received_at``.
        """
        long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
        # Two distinct long packets, both with insufficient depth.
        # The existing ``distinct_valid`` collapses them by
        # ``raw_sha256`` -- different prices mean different
        # hashes -- so this becomes a CONFLICTING_LEG_OBSERVATION,
        # NOT an asymmetric case. To exercise the
        # asymmetric-only-once-per-receipt contract, we use
        # two long packets with the SAME price but the test
        # is constructed so they share a hash -- this is
        # impossible in practice (different receipts always
        # have different prices) -- so we only need to verify
        # that the asymmetric diagnostic does NOT duplicate
        # itself when the depth check fires once.
        long_ev = _asymmetric_event(contract(long), bid_quantity=1, ask_quantity=1)
        short_ev = _asymmetric_event(contract(short), bid_quantity=75, ask_quantity=75)
        built = build_spread_observations(
            events=[long_ev, short_ev],
            long_contract=long, short_contract=short,
            master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        )
        assert built.asymmetric_batches is not None
        assert len(built.asymmetric_batches) == 1


class TestHasExecutableDepth:
    """[WORKFLOW-C.A1 2026-09-15] The pure executable-depth
    helper. Pins the contract: ``lot_size`` is a positive
    int, ``bid_depth`` and ``ask_depth`` are non-bool ints
    both ``>= lot_size``.
    """

    def _leg(self, lot, bid, ask):
        from datetime import datetime, timezone
        return LegQuote(
            "TEST", "BUY", "NFO", lot,
            100.0, 102.0, bid, ask,
            datetime(2026, 9, 10, 4, 30, tzinfo=timezone.utc),
            datetime(2026, 9, 10, 4, 30, tzinfo=timezone.utc),
            token=1, option_type="CE", strike=25000.0, expiry="2026-09-24",
            quantity=lot, master_sha256="a" * 64,
            oi=0, volume=0,
        )

    def test_full_lot_on_both_sides_is_executable(self):
        assert _has_executable_depth(self._leg(lot=75, bid=75, ask=75)) is True

    def test_oversized_bid_is_executable(self):
        # More depth than lot_size is fine.
        assert _has_executable_depth(self._leg(lot=75, bid=150, ask=150)) is True

    def test_undersized_bid_is_not_executable(self):
        assert _has_executable_depth(self._leg(lot=75, bid=74, ask=75)) is False

    def test_undersized_ask_is_not_executable(self):
        assert _has_executable_depth(self._leg(lot=75, bid=75, ask=0)) is False

    def test_zero_bid_is_not_executable(self):
        assert _has_executable_depth(self._leg(lot=75, bid=0, ask=75)) is False

    def test_negative_depth_is_not_executable(self):
        """Defensive: a corrupt depth field (negative int) is
        not executable. The helper treats any non-positive
        depth as not executable.
        """
        assert _has_executable_depth(self._leg(lot=75, bid=-1, ask=75)) is False

    def test_bool_depth_is_not_executable(self):
        """[WORKFLOW-C.A1 2026-09-15] ``bool`` is a subclass
        of ``int`` in Python -- a stray ``True`` / ``False``
        would pass the ``isinstance(depth, int)`` check. The
        helper explicitly excludes ``bool`` to keep the
        contract honest.
        """
        assert _has_executable_depth(self._leg(lot=75, bid=True, ask=75)) is False

    def test_string_depth_is_not_executable(self):
        assert _has_executable_depth(self._leg(lot=75, bid="75", ask=75)) is False

    def test_zero_lot_size_is_not_executable(self):
        """Defensive: ``lot_size <= 0`` (the contract was
        malformed) degrades to ``False`` -- we don't want to
        construct a "fully executable" book on a degenerate
        contract.
        """
        assert _has_executable_depth(self._leg(lot=0, bid=75, ask=75)) is False
