import asyncio
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://platform:platform@platform-postgres:5432/platform"

async def fix_dev_kc():
    engine = create_async_engine(DATABASE_URL)
    kc_path = Path("tenants/local_kubeconfig.yaml")
    if not kc_path.exists():
        print("local_kubeconfig.yaml not found")
        return
        
    content = kc_path.read_text()
    
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE infrastructure_envs SET kubeconfig_content = :c WHERE slug = 'DEV'"),
            {"c": content}
        )
        print("Updated DEV kubeconfig_content")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_dev_kc())
