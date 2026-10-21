# Contributing

Thanks for helping make existing assistants work reliably in Buzz. Useful first
contributions include installation reports, protocol compatibility fixtures,
clearer diagnostics, tests for failure recovery, and documentation fixes.

Open an issue before proposing a new provider or changing authentication, storage,
publication, or cancellation semantics. Include official protocol evidence and
describe the expected behavior. Do not paste real credentials or conversations.

Keep changes small and explain the user-visible problem, the resulting behavior,
and the checks you ran. Add tests for meaningful behavior and failure boundaries;
avoid tests that only duplicate implementation details. Document unsupported
features honestly, including account prerequisites and untested platforms.

Follow [development](docs/development.md) and [AGENTS.md](AGENTS.md). New providers
must preserve the common broker's validation and single-publisher design. Do not
add undocumented session scraping or automatic permission expansion as a fallback.

Third-party contributions must identify their source and license. Do not copy code
from related projects without reviewing compatibility and required notices.
