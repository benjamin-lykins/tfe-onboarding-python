#!/usr/bin/env python3
"""
HCP Terraform Project Onboarding Script

Given a project name and team name, this script will:
  1. Create three teams (if they don't exist): {team_name}-contributor, {team_name}-reader, {team_name}-cicd
  2. Create a team token for {team_name}-cicd (description = github_repository)
  3. Create two projects: {project_name}-nprod, {project_name}-prod
  4. Grant each team access to both projects (reader=read, contributor=write, cicd=write)
  5. Create a variable set for each project and assign it
  6. Attach each project to the specified policy sets

Usage:
  python onboard.py --project-name <name> --team-name <name> --github-repository <org/repo>
"""

import argparse
import os
import sys

import dotenv
from pytfe import TFEClient, TFEConfig

from tfe_helpers import (
    assign_policy_sets,
    assign_team_access,
    create_team_tokens,
    ensure_projects,
    ensure_teams,
    ensure_varsets,
    get_http,
)

# Edit this list to change the default policy sets applied to every onboarded project.
DEFAULT_POLICY_SETS: list[str] = [
    "default-policy",
]

# Edit this list to change the default agent pools applied to every onboarded project.
DEFAULT_AGENT_POOLS: list[str] = [
    "default-agent-pool",
]


def onboard(
    project_name: str,
    team_name: str,
    org: str,
    github_repository: str,
    policy_sets: list[str],
    # agent_pools: list[str], 
    client: TFEClient,
    http,
) -> None:
    print(f"\n=== Onboarding '{project_name}' into HCP Terraform org '{org}' ===\n")

    print("Step 1: Ensuring teams exist...")
    team_ids = ensure_teams(http, org, team_name)

    print("\nStep 2: Creating team tokens...")
    tokens = create_team_tokens(http, org, {"cicd": team_ids["cicd"]}, team_name, description=github_repository)
    if tokens:
        print("\n  Store these token values — they will not be shown again:")
        for role, token_value in tokens.items():
            print(f"    {team_name}-{role}: {token_value}")

    print("\nStep 3: Ensuring projects exist...")
    project_ids = ensure_projects(client, org, project_name)

    print("\nStep 4: Assigning team access to projects...")
    assign_team_access(http, team_ids, project_ids, project_prefix=project_name, team_prefix=team_name)

    print("\nStep 5: Creating and assigning variable sets...")
    ensure_varsets(client, org, project_ids, project_name)

    print("\nStep 6: Attaching policy sets to projects...")
    assign_policy_sets(client, org, project_ids, policy_sets)

    print("\n=== Onboarding complete! ===\n")


if __name__ == "__main__":
    dotenv.load_dotenv()

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
    args = parser.parse_args()

    org = os.getenv("TFE_ORGANIZATION")
    if not org:
        print("Error: TFE_ORGANIZATION environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    config = TFEConfig()
    tfe_client = TFEClient(config)
    http_transport = get_http(config)

    onboard(
        project_name=args.project_name,
        team_name=args.team_name,
        org=org,
        github_repository=args.github_repository,
        policy_sets=[p.strip() for p in args.policy_sets.split(",") if p.strip()],
        client=tfe_client,
        http=http_transport,
    )
