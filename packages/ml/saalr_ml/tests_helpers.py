from __future__ import annotations

import numpy as np


def simulate_garch(n, omega, alpha, beta, mu=0.0, seed=7):
    """Generate a GARCH(1,1) return series (scaled units) for tests."""
    rng = np.random.default_rng(seed)
    r = np.empty(n)
    sigma2 = omega / (1 - alpha - beta)
    resid_prev2 = sigma2
    for t in range(n):
        sigma2 = omega + alpha * resid_prev2 + beta * sigma2
        eps = np.sqrt(sigma2) * rng.standard_normal()
        r[t] = mu + eps
        resid_prev2 = eps * eps
    return r
