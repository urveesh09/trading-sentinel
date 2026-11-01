"""Mechanical snapshot repair only: 24 fresh candidate annuals, exact economic parity required."""
import json
from pathlib import Path
import n091_lab as L

HERE = Path(__file__).resolve().parent
L.Y.EVALS = L.LOCAL / "repair-evals" / L.YEAR  # Windows children must receive the fresh namespace too.


def main():
    L.verify()
    original_evals = L.LOCAL / "evals"
    assert not L.Y.EVALS.exists() or not list(L.Y.EVALS.glob("*.json")), "preserve prior repair attempts"
    books = {"primary|" + n: b for n, b in L.books("primary").items()}
    books.update({"costs|" + n: b for n, b in L.books("costs").items() if n.split("|")[0] != "N08"})
    L.Z.N.run_books(books, 3)
    result = {}
    for name, book in books.items():
        key = L.Y.task_key(book, "year", L.C.WINDOW)
        before = json.loads((original_evals / f"{key}.json").read_text())
        after = json.loads((L.Y.EVALS / f"{key}.json").read_text())
        assert before["trades"] == after["trades"], (name, "repair changed trade economics")
        original_receipt = json.loads((L.LOCAL / "original-receipts" / f"{key}.json").read_text())
        repaired_receipt = json.loads((L.LOCAL / "receipts" / f"{key}.json").read_text())
        assert original_receipt == repaired_receipt, (name, "repair changed admission cash/floor decisions")
        assert (L.LOCAL / "states" / f"{key}.json").is_file()
        result[name] = {"key": key, "trades": len(after["trades"]), "exact_economic_parity": True}
    L.write(HERE / f"state-repair-parity-{L.YEAR}.json", result)
    print("STATE_REPAIR_EXACT", L.YEAR, len(result), flush=True)


if __name__ == "__main__":
    main()
