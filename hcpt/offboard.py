#!/usr/bin/env python3
"""
HCP Terraform Project Offboarding Script

Steps:
  1. Check projects have no workspaces (aborts if any exist)
  2. Delete projects ({project_name}-nprod, {project_name}-prod) and their team-project access entries
  3. Delete teams ({team_name}-reader, {team_name}-contributor, {team_name}-cicd)

Environment variables:
  TFE_TOKEN         HCP Terraform API token (required)
  TFE_ORGANIZATION  HCP Terraform organisation name (required)
  TFE_HOSTNAME      HCP Terraform hostname (optional, defaults to app.terraform.io)

Usage:
  python offboard.py --project-name <name> --team-name <name>
"""

import argparse
import os
import sys

import dotenv
from pytfe import TFEClient, TFEConfig

from tfe_helpers import (
    delete_projects,
    delete_teams,
    delete_varsets,
    get_http,
    list_project_workspaces,
    list_projects,
)


def offboard(
    project_name: str,
    team_name: str,
    org: str,
    client: TFEClient,
    http,
) -> None:
    print(f"\n=== Offboarding '{project_name}' from HCP Terraform org ===\n")

    print("Step 1: Checking for existing workspaces...")
    existing_projects = list_projects(client, org)
    project_ids = {
        env: existing_projects[f"{project_name}-{env}"]
        for env in ["nprod", "prod"]
        if f"{project_name}-{env}" in existing_projects
    }

    projects_with_workspaces: dict[str, list[str]] = {}
    for env, pid in project_ids.items():
        workspaces = list_project_workspaces(http, org, pid)
        if workspaces:
            projects_with_workspaces[f"{project_name}-{env}"] = workspaces

    if projects_with_workspaces:
        print("  [error] The following projects still have workspaces — remove them before offboarding:")
        for proj, ws_names in projects_with_workspaces.items():
            for name in ws_names:
                print(f"    {proj}: {name}")
        sys.exit(1)

    print("  [ok]   No workspaces found — safe to proceed")

    print("\nStep 2: Deleting variable sets...")
    delete_varsets(client, org, project_name)

    print("\nStep 3: Deleting projects...")
    delete_projects(http, client, org, project_name)

    print("\nStep 4: Deleting teams...")
    delete_teams(http, org, team_name)

    print(f"\n=== Offboarding complete! ===\n")


if __name__ == "__main__":
    dotenv.load_dotenv(override=True)

    parser = argparse.ArgumentParser(
        description="Offboard a project from HCP Terraform",
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Project name used during onboarding (e.g. 'myapp'). Projects named '{name}-nprod' and '{name}-prod' will be removed.",
    )
    parser.add_argument(
        "--team-name",
        required=True,
        help="Team name used during onboarding (e.g. 'myapp'). Teams named '{name}-reader', '{name}-contributor', and '{name}-cicd' will be deleted.",
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
        print(f"\nThis will delete the following resources in org '{org}':")
        print(f"  Variable sets : {args.project_name}-nprod, {args.project_name}-prod")
        print(f"  Projects      : {args.project_name}-nprod, {args.project_name}-prod")
        print(f"  Team access   : all entries for the above projects")
        print(f"  Teams         : {args.team_name}-nprd-*/prod-* (reader, contributor, cicd)")
        print()
        confirm = input("Continue? [y/N] ").strip()
        if confirm.lower() != "y":
            print("Aborted.")
            sys.exit(0)

    config = TFEConfig()
    tfe_client = TFEClient(config)
    http_transport = get_http(config)

    offboard(
        project_name=args.project_name,
        team_name=args.team_name,
        org=org,
        client=tfe_client,
        http=http_transport,
    )
