"""
Shared helpers for HCP Terraform onboarding scripts.
"""

from pytfe import TFEClient, TFEConfig
from pytfe._http import HTTPTransport
import datetime

from pytfe.models import (
    Project,
    ProjectCreateOptions,
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


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def list_teams(http: HTTPTransport, org: str) -> dict[str, str]:
    """Return a dict of {team_name: team_id} for all teams in the org."""
    response = http.request("GET", f"/api/v2/organizations/{org}/teams")
    data = response.json().get("data", [])
    return {t["attributes"]["name"]: t["id"] for t in data}


def create_team(http: HTTPTransport, org: str, name: str) -> str:
    """Create a team with organisation read-only access and return its ID."""
    payload = {
        "data": {
            "type": "teams",
            "attributes": {
                "name": name,
                "visibility": "secret",
                "organization-access": {
                    "manage-policies": False,
                    "manage-policy-overrides": False,
                    "manage-workspaces": False,
                    "manage-vcs-settings": False,
                    "manage-providers": False,
                    "manage-modules": False,
                    "manage-run-tasks": False,
                    "manage-projects": False,
                    "read-workspaces": True,
                    "read-projects": True,
                    "manage-membership": False,
                },
            },
        }
    }
    response = http.request("POST", f"/api/v2/organizations/{org}/teams", json_body=payload)
    return response.json()["data"]["id"]


def ensure_teams(http: HTTPTransport, org: str, prefix: str) -> dict[str, str]:
    """
    Ensure the three onboarding teams exist.
    Returns {role: team_id} e.g. {"reader": "team-abc", ...}
    """
    roles = ["reader", "contributor", "cicd"]
    existing = list_teams(http, org)
    team_ids: dict[str, str] = {}

    for role in roles:
        team_name = f"{prefix}-{role}"
        if team_name in existing:
            print(f"  [skip] Team '{team_name}' already exists (id={existing[team_name]})")
            team_ids[role] = existing[team_name]
        else:
            tid = create_team(http, org, team_name)
            print(f"  [ok]   Created team '{team_name}' (id={tid})")
            team_ids[role] = tid

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


def ensure_projects(client: TFEClient, org: str, prefix: str) -> dict[str, str]:
    """
    Ensure nprod and prod projects exist.
    Returns {"nprod": project_id, "prod": project_id}
    """
    envs = ["nprod", "prod"]
    existing = list_projects(client, org)
    project_ids: dict[str, str] = {}

    for env in envs:
        project_name = f"{prefix}-{env}"
        if project_name in existing:
            print(f"  [skip] Project '{project_name}' already exists (id={existing[project_name]})")
            project_ids[env] = existing[project_name]
        else:
            opts = ProjectCreateOptions(name=project_name)
            project = client.projects.create(org, opts)
            print(f"  [ok]   Created project '{project_name}' (id={project.id})")
            project_ids[env] = project.id

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
    access: str,
) -> None:
    """Grant a team access to a project via the team-projects API."""
    payload = {
        "data": {
            "type": "team-projects",
            "attributes": {"access": access},
            "relationships": {
                "team": {"data": {"id": team_id, "type": "teams"}},
                "project": {"data": {"id": project_id, "type": "projects"}},
            },
        }
    }
    http.request("POST", "/api/v2/team-projects", json_body=payload)


def assign_team_access(
    http: HTTPTransport,
    team_ids: dict[str, str],
    project_ids: dict[str, str],
    project_prefix: str,
    team_prefix: str,
) -> None:
    """
    Add teams to both projects with the required access levels:
      reader      -> read
      contributor -> write
      cicd        -> write
    """
    access_map = {
        "reader": "read",
        "contributor": "write",
        "cicd": "write",
    }

    for env, project_id in project_ids.items():
        project_name = f"{project_prefix}-{env}"
        existing_team_ids = get_existing_team_project_access(http, project_id)

        for role, access in access_map.items():
            team_id = team_ids[role]
            team_name = f"{team_prefix}-{role}"
            if team_id in existing_team_ids:
                print(f"  [skip] Team '{team_name}' already has access to project '{project_name}'")
            else:
                grant_team_project_access(http, team_id, project_id, access)
                print(
                    f"  [ok]   Granted '{access}' access to team '{team_name}'"
                    f" on project '{project_name}'"
                )


# ---------------------------------------------------------------------------
# Projects (delete)
# ---------------------------------------------------------------------------

def delete_team_project_access(http: HTTPTransport, project_id: str) -> None:
    """Remove all team-project access entries for a project."""
    response = http.request(
        "GET",
        "/api/v2/team-projects",
        params={"filter[project][id]": project_id},
    )
    for entry in response.json().get("data", []):
        http.request("DELETE", f"/api/v2/team-projects/{entry['id']}")
        print(f"  [ok]   Removed team access entry {entry['id']}")


def delete_projects(http: HTTPTransport, client: TFEClient, org: str, prefix: str) -> None:
    """Remove team access then delete nprod and prod projects."""
    existing = list_projects(client, org)
    for env in ["nprod", "prod"]:
        project_name = f"{prefix}-{env}"
        if project_name not in existing:
            print(f"  [skip] Project '{project_name}' not found")
            continue
        project_id = existing[project_name]
        delete_team_project_access(http, project_id)
        client.projects.delete(project_id)
        print(f"  [ok]   Deleted project '{project_name}'")


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
    for env in ["nprod", "prod"]:
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
    all_policy_sets = {ps.name: ps.id for ps in client.policy_sets.list(org, PolicySetListOptions())}
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
