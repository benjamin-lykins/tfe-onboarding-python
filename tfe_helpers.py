"""
Shared helpers for HCP Terraform onboarding scripts.
"""

from pytfe import TFEClient, TFEConfig
from pytfe._http import HTTPTransport
import base64
import datetime

import httpx
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from pytfe.models import (
    Project,
    ProjectListOptions,
    PolicySetAddProjectsOptions,
    PolicySetListOptions,
    PolicySetRemoveProjectsOptions,
    VariableSetApplyToProjectsOptions,
    VariableSetCreateOptions,
    VariableSetListOptions,
)



def get_http(config: TFEConfig) -> HTTPTransport:
    return HTTPTransport(
        address=config.address,
        token=config.token,
        timeout=config.timeout,
        verify_tls=config.verify_tls,
        user_agent_suffix=config.user_agent_suffix,
        max_retries=config.max_retries,
        backoff_base=config.backoff_base,
        backoff_cap=config.backoff_cap,
        backoff_jitter=config.backoff_jitter,
        http2=config.http2,
        proxies=config.proxies,
        ca_bundle=config.ca_bundle,
    )



DEFAULT_ENVIRONMENTS: list[str] = [
    "nprd",
    "prod",
]

# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def list_teams(http: HTTPTransport, org: str) -> dict[str, str]:
    """Return a dict of {team_name: team_id} for all teams in the org."""
    response = http.request("GET", f"/api/v2/organizations/{org}/teams")
    data = response.json().get("data", [])
    return {t["attributes"]["name"]: t["id"] for t in data}


def create_team(http: HTTPTransport, org: str, name: str) -> str:
    """
    Create a team with no organisation access and return its ID.
    Permissions will be set on a project level. 
    """
    payload = {
        "data": {
            "type": "teams",
            "attributes": {
                "name": name,
                "visibility": "secret",
                "permissions": {},
                "allow-member-token-management": False,
            },
        }
    }
    response = http.request("POST", f"/api/v2/organizations/{org}/teams", json_body=payload)
    return response.json()["data"]["id"]


def ensure_teams(http: HTTPTransport, org: str, prefix: str) -> dict[str, str]:
    """
    Ensure the six onboarding teams exist (three per environment).
    Returns {"nprd-reader": team_id, "nprd-contributor": team_id, "nprd-cicd": team_id,
             "prod-reader": team_id, "prod-contributor": team_id, "prod-cicd": team_id}
    """
    roles = ["reader", "contributor", "cicd"]
    existing = list_teams(http, org)
    team_ids: dict[str, str] = {}

    for env in DEFAULT_ENVIRONMENTS:
        for role in roles:
            key = f"{env}-{role}"
            team_name = f"{prefix}-{key}"
            if team_name in existing:
                print(f"  [skip] Team '{team_name}' already exists (id={existing[team_name]})")
                team_ids[key] = existing[team_name]
            else:
                tid = create_team(http, org, team_name)
                print(f"  [ok]   Created team '{team_name}' (id={tid})")
                team_ids[key] = tid

    return team_ids


# ---------------------------------------------------------------------------
# Team Tokens
# ---------------------------------------------------------------------------

def _get_org_team_tokens(http: HTTPTransport, org: str) -> list[dict]:
    """Return all team tokens for the org from the list endpoint."""
    response = http.request("GET", f"/api/v2/organizations/{org}/team-tokens")
    return response.json().get("data", [])


def _find_token_for_team(org_tokens: list[dict], team_id: str, description: str) -> dict | None:
    """Return the token entry matching both team_id and description, or None."""
    for token in org_tokens:
        rel_team = token.get("relationships", {}).get("team", {}).get("data", {})
        if rel_team.get("id") == team_id and token.get("attributes", {}).get("description") == description:
            return token
    return None


def create_team_tokens(
    http: HTTPTransport,
    org: str,
    team_ids: dict[str, str],
    prefix: str,
    description: str,
) -> dict[str, str]:
    """
    Create a token for each team if one does not already exist.
    Returns {role: token_value} — only includes newly created tokens since
    existing token values are not returned by the API.
    """
    org_tokens = _get_org_team_tokens(http, org)
    tokens: dict[str, str] = {}

    for role, team_id in team_ids.items():
        team_name = f"{prefix}-{role}"
        existing = _find_token_for_team(org_tokens, team_id, description)
        if existing:
            print(f"  [skip] Token with description '{description}' already exists for team '{team_name}' (id={existing['id']})")
            continue
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).isoformat()
        payload = {
            "data": {
                "type": "authentication-tokens",
                "attributes": {
                    "description": description,
                    "expired-at": expires_at,
                },
            }
        }
        response = http.request(
            "POST",
            f"/api/v2/teams/{team_id}/authentication-tokens",
            json_body=payload,
        )
        token_value = response.json()["data"]["attributes"]["token"]
        tokens[role] = token_value
        print(f"  [ok]   Created token for team '{team_name}' (description: {description})")

    return tokens


