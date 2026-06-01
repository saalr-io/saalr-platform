from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from saalr_brokers.credentials import EnvCredentialResolver, build_alpaca_adapter
from saalr_core.db.session import create_sessionmaker, tenant_session
from saalr_core.oms import repo as core_repo
from saalr_core.oms.reconcile import reconcile_account

_logger = logging.getLogger("saalr.oms.worker")


def _default_adapter_factory(account):
    return build_alpaca_adapter(account.credential_ref, account.is_paper,
                                EnvCredentialResolver(os.environ))


async def reconcile_once(app_sessionmaker, admin_engine, *, adapter_factory, now) -> int:
    """Discover active alpaca accounts (admin engine bypasses RLS), reconcile each in a tenant txn."""
    admin_sm = create_sessionmaker(admin_engine)
    async with admin_sm() as s:
        accounts = await core_repo.list_active_alpaca_accounts(s)

    reconciled = 0
    for acct in accounts:
        try:
            async with tenant_session(app_sessionmaker, acct.tenant_id) as s:
                account = await core_repo.get_broker_account(s, acct.broker_account_id)
                if account is None:
                    continue
                adapter = adapter_factory(account)
                await reconcile_account(s, adapter, account, now=now)
            reconciled += 1
        except Exception:  # crash isolation: one bad account never stops the loop
            _logger.exception("reconcile failed for account %s", acct.broker_account_id)
    return reconciled


async def run_reconcile(app_sessionmaker, admin_engine, *, adapter_factory=None, once: bool = False,
                        interval: float = 5.0, now: datetime | None = None) -> None:
    factory = adapter_factory or _default_adapter_factory
    while True:
        stamp = now or datetime.now(timezone.utc)
        n = await reconcile_once(app_sessionmaker, admin_engine, adapter_factory=factory, now=stamp)
        _logger.info("reconciled %d alpaca account(s)", n)
        if once:
            return
        await asyncio.sleep(interval)
