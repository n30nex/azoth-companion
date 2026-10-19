# Security reports

For a suspected vulnerability, use GitHub's private vulnerability reporting when available. Otherwise open an issue that describes the affected component and how to contact you, without including exploit data, credentials or recordings.

Never attach real ledgers, HTTPS logs, TLS keys, `access.json`, browser cookies, raw game logs or personal menu templates to a public issue. A synthetic reproducer and redacted error text are preferable.

## Boundaries

- HTTP listeners bind only to loopback or a specific RFC1918 LAN address. They reject unexpected Host headers, cross-origin write requests and unauthenticated dashboard commands.
- The upload connector has its own token and cannot start or stop recordings. Its pairing endpoint is loopback-only and checks the expected extension identity and browser origin.
- The native recorder bridge binds to a random loopback port and requires a random bearer token.
- Packet steps are descriptions, not proof of packet capture. Uncertain marks remain uncertain. Original timestamps and ledgers are retained.
- Menu automation checks the installed executable, process creation time, current recording and calibrated screen regions. It does not automate gameplay or attempt to defeat server checks.
- Downloads for Python, the pip bootstrap wheel and the capture engine are hash-checked. Dependencies are retrieved from official Python/GitHub/PyPI hosts. Remaining supply-chain limits are described in NOTICE.md.

This is an unsigned, early community release. Checksums help detect altered or incomplete downloads; they are not code signing. Do not disable endpoint protection to run it. Account restrictions and anti-cheat disconnects are separate from the companion's local security controls.
