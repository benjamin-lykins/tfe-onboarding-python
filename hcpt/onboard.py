#!/usr/bin/env python3
"""
HCP Terraform Project Onboarding Script

Given a project name and team name, this script will:
  1. Create six teams (if they don't exist): {team_name}-nprd-reader/contributor/cicd and {team_name}-prod-reader/contributor/cicd
  2. Create two projects: {project_name}-nprod, {project_name}-prod
     (with default execution mode set to 'agent' using the specified agent pool)
  3. Grant each team access to both projects (reader=read, contributor=custom/plan-only, cicd=custom/create+apply+variables)
  4. Create a variable set for each project and assign it
  5. Attach each project to the specified policy sets

Environment variables:
  TFE_TOKEN         HCP Terraform API token (required)
  TFE_ORGANIZATION  HCP Terraform organisation name (required)
  TFE_HOSTNAME      HCP Terraform hostname (optional, defaults to app.terraform.io)

Usage:
  python onboard.py --project-name <name> --team-name <name>
"""

import argparse
import os
import sys

import dotenv
from pytfe import TFEClient, TFEConfig

from tfe_helpers import (
    assign_policy_sets,
    assign_team_access,
    ensure_projects,
    ensure_teams,
    ensure_varsets,
    get_http,
)

# Edit this list to change the default policy sets applied to every onboarded project.
DEFAULT_POLICY_SETS: list[str] = [
    "default-policy",
]

# Edit this string to change the default agent pool applied to every onboarded project.
DEFAULT_AGENT_POOL: str = "default-agent-pool"

def onboard(
    project_name: str,
    team_name: str,
    org: str,
    policy_sets: list[str],
    agent_pool: str,
    client: TFEClient,
    http,
) -> None:
    print(f"\n=== Onboarding '{project_name}' into HCP Terraform org ===\n")

    print("Step 1: Ensuring teams exist...")
    team_ids = ensure_teams(http, org, team_name)

    print("\nStep 2: Ensuring projects exist...")
    project_ids = ensure_projects(http, client, org, project_name, agent_pool_name=agent_pool)

    print("\nStep 3: Assigning team access to projects...")
    assign_team_access(http, team_ids, project_ids, project_prefix=project_name, team_prefix=team_name)

    print("\nStep 4: Creating and assigning variable sets...")
    ensure_varsets(client, org, project_ids, project_name)

    print("\nStep 5: Attaching policy sets to projects...")
    assign_policy_sets(client, org, project_ids, policy_sets)

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
        help="Team name prefix (e.g. 'myapp'). Teams will be named '{name}-{env}-reader/contributor/cicd' and '{name}-prod-reader/contributor/cicd'.",
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

    onboard(
        project_name=args.project_name,
        team_name=args.team_name,
        org=org,
        policy_sets=[p.strip() for p in args.policy_sets.split(",") if p.strip()],
        agent_pool=args.agent_pool,
        client=tfe_client,
        http=http_transport,
    )
