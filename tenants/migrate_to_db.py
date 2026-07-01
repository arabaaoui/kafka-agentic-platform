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

async def migrate_to_db():
    yaml_path = Path("/app/tenants/enterprise.yaml")
    if not yaml_path.exists():
        print("YAML not found")
        return

    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    envs = config.get("envs", {})
    
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        for slug, cfg in envs.items():
            if slug == "lab":
                continue # Keep lab in YAML
                
            print(f"Migrating {slug} to DB...")
            
            # Check if exists
            res = await conn.execute(
                text("SELECT id FROM infrastructure_envs WHERE tenant = 'enterprise' AND slug = :slug"),
                {"slug": slug}
            )
            row = res.fetchone()
            
            if not row:
                proxy_base = cfg.get("proxy_url", "")
                user = cfg.get("proxy_user", "")
                password = cfg.get("proxy_pass", "")
                if user and password and "://" in proxy_base and "@" not in proxy_base:
                    scheme, host = proxy_base.split("://", 1)
                    proxy_url = f"{scheme}://{user}:{password}@{host}"
                else:
                    proxy_url = proxy_base

                stmt = text("""
                    INSERT INTO infrastructure_envs (
                        id, tenant, slug, display_name, badge_color, clusters, 
                        kubeconfig, kubeconfig_content, kafka_namespace, prom_url, vm_url, 
                        kube_context, alertmanager_url, proxy_url, proxy_user, proxy_pass,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, 'enterprise', :slug, :dn, :bc, :cl, 
                        :kc_path, :kc, :ns, :pu, :vu, 
                        :kctx, :am_url, :prx_url, :prx_user, :prx_pass,
                        :now, :now
                    )
                """)
                await conn.execute(stmt, {
                    "id": str(uuid.uuid4()),
                    "slug": slug,
                    "dn": cfg.get("display_name", slug.upper()),
                    "bc": cfg.get("badge_color", "gray"),
                    "cl": json.dumps(cfg.get("clusters", [])),
                    "kc_path": cfg.get("kubeconfig", ""),
                    "kc": cfg.get("kubeconfig_content", ""),
                    "ns": cfg.get("kafka_namespace", "kafka"),
                    "pu": cfg.get("prom_url", ""),
                    "vu": cfg.get("vm_url", ""),
                    "kctx": cfg.get("kube_context", ""),
                    "am_url": cfg.get("alertmanager_url", ""),
                    "prx_url": proxy_url,
                    "prx_user": user,
                    "prx_pass": password,
                    "now": datetime.now(timezone.utc)
                })
                print(f"Created {slug} in DB")
            else:
                print(f"{slug} already in DB, skipping")

    print("Migration finished.")

if __name__ == "__main__":
    asyncio.run(migrate_to_db())
