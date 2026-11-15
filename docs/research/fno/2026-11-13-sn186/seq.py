"""Sequence data and the LSTM for SN191-SN194 (PLAN.md). Per minute of a session, six causal features: the index's
1-minute log return (x 1e4), its bar range / ATR, its distance to VWAP / ATR, the ATM call and put marks / index
(x 1e4, last print within 5 minutes, else carried) and the minute of day / 375. A decision at minute i sees the last
60 minutes (left-padded with zeros before 09:15). The LSTM: 2 layers x 64 units, dropout 0.2, Adam 1e-3, batch 64,
8 epochs, seed fixed, CPU (4 threads); outputs one logit per label column (masked BCE where a label is missing)."""
from __future__ import annotations

import numpy as np

import pe

pw, C = pe.pw, pe.C
W, NF = 60, 6


def session_feats(S):
    F = S.F
    c, h, l, atr, vw = F["c"], F["h"], F["l"], F["atr"], F["vwap"]
    n = len(c)
    out = np.zeros((n, NF), dtype=np.float32)
    out[1:, 0] = np.diff(np.log(c)) * 1e4
    a = np.where(atr > 0, atr, 1.0)
    out[:, 1] = (h - l) / a
    out[:, 2] = (c - vw) / a
    last = [np.nan, np.nan]
    for i in range(n):
        K = int(round(c[i] / pw.STEP) * pw.STEP)
        for q, opt in enumerate(("CE", "PE")):
            m = C.leg_mark(S, K, opt, i)
            if m is not None:
                last[q] = m / c[i] * 1e4
            out[i, 3 + q] = last[q] if last[q] == last[q] else 0.0
        out[i, 5] = i / 375.0
    return np.nan_to_num(out)


def window(feats, i):
    x = np.zeros((W, NF), dtype=np.float32)
    lo = max(0, i - W + 1)
    seg = feats[lo: i + 1]
    x[W - len(seg):] = seg
    return x


class Standard:
    def __init__(self, X):
        flat = X.reshape(-1, X.shape[-1])
        self.mu, self.sd = flat.mean(axis=0), flat.std(axis=0) + 1e-6

    def __call__(self, X):
        return ((X - self.mu) / self.sd).astype(np.float32)


def train_lstm(X, Y, seed=191, epochs=8, static=None):
    """X: (n, W, NF) standardised; Y: (n, k) in {0, 1, nan}; static: optional (n, s) appended to the last state."""
    import torch
    from torch import nn
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    k = Y.shape[1]
    s_dim = 0 if static is None else static.shape[1]

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(X.shape[2], 64, num_layers=2, batch_first=True, dropout=0.2)
            self.head = nn.Linear(64 + s_dim, k)

        def forward(self, x, s=None):
            h, _ = self.lstm(x)
            z = h[:, -1, :]
            if s is not None:
                z = torch.cat([z, s], dim=1)
            return self.head(z)
    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    Xt = torch.tensor(X)
    Yt = torch.tensor(np.nan_to_num(Y, nan=0.0), dtype=torch.float32)
    Mt = torch.tensor(~np.isnan(Y), dtype=torch.float32)
    St = None if static is None else torch.tensor(static.astype(np.float32))
    rng = np.random.default_rng(seed)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    for _ep in range(epochs):
        net.train()
        for b in np.array_split(rng.permutation(len(X)), max(1, len(X) // 64)):
            opt.zero_grad()
            out = net(Xt[b], None if St is None else St[b])
            loss = (loss_fn(out, Yt[b]) * Mt[b]).sum() / Mt[b].sum().clamp(min=1.0)
            loss.backward()
            opt.step()
    net.eval()
    return net


def predict(net, X, static=None):
    import torch
    with torch.no_grad():
        out = net(torch.tensor(X), None if static is None else torch.tensor(static.astype(np.float32)))
        return torch.sigmoid(out).numpy()


def train_regressor(X, y, static, seed=192, epochs=30):
    """LSTM regression (MSE) with static features appended (for SN192)."""
    import torch
    from torch import nn
    torch.manual_seed(seed)
    torch.set_num_threads(4)

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(X.shape[2], 32, num_layers=1, batch_first=True)
            self.head = nn.Sequential(nn.Linear(32 + static.shape[1], 16), nn.ReLU(), nn.Linear(16, 1))

        def forward(self, x, s):
            h, _ = self.lstm(x)
            return self.head(torch.cat([h[:, -1, :], s], dim=1)).squeeze(1)
    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    Xt, St, yt = torch.tensor(X), torch.tensor(static.astype(np.float32)), torch.tensor(y.astype(np.float32))
    rng = np.random.default_rng(seed)
    for _ep in range(epochs):
        for b in np.array_split(rng.permutation(len(X)), max(1, len(X) // 32)):
            opt.zero_grad()
            loss = ((net(Xt[b], St[b]) - yt[b]) ** 2).mean()
            loss.backward()
            opt.step()
    net.eval()
    return net


def predict_reg(net, X, static):
    import torch
    with torch.no_grad():
        return net(torch.tensor(X), torch.tensor(static.astype(np.float32))).numpy()
