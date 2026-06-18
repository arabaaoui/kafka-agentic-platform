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

async def import_real_kubeconfigs():
    # Use the copy we made earlier
    kube_path = Path("/app/tenants/local_kubeconfig.yaml")
    if not kube_path.exists():
        print(f"Error: {kube_path} not found")
        return

    with open(kube_path) as f:
        config = yaml.safe_load(f)

    contexts = config.get("contexts", [])
    clusters = {c["name"]: c["cluster"] for c in config.get("clusters", [])}
    users = {u["name"]: u["user"] for u in config.get("users", [])}

    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        for ctx in contexts:
            name = ctx["name"]
            if not name.startswith("gke-"):
                continue
                
            slug = name.replace("gke-", "")
            cluster_name = ctx["context"]["cluster"]
            user_name = ctx["context"]["user"]
            
            cluster_data = clusters.get(cluster_name)
            user_data = users.get(user_name)
            
            if not cluster_data or not user_data:
                continue

            # Create a standalone kubeconfig for this context
            standalone = {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [{"name": cluster_name, "cluster": cluster_data}],
                "contexts": [{"name": name, "context": {"cluster": cluster_name, "user": user_name}}],
                "current-context": name,
                "users": [{"name": user_name, "user": user_data}]
            }
            
            content = yaml.dump(standalone)
            
            # Determine badge color
            badge = "gray"
            if "prod" in slug: badge = "red"
            elif "preprod" in slug: badge = "yellow"
            elif "dev" in slug: badge = "green"
            elif "rec" in slug: badge = "blue"

            # Create or update record
            print(f"Importing environment: {slug} ({name})")
            
            # Upsert
            stmt = text("""
                INSERT INTO infrastructure_envs (
                    id, tenant, slug, display_name, badge_color, clusters, 
                    kubeconfig, kubeconfig_content, kafka_namespace, prom_url, vm_url, 
                    kube_context, proxy_url, proxy_user, proxy_pass, created_at, updated_at
                )
                VALUES (
                    :id, 'carrefour', :slug, :dn, :bc, :cl, 
                    '', :kc, :ns, :pu, '', 
                    :kctx, '', '', '', :now, :now
                )
                ON CONFLICT (tenant, slug) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    badge_color = EXCLUDED.badge_color,
                    clusters = EXCLUDED.clusters,
                    kubeconfig_content = EXCLUDED.kubeconfig_content,
                    kafka_namespace = EXCLUDED.kafka_namespace,
                    kube_context = EXCLUDED.kube_context,
                    updated_at = EXCLUDED.updated_at
            """)
            
            # Namespaces mapping
            ns = "kafka"
            if "kafkahub" in name: ns = "kafkahub"
            elif "dev" in name: ns = "platform-dev"
            elif "preprod" in name: ns = "platform-preprod"
            elif "prod" in name: ns = "kafka-prod"
            elif "rec" in name: ns = "platform-rec"

            await conn.execute(stmt, {
                "id": str(uuid.uuid4()),
                "slug": slug,
                "dn": f"GKE — {slug.upper()}",
                "bc": badge,
                "cl": json.dumps([cluster_name]),
                "kc": content,
                "ns": ns,
                "pu": "http://prometheus-not-configured:9090",
                "kctx": name,
                "now": datetime.now(timezone.utc)
            })

    print("Import completed.")

if __name__ == "__main__":
    asyncio.run(import_real_kubeconfigs())
