# HCP Terraform Project Onboarding

Python scripts for onboarding new projects into HCP Terraform. Given a project name prefix, the onboarding script provisions a consistent set of teams, projects, team permissions, and variable sets.

## What it provisions

| Resource | Names created |
|---|---|
| Teams | `{prefix}-reader`, `{prefix}-contributor`, `{prefix}-cicd` |
| Projects | `{prefix}-nprod`, `{prefix}-prod` |
| Team access (per project) | reader → `read`, contributor → `write`, cicd → `write` |
| Variable sets | `{prefix}-nprod`, `{prefix}-prod` (assigned to their project) |

All teams are created with organisation-level read-only access (`read-workspaces`, `read-projects`). The script is fully idempotent — re-running it skips resources that already exist.

## Prerequisites

- Python 3.11+
- An HCP Terraform organisation
- An API token with permission to manage teams, projects, and variable sets

## Setup

**1. Clone and install dependencies**

```bash
make install
source .venv/bin/activate
```

**2. Configure environment**

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

```ini
TFE_TOKEN=your-token-here
TFE_ORGANIZATION=your-org-name

# Optional — defaults to app.terraform.io
# TFE_HOSTNAME=app.terraform.io
```

## Usage

```bash
python onboard.py --project-name <prefix>
```

**Example**

```
$ python onboard.py --project-name myapp

=== Onboarding 'myapp' into HCP Terraform org 'my-org' ===

Step 1: Ensuring teams exist...
  [ok]   Created team 'myapp-reader' (id=team-abc123)
  [ok]   Created team 'myapp-contributor' (id=team-def456)
  [ok]   Created team 'myapp-cicd' (id=team-ghi789)

Step 2: Ensuring projects exist...
  [ok]   Created project 'myapp-nprod' (id=prj-abc123)
  [ok]   Created project 'myapp-prod' (id=prj-def456)

Step 3: Assigning team access to projects...
  [ok]   Granted 'read' access to team 'myapp-reader' on project 'myapp-nprod'
  [ok]   Granted 'write' access to team 'myapp-contributor' on project 'myapp-nprod'
  ...

Step 4: Creating and assigning variable sets...
  [ok]   Created variable set 'myapp-nprod' (id=varset-abc123)
  [ok]   Assigned variable set 'myapp-nprod' to project 'myapp-nprod'
  ...

=== Onboarding complete! ===
```

## Examples

### Demo

Run a guided demo with a sample project name (defaults to `demo-app`):

```bash
./examples/demo.sh
# or specify a name
./examples/demo.sh myapp
```

### Cleanup

Remove all resources created for a given prefix:

```bash
python examples/cleanup.py --project-name myapp
```

Pass `--yes` to skip the confirmation prompt:

```bash
python examples/cleanup.py --project-name myapp --yes
```

Cleanup tears down resources in reverse order: variable sets → project team access → projects → teams.

## Project structure

```
.
├── onboard.py          # Main onboarding entrypoint
├── tfe_helpers.py      # Shared helper functions (teams, projects, varsets, HTTP)
├── examples/
│   ├── demo.sh         # Interactive demo shell script
│   └── cleanup.py      # Tears down all onboarded resources
├── requirements.in     # Direct dependencies
├── requirements.txt    # Pinned lockfile (auto-generated)
└── Makefile            # Developer tasks
```

## Makefile targets

| Target | Description |
|---|---|
| `make install` | Create `.venv` and install pinned dependencies |
| `make requirements` | Regenerate `requirements.txt` from `requirements.in` |

## Dependencies

- [pytfe](https://pypi.org/project/pytfe/) — official HCP Terraform Python client
- [python-dotenv](https://pypi.org/project/python-dotenv/) — `.env` file support

Team management and team-project access use the [HCP Terraform REST API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs) directly, as these endpoints are not yet covered by `pytfe`.
