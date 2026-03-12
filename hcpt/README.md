# HCP Terraform Project Onboarding

Python scripts for onboarding and offboarding projects in HCP Terraform. Given a project name and team name, the onboarding script provisions a consistent set of teams, projects, team permissions, variable sets, and policy set assignments.

## What it provisions

| Resource | Names created |
|---|---|
| Teams | `{team_name}-nprd-reader`, `{team_name}-nprd-contrib`, `{team_name}-nprd-cicd`, `{team_name}-prod-reader`, `{team_name}-prod-contrib`, `{team_name}-prod-cicd` |
| Projects | `{project_name}-nprd`, `{project_name}-prod` (execution mode: `agent`, default agent pool set) |
| Team access (per project) | see [Team access](#team-access) below |
| Variable sets | `{project_name}-nprd`, `{project_name}-prod` (assigned to their project) |
| Policy sets | Projects attached to each policy set in `--policy-sets` |

All teams are created with no organisation-level access — permissions are managed at the project level. The script is fully idempotent — re-running it skips resources that already exist.

### Team access

Each env-scoped team is granted access only to its matching project (`-nprd-*` teams → `{project_name}-nprd`, `-prod-*` teams → `{project_name}-prod`):

| Team | Access type | Permissions |
|---|---|---|
| `{team_name}-{env}-reader` | `read` | Read-only access to the project |
| `{team_name}-{env}-contrib` | `custom` | Runs: `plan` only. Variables: `read`. No workspace, state, or variable-set management. |
| `{team_name}-{env}-cicd` | `custom` | Create workspaces: ✓ · Runs: `apply` · Sentinel mocks: `read` · Variables: `read/write` · State versions: `read-outputs` |

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
```

## Onboarding

```bash
python onboard.py --project-name <name> --team-name <name>
```

| Argument | Required | Description |
|---|---|---|
| `--project-name` | Yes | Prefix for projects (`{name}-nprd`, `{name}-prod`) and variable sets |
| `--team-name` | Yes | Prefix for teams (`{name}-nprd-*`, `{name}-prod-*`) |
| `--policy-sets` | No | Comma-separated policy set names to attach. Defaults to `DEFAULT_POLICY_SETS` in `onboard.py` |
| `--agent-pool` | No | Agent pool name to set as the default for new projects (execution mode: `agent`). Defaults to `DEFAULT_AGENT_POOL` in `onboard.py` |

**Example**

```
$ python onboard.py --project-name myapp --team-name platform

=== Onboarding 'myapp' into HCP Terraform org 'my-org' ===

Step 1: Ensuring teams exist...
  [ok]   Created team 'platform-nprd-reader' (id=team-abc123)
  [ok]   Created team 'platform-nprd-contrib' (id=team-def456)
  [ok]   Created team 'platform-nprd-cicd' (id=team-ghi789)
  [ok]   Created team 'platform-prod-reader' (id=team-jkl012)
  [ok]   Created team 'platform-prod-contrib' (id=team-mno345)
  [ok]   Created team 'platform-prod-cicd' (id=team-pqr678)

Step 2: Ensuring projects exist...
  [ok]   Created project 'myapp-nprd' (id=prj-abc123)
  [ok]   Created project 'myapp-prod' (id=prj-def456)

Step 3: Assigning team access to projects...
  [ok]   Granted 'read' access to team 'platform-nprd-reader' on project 'myapp-nprd'
  [ok]   Granted 'custom' access to team 'platform-nprd-contrib' on project 'myapp-nprd'
  [ok]   Granted 'custom' access to team 'platform-nprd-cicd' on project 'myapp-nprd'
  [ok]   Granted 'read' access to team 'platform-prod-reader' on project 'myapp-prod'
  ...

Step 4: Creating and assigning variable sets...
  [ok]   Created variable set 'myapp-nprd' (id=varset-abc123)
  [ok]   Assigned variable set 'myapp-nprd' to project 'myapp-nprd'
  [ok]   Created variable set 'myapp-prod' (id=varset-def456)
  [ok]   Assigned variable set 'myapp-prod' to project 'myapp-prod'

Step 5: Attaching policy sets to projects...
  [ok]   Attached policy set 'default-policy' to projects 'nprd', 'prod'

=== Onboarding complete! ===
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
  --policy-sets "default-policy,compliance-policy"
```

## Offboarding

Deletes the variable sets, projects, and teams created by `onboard.py`.

```bash
python offboard.py --project-name <name> --team-name <name>
```

| Argument | Required | Description |
|---|---|---|
| `--project-name` | Yes | Project name prefix used during onboarding |
| `--team-name` | Yes | Team name prefix used during onboarding |
| `--yes` | No | Skip the confirmation prompt |

Offboarding tears down resources in this order:
1. Check that both projects have no workspaces (aborts if any exist)
2. Delete variable sets (`{project_name}-nprd`, `{project_name}-prod`)
3. Remove team-project access entries and delete projects (`{project_name}-nprd`, `{project_name}-prod`)
4. Delete teams (`{team_name}-nprd-reader/contrib/cicd`, `{team_name}-prod-reader/contrib/cicd`)

```bash
python offboard.py --project-name myapp --team-name platform

# Skip confirmation
python offboard.py --project-name myapp --team-name platform --yes
```

## Project structure

```
hcpt/
├── onboard.py          # Onboarding entrypoint
├── offboard.py         # Offboarding entrypoint
├── tfe_helpers.py      # Shared helper functions
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

| Secret | Used by | Description |
|---|---|---|
| `TFE_TOKEN` | both | HCP Terraform API token |
| `TFE_ORGANIZATION` | both | HCP Terraform organisation name |
| `TFE_HOSTNAME` | both | Optional — defaults to `app.terraform.io` |

**Workflow inputs:**

| Input | Onboard | Offboard | Description |
|---|---|---|---|
| `project_name` | required | required | Project name prefix |
| `team_name` | required | required | Team name prefix |
| `policy_sets` | optional | — | Comma-separated policy set names (blank = defaults) |

The offboarding workflow passes `--yes` automatically to skip the interactive confirmation prompt.

### Triggering via the GitHub API

Workflows can also be triggered programmatically using the [`workflow_dispatch` REST API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event):

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR_GITHUB_TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/<owner>/<repo>/actions/workflows/onboard.yml/dispatches \
  -d '{
    "ref": "main",
    "inputs": {
      "project_name": "myapp",
      "team_name": "platform",
      "policy_sets": ""
    }
  }'
