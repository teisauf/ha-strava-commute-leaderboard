# Repository conventions for GitHub Copilot

This is a Home Assistant custom integration distributed via HACS.

## Commit messages and PR titles

Use [Conventional Commits](https://www.conventionalcommits.org/) prefixes. They drive automatic versioning and changelog generation via [release-please](https://github.com/googleapis/release-please).

| Prefix | Triggers | Use for |
|---|---|---|
| `feat:` | **minor** bump | new user-visible capability |
| `fix:` | **patch** bump | bug fix |
| `feat!:` / `fix!:` (or `BREAKING CHANGE:` in body) | **major** bump | breaking change |
| `chore:`, `docs:`, `refactor:`, `test:`, `ci:`, `style:`, `build:`, `perf:` | no bump | internal changes; appear under "Other changes" in CHANGELOG |

Format: `<prefix>: <imperative summary>` — lowercase summary, no trailing period.

Examples:
- `feat: add live diesel price fetching from Q8 API`
- `fix: fall back to manual price when both Q8 and Shell are unreachable`
- `chore: bump pytest to 8.x`
- `feat!: drop Python 3.11 support`

**Set the PR title with the same prefix.** When a PR is squash-merged, the PR title becomes the commit message on `main` — that's what release-please reads.

## Things NOT to do

- Don't manually edit `version` in `custom_components/strava_commute_leaderboard/manifest.json` — release-please updates it.
- Don't manually create git tags or GitHub releases — release-please tags `v0.2.0` and writes the release when its Release PR is merged.

## CI

PRs and pushes to `main` run `pytest`, `hassfest`, and the HACS validator. See `.github/workflows/tests.yml`.

## Testing

Tests in `tests/` import helpers directly (e.g. `from fuel_price import …`) rather than through the `custom_components.strava_commute_leaderboard` package, because the package init imports `homeassistant` which isn't installed in plain CI. `conftest.py` adds the integration directory to `sys.path` to make this work. New pure helpers worth testing should live in standalone modules.
