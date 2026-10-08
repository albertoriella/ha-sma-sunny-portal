# Release checklist

Use this checklist for every public release. Commands assume the repository is
`albertoriella/ha-sma-sunny-portal` and the local checkout is clean.

## 1. Prepare the release commit

- Set the SemVer version in `custom_components/sma_sunny_portal/manifest.json`.
- Add the same version and date to `CHANGELOG.md`.
- Confirm `hacs.json` contains only currently supported HACS keys.
- Run the complete Python and JavaScript validation suite.
- Run Gitleaks against `--all` Git history, not only the working tree.
- Review the diff and commit it without including local archives or reports.

## 2. Prepare GitHub

- Keep Issues enabled.
- Enable private vulnerability reporting under **Settings → Security**.
- Add repository topics such as `home-assistant`, `hacs`, `sma`,
  `sunny-portal`, `solar-forecast`, and `photovoltaic`.
- Confirm the repository description is concise and the default branch is
  `main`.
- Make the repository public only after the privacy and secret scans are clean.

HACS requires a public GitHub repository with a description, topics, README,
root `hacs.json`, supported manifest, issues, and brand assets.

## 3. Validate the public commit

- Wait for Tests, Hassfest, HACS, and Secret scan to pass on `main`.
- Inspect the public file tree once more for identifiers, generated databases,
  captures, archives, and local configuration.
- Install the default branch once as a HACS custom repository in a test Home
  Assistant instance.

Do not ignore a HACS validation check when preparing for inclusion in the
default catalogue.

## 4. Publish the release

- Create an annotated tag matching the manifest version, prefixed with `v`.
- Create a full GitHub Release from that tag; a tag alone is not sufficient for
  HACS release discovery or default-catalogue submission.
- Use the matching `CHANGELOG.md` section as release notes.
- Test a clean HACS install and an upgrade from the previous release.

## 5. After release

- Verify the installed integration reports the expected version.
- Verify the Lovelace resource URL and card load after a restart.
- Monitor only redacted issue reports; ask reporters to remove secrets
  immediately if they post any.
- Submit to the HACS default catalogue only after the custom-repository release
  has received enough real-world testing and both required actions pass.