def delete_team_tokens(
    http: HTTPTransport,
    org: str,
    team_ids: dict[str, str],
    prefix: str,
    description: str,
) -> None:
    """Delete the token matching description for each team using the token ID from the list endpoint."""
    org_tokens = _get_org_team_tokens(http, org)

    for role, team_id in team_ids.items():
        team_name = f"{prefix}-{role}"
        existing = _find_token_for_team(org_tokens, team_id, description)
        if not existing:
            print(f"  [skip] No token with description '{description}' found for team '{team_name}'")
            continue
        http.request("DELETE", f"/api/v2/authentication-tokens/{existing['id']}")
        print(f"  [ok]   Revoked token with description '{description}' for team '{team_name}'")


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def list_projects(client: TFEClient, org: str) -> dict[str, str]:
    """Return a dict of {project_name: project_id}."""
    projects = client.projects.list(org, ProjectListOptions())
    return {p.name: p.id for p in projects}


def list_project_workspaces(http: HTTPTransport, org: str, project_id: str) -> list[str]:
    """Return a list of workspace names belonging to the given project."""
    response = http.request(
        "GET",
        f"/api/v2/organizations/{org}/workspaces",
        params={"filter[project][id]": project_id},
    )
    return [ws["attributes"]["name"] for ws in response.json().get("data", [])]


def ensure_projects(
    http: HTTPTransport,
    client: TFEClient,
    org: str,
    prefix: str,
    agent_pool_name: str | None = None,
) -> dict[str, str]:
    """
    Ensure nprod and prod projects exist.
    Returns {"nprod": project_id, "prod": project_id}

    If agent_pool_name is provided, new projects are created with
    default-execution-mode=agent and the resolved agent pool assigned.
    """
    envs = list(_PROJECT_TO_TEAM_ENV)
    existing = list_projects(client, org)

    agent_pool_id: str | None = None
    if agent_pool_name:
        agent_pool_id = _resolve_agent_pool_id(http, org, agent_pool_name)

    project_ids: dict[str, str] = {}

    for env in envs:
        project_name = f"{prefix}-{env}"
        if project_name in existing:
            print(f"  [skip] Project '{project_name}' already exists (id={existing[project_name]})")
            project_ids[env] = existing[project_name]
        else:
            body: dict = {
                "data": {
                    "type": "projects",
                    "attributes": {"name": project_name},
                }
            }
            if agent_pool_id:
                body["data"]["attributes"]["default-execution-mode"] = "agent"
                body["data"]["relationships"] = {
                    "default-agent-pool": {
                        "data": {"type": "agent-pools", "id": agent_pool_id}
                    }
                }
            response = http.request("POST", f"/api/v2/organizations/{org}/projects", json_body=body)
            project_id = response.json()["data"]["id"]
            print(f"  [ok]   Created project '{project_name}' (id={project_id})")
            project_ids[env] = project_id

    return project_ids


# ---------------------------------------------------------------------------
# Team-Project Access
# ---------------------------------------------------------------------------

def get_existing_team_project_access(http: HTTPTransport, project_id: str) -> set[str]:
    """Return a set of team IDs that already have access to the given project."""
    response = http.request(
        "GET",
        "/api/v2/team-projects",
        params={"filter[project][id]": project_id},
    )
    data = response.json().get("data", [])
    return {item["relationships"]["team"]["data"]["id"] for item in data}


def grant_team_project_access(
    http: HTTPTransport,
    team_id: str,
    project_id: str,
    attributes: dict,
) -> None:
    """Grant a team access to a project via the team-projects API."""
    payload = {
        "data": {
            "type": "team-projects",
            "attributes": attributes,
            "relationships": {
                "team": {"data": {"id": team_id, "type": "teams"}},
                "project": {"data": {"id": project_id, "type": "projects"}},
            },
        }
    }
    http.request("POST", "/api/v2/team-projects", json_body=payload)


# Access configurations per role:
#   reader      - read-only access to the project
#   contributor - custom: plan-only runs, no other permissions
#   cicd        - custom: create workspaces, apply runs, read/write variables
_ROLE_ACCESS: dict[str, dict] = {
    "reader": {
        "access": "read",
    },
    "contributor": {
        "access": "custom",
        "project-access": {"settings": "read", "teams": "none"},
        "workspace-access": {
            "runs": "plan",
            "sentinel-mocks": "none",
            "state-versions": "none",
            "variables": "none",
            "create": False,
            "locking": False,
            "delete": False,
            "move": False,
            "run-tasks": False,
        },
    },
    "cicd": {
        "access": "custom",
        "project-access": {"settings": "read", "teams": "none"},
        "workspace-access": {
            "runs": "apply",
            "sentinel-mocks": "none",
            "state-versions": "read-outputs",
            "variables": "write",
            "create": True,
            "locking": False,
            "delete": False,
            "move": False,
            "run-tasks": False,
        },
    },
}


