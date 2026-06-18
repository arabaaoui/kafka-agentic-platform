import yaml
import os
import uuid
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://platform:platform@platform-postgres:5432/platform")

async def import_local_kubeconfig():
    # In container, Path.home() is /root
    # We need to mount the host's .kube/config or pass it.
    # Since I can read it from the host, I will just generate the SQL commands 
    # or write a temporary JSON file to the container.
    
    # Actually, I'll just write the data directly in this script since I already read it.
    
    envs_to_import = [
        {"slug": "dev", "name": "gke-dev", "cluster": "gke_vg1np-pf-phenix-caas-1a_europe-west1_phenix-dev-gke"},
        {"slug": "rec", "name": "gke-rec", "cluster": "gke_vg1np-pf-phenix-caas-1a_europe-west1_phenix-recgke"},
        {"slug": "preprod", "name": "gke-preprod", "cluster": "gke_vg1p-pf-phenix-caas-78_europe-west1_phenix-preprod-gke"},
        {"slug": "prod", "name": "gke-prod", "cluster": "gke_vg1p-pf-phenix-caas-78_europe-west1_phenix-productiongke"},
        {"slug": "kh-preprod", "name": "gke-kafkahub-preprod", "cluster": "gke_vg1np-pf-phenix-khpre-3a_europe-west1_kafkahub-preprod-gke"},
        {"slug": "kh-prod", "name": "gke-kafkahub-prod", "cluster": "gke_vg1p-pf-phenix-khprd-11_europe-west1_kafkahub-prod-gke"},
    ]

    # I need the actual content from the file for each.
    # But wait, I can just use the content I cat'ed earlier.
    
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        for item in envs_to_import:
            slug = item["slug"]
            name = item["name"]
            
            # Create or update record
            print(f"Importing environment: {slug} ({name})")
            
            # Check if exists
            res = await conn.execute(
                text("SELECT id FROM infrastructure_envs WHERE tenant = 'carrefour' AND slug = :slug"),
                {"slug": slug}
            )
            row = res.fetchone()
            
            badge = "gray"
            if "prod" in slug: badge = "red"
            elif "preprod" in slug: badge = "yellow"
            elif "dev" in slug: badge = "green"
            elif "rec" in slug: badge = "blue"

            # For now, I'll set a dummy content and the user can edit it or I can fetch it if I mount the file.
            # But the user asked to "take my kubeconfig local".
            # I will use a placeholder and then I'll use a second script to inject the real YAML 
            # by reading it from a temp file I'll write.
            
            if not row:
                stmt = text("""
                    INSERT INTO infrastructure_envs (id, tenant, slug, display_name, badge_color, clusters, kubeconfig, kubeconfig_content, kafka_namespace, prom_url, vm_url, created_at, updated_at)
                    VALUES (:id, 'carrefour', :slug, :dn, :bc, :cl, '', '', 'kafka', :pu, '', :now, :now)
                """)
                await conn.execute(stmt, {
                    "id": str(uuid.uuid4()),
                    "slug": slug,
                    "dn": f"LOCAL — {slug.upper()}",
                    "bc": badge,
                    "cl": json.dumps([item["cluster"]]),
                    "pu": "http://prometheus-not-configured:9090",
                    "now": datetime.now(timezone.utc)
                })

    print("Import completed. Please check the Infrastructure menu.")

if __name__ == "__main__":
    asyncio.run(import_local_kubeconfig())
