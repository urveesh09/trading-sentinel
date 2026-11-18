"""Round-10 data loading: sealed round-8 books, round-8/9 causal preparation, then round-10 causal inputs."""
import round10  # noqa: F401
import data8, signals8
import families9 as F9
import families10 as FM


def load(verbose=True):
    B, bindings = data8.historical_books()
    for u, book in B.items():
        signals8.prepare(book); F9.prepare9(book)
    receipts = FM.prepare10(B, verbose)
    return B, bindings, receipts