# Maps project env key → team env key
_PROJECT_TO_TEAM_ENV: dict[str, str] = {"nprod": "nprd", "prod": "prod"}


def assign_team_access(
    http: HTTPTransport,
    team_ids: dict[str, str],
    project_ids: dict[str, str],
    project_prefix: str,
    team_prefix: str,
) -> None:
    """
    Add env-scoped teams to their matching project with role-specific access:
      {env}-reader      -> read
      {env}-contributor -> custom: plan-only runs
      {env}-cicd        -> custom: create workspaces, apply runs, read/write variables
    """
    for env, project_id in project_ids.items():
        project_name = f"{project_prefix}-{env}"
        team_env = _PROJECT_TO_TEAM_ENV[env]
        existing_team_ids = get_existing_team_project_access(http, project_id)

        for role, attributes in _ROLE_ACCESS.items():
            key = f"{team_env}-{role}"
            team_id = team_ids[key]
            team_name = f"{team_prefix}-{key}"
            if team_id in existing_team_ids:
                print(f"  [skip] Team '{team_name}' already has access to project '{project_name}'")
            else:
                grant_team_project_access(http, team_id, project_id, attributes)
                print(
                    f"  [ok]   Granted '{attributes['access']}' access to team '{team_name}'"
                    f" on project '{project_name}'"
                )


# ---------------------------------------------------------------------------
# Projects (delete)
# ---------------------------------------------------------------------------

def delete_projects(http: HTTPTransport, client: TFEClient, org: str, prefix: str) -> None:
    """Remove team access then delete nprod and prod projects."""
    existing = list_projects(client, org)
    for env in _PROJECT_TO_TEAM_ENV:
        project_name = f"{prefix}-{env}"
        if project_name not in existing:
            print(f"  [skip] Project '{project_name}' not found")
            continue
        project_id = existing[project_name]
        client.projects.delete(project_id)
        print(f"  [ok]   Deleted project '{project_name}'")


def delete_teams(http: HTTPTransport, org: str, prefix: str) -> None:
    """Delete the six onboarding teams (three per environment) for a given prefix."""
    existing = list_teams(http, org)
    for env in DEFAULT_ENVIRONMENTS:
        for role in ["reader", "contributor", "cicd"]:
            team_name = f"{prefix}-{env}-{role}"
            if team_name not in existing:
                print(f"  [skip] Team '{team_name}' not found")
                continue
            team_id = existing[team_name]
            http.request("DELETE", f"/api/v2/teams/{team_id}")
            print(f"  [ok]   Deleted team '{team_name}'")


# ---------------------------------------------------------------------------
# Variable Sets
# ---------------------------------------------------------------------------

def ensure_varsets(
    client: TFEClient,
    org: str,
    project_ids: dict[str, str],
    prefix: str,
) -> None:
    """Create one variable set per environment and assign it to its project."""
    existing_varsets = {
        vs.name: vs.id
        for vs in client.variable_sets.list(org, VariableSetListOptions())
    }

    for env, project_id in project_ids.items():
        varset_name = f"{prefix}-{env}"

        if varset_name in existing_varsets:
            varset_id = existing_varsets[varset_name]
            print(f"  [skip] Variable set '{varset_name}' already exists (id={varset_id})")
        else:
            opts = VariableSetCreateOptions(
                name=varset_name,
                description=f"Variable set for {prefix} {env} environment",
                **{"global": False},
            )
            varset = client.variable_sets.create(org, opts)
            varset_id = varset.id
            print(f"  [ok]   Created variable set '{varset_name}' (id={varset_id})")

        projects_payload = VariableSetApplyToProjectsOptions(
            projects=[Project(id=project_id)]
        )
        client.variable_sets.apply_to_projects(varset_id, projects_payload)
        print(f"  [ok]   Assigned variable set '{varset_name}' to project '{prefix}-{env}'")


def delete_varsets(client: TFEClient, org: str, prefix: str) -> None:
    """Delete the nprod and prod variable sets for a prefix."""
    existing = {
        vs.name: vs.id
        for vs in client.variable_sets.list(org, VariableSetListOptions())
    }
    for env in _PROJECT_TO_TEAM_ENV:
        varset_name = f"{prefix}-{env}"
        if varset_name not in existing:
            print(f"  [skip] Variable set '{varset_name}' not found")
            continue
        client.variable_sets.delete(existing[varset_name])
        print(f"  [ok]   Deleted variable set '{varset_name}'")


# ---------------------------------------------------------------------------
# Policy Sets
# ---------------------------------------------------------------------------

