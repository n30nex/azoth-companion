# Components and provenance

Azoth Companion code and supporting scripts: Copyright 2026 n30nex, licensed AGPL-3.0-only.

`recorder/` is based on Azoth Capture v0.2.0, commit `186bf6888e5594869c7f54fda5f673a7d5ecabcb`, by tempesTT / KyzaBOY. Its MIT license is preserved in `recorder/LICENSE`; the integration changes in that component are also MIT. Its original third-party license texts and font notices remain in the source. The public release includes the compiled Go dependency license texts.

Changes to the recorder include a loopback control bridge, dashboard startup, DX11 launch arguments, flushed recovery journals, waiting for the writer before export, export-error reporting and a PowerShell runtime installer with locked downloads. Capture hooks and packet interception logic remain the upstream implementation.

The runtime installer downloads Aeternum-World by Coldzer0 at commit `820156dbc44c86c9436af81aa0dba72e94cb636b` from https://github.com/Coldzer0/Aeternum-World (AGPL-3.0). It extracts the capture tools and license, not game assets or recordings. The engine is not shipped inside this repository or the release ZIP. Its DTLS decoder is imported by the AGPL companion for validation. The generated patched ledger script is an AGPL derivative; corresponding source is the pinned upstream script together with `recorder/internal/capture/agent.go`.

Additional downloads:

| Component | License/source |
| --- | --- |
| Python 3.12.10 embeddable | Python Software Foundation; python.org |
| pip, setuptools, wheel | Their PyPI distributions and included license notices |
| Frida and engine requirements | Exact versions declared by the pinned engine; upstream distribution licenses |
| OpenCV Python, NumPy, Pillow | Pinned in `requirements-extra.txt`; their distribution licenses are installed with the packages |
| Wails and Go libraries | Preserved texts under `recorder/third_party/licenses` |

Python, pip bootstrap wheel and engine archive URLs and SHA-256 values are in `recorder/internal/capture/embed/downloads.json`. Python package requirements are version-pinned; they are retrieved from PyPI and are not all hash-locked transitively. No Portable Git installation is needed.

New World and New World: Aeternum are Amazon trademarks. This package contains no game binaries, game assets, private captures or user-specific menu templates. Project names identify compatibility, not endorsement.
