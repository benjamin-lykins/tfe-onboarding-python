#!/usr/bin/env python3
"""
HCP Terraform Project Onboarding Script

Given a project name and team name, this script will:
  1. Create three teams (if they don't exist): {team_name}-contributor, {team_name}-reader, {team_name}-cicd
  2. Create a team token for {team_name}-cicd (description = github_repository) and write it
     as the Actions secret TFE_TOKEN on the target GitHub repository
  3. Create two projects: {project_name}-nprod, {project_name}-prod
  4. Grant each team access to both projects (reader=read, contributor=write, cicd=write)
  5. Create a variable set for each project and assign it
  6. Attach each project to the specified policy sets
  7. Grant each project access to the specified agent pools

Environment variables:
  TFE_TOKEN         HCP Terraform API token (required)
  TFE_ORGANIZATION  HCP Terraform organisation name (required)
  TFE_HOSTNAME      HCP Terraform hostname (optional, defaults to app.terraform.io)
  GITHUB_TOKEN      GitHub PAT or fine-grained token with Secrets: read/write on the
                    target repository (optional — skips GitHub secret write if unset)

Optional flags:
  --skip-token-creation   Skip creating the cicd team token and writing it to GitHub.
                          Useful when re-onboarding a project where the token already exists
                          or when GitHub secret management is handled separately.

Usage:
  python onboard.py --project-name <name> --team-name <name> --github-repository <org/repo>
"""

import argparse
import os
import sys

import dotenv
from pytfe import TFEClient, TFEConfig

from tfe_helpers import (
    assign_agent_pool_to_projects,
    assign_policy_sets,
    assign_team_access,
    create_team_tokens,
    ensure_projects,
    ensure_teams,
    ensure_varsets,
    get_http,
    set_repo_secret,
)

# Edit this list to change the default policy sets applied to every onboarded project.
DEFAULT_POLICY_SETS: list[str] = [
    "default-policy",
]

# Edit this string to change the default agent pool applied to every onboarded project.
DEFAULT_AGENT_POOL: str = "default-agent-pool"

# Edit this to update the teams which will get an initial token created during onboarding.
DEFAULT_TEAMS_WITH_TOKENS: list[str] = [
    "cicd",
]



def onboard(
    project_name: str,
    team_name: str,
    org: str,
    github_repository: str,
    github_token: str | None,
    policy_sets: list[str],
    agent_pool: str,
    client: TFEClient,
    http,
    skip_token_creation: bool = False,
) -> None:
    print(f"\n=== Onboarding '{project_name}' into HCP Terraform org ===\n")

    print("Step 1: Ensuring teams exist...")
    team_ids = ensure_teams(http, org, team_name)

    print("\nStep 2: Creating cicd team token...")
    if not skip_token_creation:
        tokens = create_team_tokens(http, org, {"cicd": team_ids["cicd"]}, team_name, description=github_repository)
        if tokens:
            owner, repo_name = github_repository.split("/", 1)
            if not github_token:
                print("  [warn] GITHUB_TOKEN not set — skipping GitHub secret creation")
            else:
                print(f"\n  Writing team tokens as GitHub Actions secrets on {github_repository}:")
            for role, token_value in tokens.items():
                secret_name = f"TFE_TOKEN"
                set_repo_secret(github_token, owner, repo_name, secret_name, token_value)
                print(f"    [ok]   Set secret '{secret_name}'")
    else: 
         print("  [skip] Skipping cicd team token creation and GitHub secret write")


    print("\nStep 3: Ensuring projects exist...")
    project_ids = ensure_projects(client, org, project_name)

    print("\nStep 4: Assigning team access to projects...")
    assign_team_access(http, team_ids, project_ids, project_prefix=project_name, team_prefix=team_name)

    print("\nStep 5: Creating and assigning variable sets...")
    ensure_varsets(client, org, project_ids, project_name)

    print("\nStep 6: Attaching policy sets to projects...")
    assign_policy_sets(client, org, project_ids, policy_sets)

    print("\nStep 7: Assigning agent pools to projects...")
    assign_agent_pool_to_projects(http, org, project_ids, agent_pool, project_prefix=project_name)

    print("\n=== Onboarding complete! ===\n")


if __name__ == "__main__":
    dotenv.load_dotenv(override=True)

    parser = argparse.ArgumentParser(
        description="Onboard a new project into HCP Terraform",
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Project name prefix (e.g. 'myapp'). Projects will be named '{name}-nprod' and '{name}-prod'.",
    )
    parser.add_argument(
        "--team-name",
        required=True,
        help="Team name prefix (e.g. 'myapp'). Teams will be named '{name}-reader', '{name}-contributor', '{name}-cicd'.",
    )
    parser.add_argument(
        "--skip-token-creation",
        required=False,
        action="store_true",
        help="Skip creating the cicd team token and writing it to the GitHub repository.",
    )

    parser.add_argument(
        "--github-repository",
        required=True,
        help="GitHub repository (e.g. 'my-org/my-repo'). Used as the cicd team token description.",
    )
    parser.add_argument(
        "--policy-sets",
        required=False,
        default=",".join(DEFAULT_POLICY_SETS),
        help=(
            "Comma-separated list of policy set names to attach to the projects. "
            f"Defaults to: {', '.join(DEFAULT_POLICY_SETS)}"
        ),
    )
    parser.add_argument(
        "--agent-pool",
        required=False,
        default=DEFAULT_AGENT_POOL,
        help=(
            f"Agent pool name to grant the projects access to. "
            f"Defaults to: {DEFAULT_AGENT_POOL}"
        ),
    )
    args = parser.parse_args()

    org = os.getenv("TFE_ORGANIZATION")
    if not org:
        print("Error: TFE_ORGANIZATION environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    config = TFEConfig()
    tfe_client = TFEClient(config)
    http_transport = get_http(config)

    github_token = os.getenv("GITHUB_TOKEN")

    onboard(
        project_name=args.project_name,
        team_name=args.team_name,
        org=org,
        github_repository=args.github_repository,
        github_token=github_token,
        policy_sets=[p.strip() for p in args.policy_sets.split(",") if p.strip()],
        agent_pool=args.agent_pool,
        client=tfe_client,
        http=http_transport,
        skip_token_creation=args.skip_token_creation,
    )
