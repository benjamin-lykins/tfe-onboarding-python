#!/usr/bin/env python3
"""
HCP Terraform Project Onboarding Script

Given a project name prefix, this script will:
  1. Create three teams (if they don't exist): {prefix}-contributor, {prefix}-reader, {prefix}-cicd
  2. Create a team token per team (description = github_repository)
  3. Create two projects: {prefix}-nprod, {prefix}-prod
  4. Grant each team access to both projects (reader=read, contributor=write, cicd=write)
  5. Create a variable set for each project and assign it

Usage:
  python onboard.py --project-name <name> --github-repository <org/repo>
"""

import argparse
import os
import sys

import dotenv
from pytfe import TFEClient, TFEConfig

from tfe_helpers import (
    assign_team_access,
    create_team_tokens,
    ensure_projects,
    ensure_teams,
    ensure_varsets,
    get_http,
)


def onboard(prefix: str, org: str, github_repository: str, client: TFEClient, http) -> None:
    print(f"\n=== Onboarding '{prefix}' into HCP Terraform org '{org}' ===\n")

    print("Step 1: Ensuring teams exist...")
    team_ids = ensure_teams(http, org, prefix)

    print("\nStep 2: Creating team tokens...")
    tokens = create_team_tokens(http, {"cicd": team_ids["cicd"]}, prefix, description=github_repository)
    print("\n  Store these token values — they will not be shown again:")
    for role, token_value in tokens.items():
        print(f"    {prefix}-{role}: {token_value}")

    print("\nStep 3: Ensuring projects exist...")
    project_ids = ensure_projects(client, org, prefix)

    print("\nStep 4: Assigning team access to projects...")
    assign_team_access(http, team_ids, project_ids, prefix)

    print("\nStep 5: Creating and assigning variable sets...")
    ensure_varsets(client, org, project_ids, prefix)

    print("\n=== Onboarding complete! ===\n")


if __name__ == "__main__":
    dotenv.load_dotenv()

    parser = argparse.ArgumentParser(
        description="Onboard a new project into HCP Terraform",
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Project name prefix (e.g. 'myapp'). Resources will be named '{prefix}-reader', '{prefix}-nprod', etc.",
    )
    parser.add_argument(
        "--github-repository",
        required=True,
        help="GitHub repository (e.g. 'my-org/my-repo'). Used as the team token description.",
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
        prefix=args.project_name,
        org=org,
        github_repository=args.github_repository,
        client=tfe_client,
        http=http_transport,
    )
