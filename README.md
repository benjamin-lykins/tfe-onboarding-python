# HCP Terraform Project Onboarding

Python scripts for onboarding and offboarding projects in HCP Terraform. Given a project name and team name, the onboarding script provisions a consistent set of teams, projects, team permissions, variable sets, and policy set assignments.

## What it provisions

| Resource | Names created |
|---|---|
| Teams | `{team_name}-reader`, `{team_name}-contributor`, `{team_name}-cicd` |
| Team token | `{team_name}-cicd` (expires in 1 year, description = GitHub repository) |
| GitHub secret | `TFE_TOKEN` written to the target GitHub repository |
| Projects | `{project_name}-nprod`, `{project_name}-prod` (execution mode: `agent`, default agent pool set) |
| Team access (per project) | see [Team access](#team-access) below |
| Variable sets | `{project_name}-nprod`, `{project_name}-prod` (assigned to their project) |
| Policy sets | Projects attached to each policy set in `--policy-sets` |

All teams are created with organisation-level read-only access (`read-workspaces`, `read-projects`). The script is fully idempotent — re-running it skips resources that already exist.

### Team access

Each team is granted project-level access with the following custom permissions:

| Team | Access type | Permissions |
|---|---|---|
| `{team_name}-reader` | `read` | Read-only access to the project |
| `{team_name}-contributor` | `custom` | Runs: `plan` only. No workspace, variable, or state access. |
| `{team_name}-cicd` | `custom` | Create workspaces: ✓ · Runs: `apply` · Variables: `read/write` · State versions: `read-outputs` |

## Prerequisites

- Python 3.11+
- An HCP Terraform organisation
- An API token with permission to manage teams, projects, variable sets, and policy sets
- `make` (Windows: install via [Git for Windows](https://gitforwindows.org/), [Chocolatey](https://chocolatey.org/) `choco install make`, or [WSL](https://learn.microsoft.com/en-us/windows/wsl/))

## Setup

**1. Clone and install dependencies**

```bash
make install
```

Activate the virtual environment:

| Platform | Shell | Command |
|---|---|---|
| macOS / Linux | bash/zsh | `source .venv/bin/activate` |
| Windows | PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows | CMD | `.venv\Scripts\activate.bat` |
| Windows | Git Bash | `source .venv/Scripts/activate` |

**2. Configure environment**

```bash
cp .env.example .env
```

```ini
TFE_TOKEN=your-token-here
TFE_ORGANIZATION=your-org-name

# Optional — defaults to app.terraform.io
# TFE_HOSTNAME=app.terraform.io

# GitHub PAT or fine-grained token with "Secrets: Read and write" on the target repo.
# Required to write/delete TFE_CICD_TOKEN on the GitHub repository during onboarding/offboarding.
# Fine-grained token (recommended): Settings → Developer settings → Personal access tokens → Fine-grained tokens
#   Permissions: Secrets → Read and write
# Classic token: requires the repo scope
GITHUB_TOKEN=your-github-pat-here
```

## Onboarding

```bash
python onboard.py --project-name <name> --team-name <name> --github-repository <org/repo>
```

| Argument | Required | Description |
|---|---|---|
| `--project-name` | Yes | Prefix for projects (`{name}-nprod`, `{name}-prod`) and variable sets |
| `--team-name` | Yes | Prefix for teams (`{name}-reader`, `{name}-contributor`, `{name}-cicd`) |
| `--github-repository` | Yes | GitHub repo (e.g. `my-org/my-repo`). Used as the cicd team token description |
| `--policy-sets` | No | Comma-separated policy set names to attach. Defaults to `DEFAULT_POLICY_SETS` in `onboard.py` |
| `--agent-pool` | No | Agent pool name to set as the default for new projects (execution mode: `agent`). Defaults to `DEFAULT_AGENT_POOL` in `onboard.py` |
| `--skip-token-creation` | No | Skip creating the cicd team token and writing `TFE_TOKEN` to the GitHub repository |

**Example**

```
$ python onboard.py --project-name myapp --team-name platform --github-repository my-org/my-repo

=== Onboarding 'myapp' into HCP Terraform org 'my-org' ===

Step 1: Ensuring teams exist...
  [ok]   Created team 'platform-reader' (id=team-abc123)
  [ok]   Created team 'platform-contributor' (id=team-def456)
  [ok]   Created team 'platform-cicd' (id=team-ghi789)

Step 2: Creating cicd team token...
  [ok]   Created token for team 'platform-cicd' (description: my-org/my-repo)

  Writing team tokens as GitHub Actions secrets on my-org/my-repo:
    [ok]   Set secret 'TFE_TOKEN'

Step 3: Ensuring projects exist...
  [ok]   Created project 'myapp-nprod' (id=prj-abc123)
  [ok]   Created project 'myapp-prod' (id=prj-def456)

Step 4: Assigning team access to projects...
  [ok]   Granted 'read' access to team 'platform-reader' on project 'myapp-nprod'
  [ok]   Granted 'custom' access to team 'platform-contributor' on project 'myapp-nprod'
  [ok]   Granted 'custom' access to team 'platform-cicd' on project 'myapp-nprod'
  ...

Step 5: Creating and assigning variable sets...
  [ok]   Created variable set 'myapp-nprod' (id=varset-abc123)
  [ok]   Assigned variable set 'myapp-nprod' to project 'myapp-nprod'
  ...

Step 6: Attaching policy sets to projects...
  [ok]   Attached policy set 'default-policy' to projects 'nprod', 'prod'

=== Onboarding complete! ===
```

Use `--skip-token-creation` to skip Step 2 entirely — useful when re-running onboarding on an existing project where the token was already created, or when the token and GitHub secret are managed separately:

```bash
python onboard.py --project-name myapp --team-name platform \
  --github-repository my-org/my-repo \
  --skip-token-creation
```

### Default policy sets

Edit `DEFAULT_POLICY_SETS` at the top of `onboard.py` to change which policy sets are applied to every onboarded project:

```python
DEFAULT_POLICY_SETS: list[str] = [
    "default-policy",
    "security-policy",
]
```

Override at runtime with `--policy-sets`:

```bash
python onboard.py --project-name myapp --team-name platform \
  --github-repository my-org/my-repo \
  --policy-sets "default-policy,compliance-policy"
```

## Offboarding

Removes all resources created by `onboard.py`. Teams are **not** deleted.

```bash
python offboard.py --project-name <name> --team-name <name> --github-repository <org/repo>
```

| Argument | Required | Description |
|---|---|---|
| `--project-name` | Yes | Project name prefix used during onboarding |
| `--team-name` | Yes | Team name prefix used during onboarding |
| `--github-repository` | Yes | GitHub repo used during onboarding — identifies the cicd token to revoke |
| `--policy-sets` | No | Comma-separated policy set names to detach. Defaults to `DEFAULT_POLICY_SETS` in `offboard.py` |
| `--yes` | No | Skip the confirmation prompt |

Offboarding tears down resources in this order:
1. Check that both projects have no workspaces (aborts if any exist)
2. Revoke `{team_name}-cicd` token matching the GitHub repository description
3. Delete the `TFE_TOKEN` Actions secret from the GitHub repository
4. Detach projects from policy sets
5. Delete variable sets
6. Remove team-project access entries and delete projects

```bash
python offboard.py --project-name myapp --team-name platform \
  --github-repository my-org/my-repo

# Skip confirmation
python offboard.py --project-name myapp --team-name platform \
  --github-repository my-org/my-repo --yes
```

## Project structure

```
.
├── onboard.py          # Onboarding entrypoint
├── offboard.py         # Offboarding entrypoint (preserves teams)
├── tfe_helpers.py      # Shared helper functions
├── examples/
│   ├── demo.sh         # Interactive demo shell script
│   └── cleanup.py      # Full teardown including teams
├── .github/
│   └── workflows/
│       ├── onboard.yml     # GitHub Actions workflow for onboarding
│       └── offboard.yml    # GitHub Actions workflow for offboarding
├── .env.example        # Environment variable template
├── requirements.in     # Direct dependencies
├── requirements.txt    # Pinned lockfile (auto-generated)
└── Makefile            # Developer tasks
```

## GitHub Actions

Both workflows are triggered manually via **Actions → Run workflow** in the GitHub UI.

**Required repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Description |
|---|---|
| `TFE_TOKEN` | HCP Terraform API token |
| `TFE_ORGANIZATION` | HCP Terraform organisation name |
| `TFE_HOSTNAME` | Optional — defaults to `app.terraform.io` |
| `GH_PAT` | GitHub PAT with `Secrets: Read and write` on target repositories. Used to write/delete `TFE_CICD_TOKEN` on the onboarded repository. Fine-grained token recommended. |

**Workflow inputs:**

| Input | Onboard | Offboard | Description |
|---|---|---|---|
| `project_name` | required | required | Project name prefix |
| `team_name` | required | required | Team name prefix |
| `github_repository` | required | required | GitHub repo (e.g. `my-org/my-repo`) |
| `policy_sets` | optional | optional | Comma-separated policy set names (blank = defaults) |

The offboarding workflow passes `--yes` automatically to skip the interactive confirmation prompt.

## Makefile targets

| Target | Description |
|---|---|
| `make install` | Create `.venv` and install pinned dependencies |
| `make requirements` | Regenerate `requirements.txt` from `requirements.in` |

## Dependencies

- [pytfe](https://pypi.org/project/pytfe/) — official HCP Terraform Python client
- [python-dotenv](https://pypi.org/project/python-dotenv/) — `.env` file support
- [pynacl](https://pypi.org/project/PyNaCl/) — NaCl encryption required by the GitHub Secrets API

Teams, team tokens, and team-project access use the [HCP Terraform REST API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs) directly, as these endpoints are not yet covered by `pytfe`.

GitHub secret management uses the [GitHub REST API](https://docs.github.com/en/rest/actions/secrets) directly. Secrets must be encrypted with the repository's NaCl public key before being written.
