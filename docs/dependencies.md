# Dependencies and provenance

The bridge implementation was extracted from its author's private deployment code,
with personal configuration and operational data removed. It does not bundle code
from the adjacent projects listed in the README or from Buzz's desktop application.
The official ACP SDK and cryptographic libraries are installed as dependencies.

License metadata reviewed in the installed validation environment:

| Dependency | Reviewed version | Declared license |
| --- | --- | --- |
| agent-client-protocol | 0.12.1 | Apache-2.0 (installed LICENSE) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| coincurve | 21.0.0 | MIT OR Apache-2.0 |
| pydantic / pydantic_core | 2.14.1 / 2.50.1 | MIT |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.11 | BSD-3-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| annotated-types | 0.8.0 | MIT |

Dependencies retain their licenses and notices. Binary distributions may include
additional third-party code such as libsecp256k1; review the actual distributions
before vendoring or redistributing them. This project does not vendor those wheels.

Buzz is a separate Apache-2.0 project and is not included in this package. The
related Grok/Dot and Agent Babel projects declare MIT; Beeper's chatgpt-dots declares
AGPL-3.0. No code has been copied from them. A future reuse proposal must review the
specific revision and obligations rather than relying on this summary.