def _resolve_policy_set_ids(client: TFEClient, org: str, names: list[str]) -> dict[str, str]:
    """Return {name: policy_set_id} for the given names, warning on any not found."""
    all_policy_sets = {ps.name: ps.id for ps in client.policy_sets.list(org, PolicySetListOptions()).items}
    resolved: dict[str, str] = {}
    for name in names:
        if name in all_policy_sets:
            resolved[name] = all_policy_sets[name]
        else:
            print(f"  [warn] Policy set '{name}' not found in org — skipping")
    return resolved


def assign_policy_sets(
    client: TFEClient,
    org: str,
    project_ids: dict[str, str],
    policy_set_names: list[str],
) -> None:
    """Attach each project to every policy set in policy_set_names."""
    policy_sets = _resolve_policy_set_ids(client, org, policy_set_names)
    projects = [Project(id=pid) for pid in project_ids.values()]

    for ps_name, ps_id in policy_sets.items():
        client.policy_sets.add_projects(ps_id, PolicySetAddProjectsOptions(projects=projects))
        project_names = ", ".join(f"'{k}'" for k in project_ids)
        print(f"  [ok]   Attached policy set '{ps_name}' to projects {project_names}")


def remove_policy_sets(
    client: TFEClient,
    org: str,
    project_ids: dict[str, str],
    policy_set_names: list[str],
) -> None:
    """Detach each project from every policy set in policy_set_names."""
    policy_sets = _resolve_policy_set_ids(client, org, policy_set_names)
    projects = [Project(id=pid) for pid in project_ids.values()]

    for ps_name, ps_id in policy_sets.items():
        client.policy_sets.remove_projects(ps_id, PolicySetRemoveProjectsOptions(projects=projects))
        project_names = ", ".join(f"'{k}'" for k in project_ids)
        print(f"  [ok]   Detached policy set '{ps_name}' from projects {project_names}")

# ---------------------------------------------------------------------------
# Agent Pools
# ---------------------------------------------------------------------------

def list_agent_pools(http: HTTPTransport, org: str) -> dict[str, str]:
    """Return {pool_name: pool_id} for all agent pools in the org."""
    response = http.request("GET", f"/api/v2/organizations/{org}/agent-pools")
    data = response.json().get("data", [])
    return {p["attributes"]["name"]: p["id"] for p in data}


def _resolve_agent_pool_id(http: HTTPTransport, org: str, name: str) -> str | None:
    """Return the pool_id for the given name, or None with a warning if not found."""
    all_pools = list_agent_pools(http, org)
    if name in all_pools:
        return all_pools[name]
    print(f"  [warn] Agent pool '{name}' not found in org — skipping")
    return None




# ---------------------------------------------------------------------------
# Azure Key Vault
# ---------------------------------------------------------------------------

def set_keyvault_secret(vault_name: str, secret_name: str, secret_value: str) -> None:
    """Create or update a secret in Azure Key Vault using DefaultAzureCredential."""
    vault_url = f"https://{vault_name}.vault.azure.net"
    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    client.set_secret(secret_name, secret_value)


# ---------------------------------------------------------------------------
# GitHub Secrets
# ---------------------------------------------------------------------------

def _github_request(method: str, path: str, token: str, **kwargs) -> httpx.Response:
    """Make a GitHub API request and raise on HTTP errors."""
    response = httpx.request(
        method,
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        **kwargs,
    )
    response.raise_for_status()
    return response


def _encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Encrypt a secret value with the repository's NaCl public key."""
    from nacl import encoding, public as nacl_public
    pk = nacl_public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    box = nacl_public.SealedBox(pk)
    encrypted = box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def set_repo_secret(github_token: str, owner: str, repo: str, secret_name: str, secret_value: str) -> None:
    """Create or update a GitHub Actions secret on the target repository."""
    try:
        key_resp = _github_request("GET", f"/repos/{owner}/{repo}/actions/secrets/public-key", github_token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise RuntimeError(
                f"Could not access '{owner}/{repo}' via the GitHub API (404). "
                "Check that: (1) the repository exists, (2) the token has 'repo' scope, "
                "and (3) GitHub Actions is enabled on the repository "
                "(Settings → Actions → General → Allow all actions)."
            ) from None
        raise
    key_data = key_resp.json()
    encrypted_value = _encrypt_secret(key_data["key"], secret_value)
    _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/actions/secrets/{secret_name}",
        github_token,
        json={"encrypted_value": encrypted_value, "key_id": key_data["key_id"]},
    )


def delete_repo_secret(github_token: str, owner: str, repo: str, secret_name: str) -> None:
    """Delete a GitHub Actions secret from the target repository (no-op if not found)."""
    try:
        _github_request("DELETE", f"/repos/{owner}/{repo}/actions/secrets/{secret_name}", github_token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return
        raise

