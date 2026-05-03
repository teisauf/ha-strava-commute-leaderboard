# Repository conventions

This is a Home Assistant custom integration distributed via HACS.

## Commit messages and PR titles

Use [Conventional Commits](https://www.conventionalcommits.org/) prefixes. They drive automatic versioning and changelog generation via [release-please](https://github.com/googleapis/release-please).

| Prefix | Triggers | Use for |
|---|---|---|
| `feat:` | **minor** version bump | new user-visible capability |
| `fix:` | **patch** version bump | bug fix |
| `feat!:` / `fix!:` (or `BREAKING CHANGE:` in body) | **major** version bump | breaking change |
| `chore:`, `docs:`, `refactor:`, `test:`, `ci:`, `style:`, `build:`, `perf:` | no bump | internal changes; appear under "Other changes" in CHANGELOG |

Format: `<prefix>: <imperative summary>` — lowercase summary, no trailing period.

Examples:
- `feat: add live diesel price fetching from Q8 API`
- `fix: fall back to manual price when both Q8 and Shell are unreachable`
- `chore: bump pytest to 8.x`
- `feat!: drop Python 3.11 support`

**Set the PR title with the same prefix.** When a PR is squash-merged, the PR title becomes the commit message on `main` — that's what release-please reads.

## Things NOT to do

- Don't manually edit `version` in `custom_components/strava_commute_leaderboard/manifest.json`. release-please updates it via its Release PR.
- Don't manually create git tags (`v0.2.0` etc.). release-please tags when its Release PR is merged.
- Don't manually create GitHub releases in the UI.

## Release flow

1. Merge feature/fix PRs into `main` with conventional-commit titles.
2. release-please opens (or updates) a Release PR titled like `chore(main): release 0.2.0` containing the version bump and CHANGELOG entry.
3. Review and merge the Release PR when ready to ship.
4. release-please tags `v0.2.0`, creates the GitHub release, and HACS users see the update.

## CI

`.github/workflows/tests.yml` runs on every PR and push to `main`:
- `pytest` (Python 3.12) — tests in `tests/`, configured by `pytest.ini`.
- `hassfest` — Home Assistant manifest validation.
- `hacs/action` — HACS publisher pre-flight (brands check skipped, no custom icon).

## Testing notes

Tests in `tests/test_fuel_price.py` import the helper module directly (`from fuel_price import …`) rather than through the package, because `custom_components/strava_commute_leaderboard/__init__.py` imports `homeassistant`, which isn't installed in plain CI. `conftest.py` adds the integration's directory to `sys.path` to make this work. If you add new pure helpers worth testing, put them in standalone modules so they stay testable without booting Home Assistant.

## Key code locations

- `custom_components/strava_commute_leaderboard/coordinator.py` — `DataUpdateCoordinator`, daily refresh, fuel-price integration, money-saved calculation.
- `custom_components/strava_commute_leaderboard/fuel_price.py` — pure parsers + Q8/Shell fetcher for the Danish diesel listepris.
- `custom_components/strava_commute_leaderboard/sensor.py` — sensor entities; `money_saved` exposes the live price as attributes.
- `custom_components/strava_commute_leaderboard/config_flow.py` — OAuth + options form.
