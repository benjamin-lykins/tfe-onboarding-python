#!/usr/bin/env python3
"""
HCP Terraform Project Offboarding Script

Removes all resources created by onboard.py for a given prefix,
except for the teams themselves (which are left intact).

Resources removed:
  1. Team tokens matching the github_repository description
  2. Variable sets ({prefix}-nprod, {prefix}-prod)
  3. Team-project access entries
  4. Projects ({prefix}-nprod, {prefix}-prod)

Usage:
  python offboard.py --project-name <name> --github-repository <org/repo>
"""

import argparse
import os
import sys

import dotenv
from pytfe import TFEClient, TFEConfig

from tfe_helpers import (
    delete_projects,
    delete_team_tokens_by_description,
    delete_varsets,
    get_http,
    list_teams,
)


def offboard(prefix: str, org: str, github_repository: str, client: TFEClient, http) -> None:
    print(f"\n=== Offboarding '{prefix}' from HCP Terraform org '{org}' ===\n")

    existing_teams = list_teams(http, org)
    team_ids = {
        role: existing_teams[f"{prefix}-{role}"]
        for role in ["reader", "contributor", "cicd"]
        if f"{prefix}-{role}" in existing_teams
    }

    print("Step 1: Revoking team tokens...")
    cicd_team_ids = {"cicd": team_ids["cicd"]} if "cicd" in team_ids else {}
    delete_team_tokens_by_description(http, cicd_team_ids, prefix, description=github_repository)

    print("\nStep 2: Deleting variable sets...")
    delete_varsets(client, org, prefix)

    print("\nStep 3: Deleting projects (and their team access)...")
    delete_projects(http, client, org, prefix)

    print(f"\n=== Offboarding complete! ===")
    print(f"    Teams ({prefix}-reader, {prefix}-contributor, {prefix}-cicd) were left intact.\n")


if __name__ == "__main__":
    dotenv.load_dotenv()

    parser = argparse.ArgumentParser(
        description="Offboard a project from HCP Terraform (teams are preserved)",
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Project name prefix used during onboarding (e.g. 'myapp')",
    )
    parser.add_argument(
        "--github-repository",
        required=True,
        help="GitHub repository used during onboarding (e.g. 'my-org/my-repo'). Used to identify which team tokens to revoke.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    org = os.getenv("TFE_ORGANIZATION")
    if not org:
        print("Error: TFE_ORGANIZATION environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    if not args.yes:
        print(f"\nThis will delete the following resources for prefix '{args.project_name}' in org '{org}':")
        print(f"  Team tokens   : tokens with description '{args.github_repository}' on team '{args.project_name}-cicd'")
        print(f"  Variable sets : {args.project_name}-nprod, {args.project_name}-prod")
        print(f"  Projects      : {args.project_name}-nprod, {args.project_name}-prod")
        print(f"  Team access   : all entries for the above projects")
        print(f"\n  Teams will NOT be deleted.")
        print()
        confirm = input("Continue? [y/N] ").strip()
        if confirm.lower() != "y":
            print("Aborted.")
            sys.exit(0)

    config = TFEConfig()
    tfe_client = TFEClient(config)
    http_transport = get_http(config)

    offboard(
        prefix=args.project_name,
        org=org,
        github_repository=args.github_repository,
        client=tfe_client,
        http=http_transport,
    )