```

Replace `<owner>/<repo>` with the repository hosting these workflows. A `204 No Content` response indicates the workflow was queued successfully. Use the [list workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository) to check status.

## Makefile targets

| Target | Description |
|---|---|
| `make install` | Create `.venv` and install pinned dependencies |
| `make requirements` | Regenerate `requirements.txt` from `requirements.in` |

## Dependencies

- [pytfe](https://pypi.org/project/pytfe/) — official HCP Terraform Python client
- [python-dotenv](https://pypi.org/project/python-dotenv/) — `.env` file support

Teams, team tokens, and team-project access use the [HCP Terraform REST API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs) directly, as these endpoints are not yet covered by `pytfe`.

## Future Proofing

The scripts have additional flexibility if additional environments are added to the `DEFAULT_ENVIRONMENTS` list in `tfe_helpers.py`. This allows for easy expansion beyond the current `nprd` and `prod` environments without requiring significant changes to the onboarding and offboarding workflows.

This does require mapping between projects and teams who should have access to those projects. For example: if `DEFAULT_ENVIRONMENTS` is updated to include a new environment `"stage"`, then `_PROJECT_TO_TEAM_ENV` in `tfe_helpers.py` would also need a `"stage": "stage"` entry to ensure the correct teams are associated with the new project.
