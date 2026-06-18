"""Alertmanager poller — active monitoring of configured Alertmanager instances.

Periodically queries all Alertmanager URLs defined in infrastructure_envs
and feeds the filter engine with active alerts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select, text

from core.db import get_engine
from core.models import InfrastructureEnv
from triggers.alertmanager_webhook import AlertmanagerWebhookHandler

log = logging.getLogger(__name__)


class AlertmanagerPoller:
    """Polls multiple Alertmanager instances for active alerts."""

    def __init__(self, interval_seconds: int = 60) -> None:
        self._interval = interval_seconds
        self._http = httpx.AsyncClient(timeout=10.0, verify=False) # Internal AMs might have self-signed certs

    async def start(self) -> None:
        log.info("AlertmanagerPoller: starting loop (interval=%ds)", self._interval)
        try:
            while True:
                await self._poll_all()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            log.info("AlertmanagerPoller: stopping")
        finally:
            await self._http.aclose()

    async def _poll_all(self) -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            q = select(InfrastructureEnv).where(InfrastructureEnv.alertmanager_url != "")
            res = await conn.execute(q)
            envs = res.fetchall()

            if not envs:
                return

            for env in envs:
                await self._poll_one(env, conn)

    async def _poll_one(self, env: Any, db_conn: Any) -> None:
        url = env.alertmanager_url.rstrip("/")
        api_url = f"{url}/api/v2/alerts?active=true&silenced=false&inhibited=false"
        
        log.debug("AlertmanagerPoller: polling %s (%s)", env.slug, url)
        
        try:
            # Use specific client if proxy is required
            client = self._http
            if env.proxy_url:
                # Permissive SSL context for internal proxies/targets
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                try:
                    ssl_context.set_ciphers('DEFAULT@SECLEVEL=0')
                except Exception:
                    pass
                
                # Use httpx.Proxy for better compatibility
                proxy = httpx.Proxy(url=env.proxy_url)
                client = httpx.AsyncClient(proxy=proxy, timeout=10.0, verify=ssl_context)
            
            try:
                resp = await client.get(api_url)
                resp.raise_for_status()
                alerts = resp.json()
            finally:
                if client is not self._http:
                    await client.aclose()
            
            if not alerts:
                return []

            # Re-wrap in the structure expected by AlertmanagerWebhookHandler
            # (which expects a list of alerts under the "alerts" key)
            payload = {"alerts": alerts}
            
            # Use the existing handler logic (it works on single alerts but the handler
            # takes a payload with a list of alerts).
            
            # For simplicity, we'll re-instantiate a handler per env
            handler = AlertmanagerWebhookHandler(
                db_conn=db_conn,
                tenant=env.tenant,
            )

            result = await handler.handle(payload)
            matched = result.get("accepted", 0)
            if matched:
                log.info("AlertmanagerPoller: %s inserted %d matched triggers", env.slug, matched)

        except Exception as exc:
            log.exception("AlertmanagerPoller: failed to poll %s", env.slug)


async def start_alertmanager_poller() -> None:
    log.info("Starting Alertmanager poller task...")
    try:
        poller = AlertmanagerPoller()
        await poller.start()
    except Exception as exc:
        log.error("Alertmanager poller task failed to start: %s", exc, exc_info=True)
