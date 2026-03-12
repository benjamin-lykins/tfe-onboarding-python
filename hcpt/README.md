# HCP Terraform Project Onboarding

Python scripts for onboarding and offboarding projects in HCP Terraform. Given a project name and team name, the onboarding script provisions a consistent set of teams, projects, team permissions, variable sets, and policy set assignments.

## What it provisions

| Resource | Names created |
|---|---|
| Teams | `{team_name}-nprd-reader`, `{team_name}-nprd-contributor`, `{team_name}-nprd-cicd`, `{team_name}-prod-reader`, `{team_name}-prod-contributor`, `{team_name}-prod-cicd` |
| Team tokens | `{team_name}-nprd-cicd`, `{team_name}-prod-cicd` (expire in 1 year, description = GitHub repository) |
| Key Vault secrets | `TFE-TOKEN-NPRD`, `TFE-TOKEN-PROD` written to the specified Azure Key Vault |
| Projects | `{project_name}-nprd`, `{project_name}-prod` (execution mode: `agent`, default agent pool set) |
| Team access (per project) | see [Team access](#team-access) below |
| Variable sets | `{project_name}-nprd`, `{project_name}-prod` (assigned to their project) |
| Policy sets | Projects attached to each policy set in `--policy-sets` |

All teams are created with organisation-level read-only access (`read-workspaces`, `read-projects`). The script is fully idempotent — re-running it skips resources that already exist.

### Team access

Each env-scoped team is granted access only to its matching project (`-nprd-*` teams → `{project_name}-nprd`, `-prod-*` teams → `{project_name}-prod`):

| Team | Access type | Permissions |
|---|---|---|
| `{team_name}-{env}-reader` | `read` | Read-only access to the project |
| `{team_name}-{env}-contributor` | `custom` | Runs: `plan` only. No workspace, variable, or state access. |
| `{team_name}-{env}-cicd` | `custom` | Create workspaces: ✓ · Runs: `apply` · Variables: `read/write` · State versions: `read-outputs` |

## Prerequisites

- Python 3.11+
- An HCP Terraform organisation
- An API token with permission to manage teams, projects, variable sets, and policy sets
- `make` (Windows: install via [Git for Windows](https://gitforwindows.org/), [Chocolatey](https://chocolatey.org/) `choco install make`, or [WSL](https://learn.microsoft.com/en-us/windows/wsl/))
- Azure identity with `Key Vault Secrets Officer` (or `Key Vault Administrator`) role on the target Key Vault (required to write team tokens during onboarding)

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

# Azure credentials for Key Vault secret storage (used by DefaultAzureCredential).
# When running locally, `az login` is sufficient — no env vars needed.
# For CI/CD, set these for a service principal:
# AZURE_TENANT_ID=your-tenant-id
# AZURE_CLIENT_ID=your-client-id
# AZURE_CLIENT_SECRET=your-client-secret
```

## Onboarding

```bash
python onboard.py --project-name <name> --team-name <name> --github-repository <org/repo>
```

| Argument | Required | Description |
|---|---|---|
| `--project-name` | Yes | Prefix for projects (`{name}-nprd`, `{name}-prod`) and variable sets |
| `--team-name` | Yes | Prefix for teams (`{name}-nprd-*`, `{name}-prod-*`) |
| `--github-repository` | Yes | GitHub repo (e.g. `my-org/my-repo`). Used as the cicd team token description |
| `--keyvault-name` | No | Azure Key Vault name. If set, cicd tokens are stored as `TFE-TOKEN-NPRD` / `TFE-TOKEN-PROD` using `DefaultAzureCredential` |
| `--policy-sets` | No | Comma-separated policy set names to attach. Defaults to `DEFAULT_POLICY_SETS` in `onboard.py` |
| `--agent-pool` | No | Agent pool name to set as the default for new projects (execution mode: `agent`). Defaults to `DEFAULT_AGENT_POOL` in `onboard.py` |
| `--skip-token-creation` | No | Skip creating the cicd team tokens and Key Vault secret storage |

**Example**

```
$ python onboard.py --project-name myapp --team-name platform --github-repository my-org/my-repo --keyvault-name my-keyvault

=== Onboarding 'myapp' into HCP Terraform org 'my-org' ===

Step 1: Ensuring teams exist...
  [ok]   Created team 'platform-nprd-reader' (id=team-abc123)
  [ok]   Created team 'platform-nprd-contributor' (id=team-def456)
  [ok]   Created team 'platform-nprd-cicd' (id=team-ghi789)
  [ok]   Created team 'platform-prod-reader' (id=team-jkl012)
  [ok]   Created team 'platform-prod-contributor' (id=team-mno345)
  [ok]   Created team 'platform-prod-cicd' (id=team-pqr678)

Step 2: Creating cicd team tokens...
  Writing team tokens to Key Vault 'my-keyvault':
    [ok]   Set secret 'TFE-TOKEN-NPRD'
    [ok]   Set secret 'TFE-TOKEN-PROD'

Step 3: Ensuring projects exist...
  [ok]   Created project 'myapp-nprd' (id=prj-abc123)
  [ok]   Created project 'myapp-prod' (id=prj-def456)

Step 4: Assigning team access to projects...
  [ok]   Granted 'read' access to team 'platform-reader' on project 'myapp-nprd'
  [ok]   Granted 'custom' access to team 'platform-contributor' on project 'myapp-nprd'
  [ok]   Granted 'custom' access to team 'platform-cicd' on project 'myapp-nprd'
  ...

Step 5: Creating and assigning variable sets...
  [ok]   Created variable set 'myapp-nprd' (id=varset-abc123)
  [ok]   Assigned variable set 'myapp-nprd' to project 'myapp-nprd'
  ...

Step 6: Attaching policy sets to projects...
  [ok]   Attached policy set 'default-policy' to projects 'nprd', 'prod'

=== Onboarding complete! ===
```

Use `--skip-token-creation` to skip Step 2 entirely — useful when re-running onboarding on an existing project where the tokens were already created:

```bash
python onboard.py --project-name myapp --team-name platform \
  --github-repository my-org/my-repo \
  --keyvault-name my-keyvault \
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

Deletes the projects and teams created by `onboard.py`.

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
4. Delete teams (`{team_name}-nprd-reader/contributor/cicd`, `{team_name}-prod-reader/contributor/cicd`)

```bash
python offboard.py --project-name myapp --team-name platform

# Skip confirmation
python offboard.py --project-name myapp --team-name platform --yes
```

## Project structure

```
.
├── onboard.py          # Onboarding entrypoint
├── offboard.py         # Offboarding entrypoint
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

| Secret | Used by | Description |
|---|---|---|
| `TFE_TOKEN` | both | HCP Terraform API token |
| `TFE_ORGANIZATION` | both | HCP Terraform organisation name |
| `TFE_HOSTNAME` | both | Optional — defaults to `app.terraform.io` |
| `AZURE_TENANT_ID` | onboard only | Azure tenant ID for service principal auth (not needed with managed identity) |
| `AZURE_CLIENT_ID` | onboard only | Azure client ID for service principal auth |
| `AZURE_CLIENT_SECRET` | onboard only | Azure client secret for service principal auth |

**Workflow inputs:**

| Input | Onboard | Offboard | Description |
|---|---|---|---|
| `project_name` | required | required | Project name prefix |
| `team_name` | required | required | Team name prefix |
| `github_repository` | required | — | GitHub repo (e.g. `my-org/my-repo`) |
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
      "github_repository": "my-org/my-repo",
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
- [pynacl](https://pypi.org/project/PyNaCl/) — NaCl encryption required by the GitHub Secrets API
- [azure-identity](https://pypi.org/project/azure-identity/) — `DefaultAzureCredential` for Key Vault authentication
- [azure-keyvault-secrets](https://pypi.org/project/azure-keyvault-secrets/) — Azure Key Vault secret management

Teams, team tokens, and team-project access use the [HCP Terraform REST API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs) directly, as these endpoints are not yet covered by `pytfe`.

Team tokens are stored in Azure Key Vault using `DefaultAzureCredential`, which supports `az login` locally and environment variables or managed identity in CI/CD.
