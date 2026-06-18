"""GCP Token Provider — environment-agnostic GKE authentication."""

from __future__ import annotations

import logging
import json
import os
from typing import Optional

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.auth import impersonated_credentials

log = logging.getLogger(__name__)

class GCPTokenProvider:
    """Generates fresh access tokens for GKE using Master Key, ADC or Impersonation."""

    @classmethod
    async def _get_base_credentials(cls):
        """Get the primary identity of the platform."""
        # 1. Try to find a Master Key in the environment or a specific file
        master_key_path = os.getenv("PLATFORM_GSA_KEY_PATH", "/app/kube_conf/platform_master_key.json")
        
        if os.path.exists(master_key_path):
            try:
                log.debug("GCP: Attempting to use Platform Master Key from %s", master_key_path)
                return service_account.Credentials.from_service_account_file(
                    master_key_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            except Exception as exc:
                log.warning("GCP: Master Key found but invalid, falling back to ADC: %s", exc)

        # 2. Fallback to ADC (Works for both GKE Workload Identity and Local PC)
        log.debug("GCP: Using Application Default Credentials (ADC)")
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return creds

    @classmethod
    async def get_token(cls, target_gsa_email: Optional[str] = None) -> str:
        """
        Get a valid access token. 
        If target_gsa_email is provided, performs impersonation.
        """
        creds = await cls._get_base_credentials()

        # Refresh if needed
        if not creds.valid:
            creds.refresh(Request())

        # If no impersonation needed, return base token
        if not target_gsa_email:
            return creds.token

        # Perform Impersonation using the base identity
        log.info("GCP: Generating impersonated token for %s", target_gsa_email)
        
        target_creds = impersonated_credentials.Credentials(
            source_credentials=creds,
            target_principal=target_gsa_email,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
            lifetime=3600
        )
        
        target_creds.refresh(Request())
        return target_creds.token
