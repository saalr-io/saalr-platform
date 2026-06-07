from __future__ import annotations

import numpy as np


def lstm_forecast(
    returns, horizon: int, last_close: float, *, seed: int = 0,
    epochs: int = 150, lookback: int = 20, hidden: int = 16,
) -> tuple[list[float], list[list[float]]]:
    """Train a small, seeded LSTM on standardized log-returns; iteratively forecast `horizon`
    returns and compound from `last_close` into a PRICE path. Returns (price_path, ci95_price).
    `returns` must be RAW log-returns (not ×100)."""
    import torch
    from torch import nn

    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.set_num_threads(1)

    r = np.asarray(returns, dtype=float)
    mu, sd = float(r.mean()), float(r.std() or 1.0)
    z = (r - mu) / sd

    xs, ys = [], []
    for i in range(len(z) - lookback):
        xs.append(z[i : i + lookback])
        ys.append(z[i + lookback])
    if not xs:
        raise ValueError("series too short for the LSTM lookback")
    xt = torch.tensor(np.array(xs), dtype=torch.float32).unsqueeze(-1)  # (N, L, 1)
    yt = torch.tensor(np.array(ys), dtype=torch.float32).unsqueeze(-1)  # (N, 1)

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(input_size=1, hidden_size=hidden, batch_first=True)
            self.fc = nn.Linear(hidden, 1)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :])

    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()
    net.train()
    for _ in range(epochs):
        opt.zero_grad()
        loss = loss_fn(net(xt), yt)
        loss.backward()
        opt.step()

    net.eval()
    with torch.no_grad():
        resid = (yt - net(xt)).squeeze(-1).numpy()
        resid_sd = float(resid.std() or 1.0)
        window = torch.tensor(z[-lookback:], dtype=torch.float32).reshape(1, lookback, 1)
        preds_z = []
        for _ in range(horizon):
            nxt = float(net(window).item())
            preds_z.append(nxt)
            window = torch.cat(
                [window[:, 1:, :], torch.tensor([[[nxt]]], dtype=torch.float32)], dim=1
            )

    preds_r = np.array(preds_z) * sd + mu     # de-standardize to raw log-returns
    cum = np.cumsum(preds_r)
    path = last_close * np.exp(cum)
    band = 1.96 * resid_sd * sd * np.sqrt(np.arange(1, horizon + 1))  # widening band
    lo = last_close * np.exp(cum - band)
    hi = last_close * np.exp(cum + band)
    return (
        [round(float(x), 4) for x in path],
        [[round(float(a), 4), round(float(b), 4)] for a, b in zip(lo, hi)],
    )
