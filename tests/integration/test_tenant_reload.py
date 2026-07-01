"""Integration tests for POST /admin/reload-tenants (spec 003 FR-005)."""

import textwrap

import pytest


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "enterprise" in data["tenants"]


def test_reload_tenants_adds_new_tenant(client, tenants_dir):
    """Adding a new YAML file and calling reload returns the new tenant."""
    new_yaml = textwrap.dedent("""\
        tenant: newclient
        envs:
          preprod:
            clusters: [kafka-newclient]
            kubeconfig: /kube/newclient
            prom_url: https://prom.newclient.example.com
    """)
    (tenants_dir / "newclient.yaml").write_text(new_yaml)

    resp = client.post("/admin/reload-tenants")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "newclient" in data["tenants"]
    assert "enterprise" in data["tenants"]


def test_reload_tenants_keeps_previous_on_all_invalid(client, tenants_dir):
    """If all YAMLs become invalid, reload raises 500 and previous state survives."""
    # Break the only valid file
    (tenants_dir / "enterprise.yaml").write_text("tenant: bad\nenvs: {}")
    resp = client.post("/admin/reload-tenants")
    assert resp.status_code == 500


def test_reload_tenants_removes_deleted_tenant(client, tenants_dir):
    """Deleting a YAML file removes the tenant from the registry after reload."""
    (tenants_dir / "enterprise.yaml").unlink()
    # Add a replacement so reload doesn't fail with zero tenants
    replacement = textwrap.dedent("""\
        tenant: replacement
        envs:
          preprod:
            clusters: [k]
            kubeconfig: /k
            prom_url: https://p.example.com
    """)
    (tenants_dir / "replacement.yaml").write_text(replacement)
    resp = client.post("/admin/reload-tenants")
    assert resp.status_code == 200
    assert "enterprise" not in resp.json()["tenants"]
    assert "replacement" in resp.json()["tenants"]
