# Contributing

English or Spanish are both fine / Puedes escribir en español.

- **Questions and ideas** → [Discussions](https://github.com/ma-ochoa/rf_devices/discussions).
- **Bugs** → open an issue with the *Bug report* form and attach the Diagnostics file.
- **New remotes or hardware** → use the *New device or hardware* form. The maintainer usually does not
  have your hardware, so captures (panel export, `rtl_433 -F json`, ESPHome `dump: raw`) and the JSON from
  the panel's **Diagnostics** button are what make support possible.
- **Pull requests** → branch from `main` (or `labs` for experimental hardware), add tests, run
  `pytest` and `ruff` (commands in the README / CI), and update `CHANGELOG.md`. Keep personal data
  (IPs, tokens, your entity names) out of code and test fixtures.
