#!/usr/bin/env python3
"""
HCP Terraform Project Offboarding Script

Removes all resources created by onboard.py, except for the teams (left intact).

Resources removed:
  1. Team token on {team_name}-cicd matching the github_repository description
  2. Projects removed from policy sets
  3. Variable sets ({project_name}-nprod, {project_name}-prod)
  4. Team-project access entries
  5. Projects ({project_name}-nprod, {project_name}-prod)

Usage:
  python offboard.py --project-name <name> --team-name <name> --github-repository <org/repo>
"""

import argparse
import os
import sys

import dotenv
from pytfe import TFEClient, TFEConfig

from tfe_helpers import (
    delete_projects,
    delete_team_tokens,
    delete_varsets,
    get_http,
    list_projects,
    list_teams,
    remove_policy_sets,
)

# Must match the DEFAULT_POLICY_SETS defined in onboard.py (or pass --policy-sets explicitly).
DEFAULT_POLICY_SETS: list[str] = [
    "default-policy",
]


def offboard(
    project_name: str,
    team_name: str,
    org: str,
    github_repository: str,
    policy_sets: list[str],
    client: TFEClient,
    http,
) -> None:
    print(f"\n=== Offboarding '{project_name}' from HCP Terraform org '{org}' ===\n")

    existing_teams = list_teams(http, org)
    team_ids = {
        role: existing_teams[f"{team_name}-{role}"]
        for role in ["reader", "contributor", "cicd"]
        if f"{team_name}-{role}" in existing_teams
    }

    print("Step 1: Revoking team tokens...")
    cicd_team_ids = {"cicd": team_ids["cicd"]} if "cicd" in team_ids else {}
    delete_team_tokens(http, org, cicd_team_ids, team_name, description=github_repository)

    print("\nStep 2: Removing projects from policy sets...")
    existing_projects = list_projects(client, org)
    project_ids = {
        env: existing_projects[f"{project_name}-{env}"]
        for env in ["nprod", "prod"]
        if f"{project_name}-{env}" in existing_projects
    }
    if project_ids:
        remove_policy_sets(client, org, project_ids, policy_sets)
    else:
        print("  [skip] No projects found to remove from policy sets")

    print("\nStep 3: Deleting variable sets...")
    delete_varsets(client, org, project_name)

    print("\nStep 4: Deleting projects (and their team access)...")
    delete_projects(http, client, org, project_name)

    print(f"\n=== Offboarding complete! ===")
    print(f"    Teams ({team_name}-reader, {team_name}-contributor, {team_name}-cicd) were left intact.\n")


if __name__ == "__main__":
    dotenv.load_dotenv()

    parser = argparse.ArgumentParser(
        description="Offboard a project from HCP Terraform (teams are preserved)",
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Project name used during onboarding (e.g. 'myapp'). Projects named '{name}-nprod' and '{name}-prod' will be removed.",
    )
    parser.add_argument(
        "--team-name",
        required=True,
        help="Team name used during onboarding (e.g. 'myapp'). Used to look up teams and revoke the cicd token.",
    )
    parser.add_argument(
        "--github-repository",
        required=True,
        help="GitHub repository used during onboarding (e.g. 'my-org/my-repo'). Used to identify which cicd team token to revoke.",
    )
    parser.add_argument(
        "--policy-sets",
        required=False,
        default=",".join(DEFAULT_POLICY_SETS),
        help=(
            "Comma-separated list of policy set names to detach from the projects. "
            f"Defaults to: {', '.join(DEFAULT_POLICY_SETS)}"
        ),
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

    policy_set_list = [p.strip() for p in args.policy_sets.split(",") if p.strip()]

    if not args.yes:
        print(f"\nThis will delete the following resources in org '{org}':")
        print(f"  Team tokens   : token with description '{args.github_repository}' on team '{args.team_name}-cicd'")
        print(f"  Policy sets   : detach '{', '.join(policy_set_list)}' from {args.project_name}-nprod, {args.project_name}-prod")
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
        project_name=args.project_name,
        team_name=args.team_name,
        org=org,
        github_repository=args.github_repository,
        policy_sets=policy_set_list,
        client=tfe_client,
        http=http_transport,
    )
