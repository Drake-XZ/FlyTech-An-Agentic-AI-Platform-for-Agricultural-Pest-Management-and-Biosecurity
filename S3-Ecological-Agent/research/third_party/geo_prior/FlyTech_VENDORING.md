# FlyTech vendoring record

- Upstream: <https://github.com/macaodha/geo_prior>
- Upstream commit: `257dc7e30f3cc6bf02fbec55ee878724d077fe61`
- Retrieved: 7 September 2026
- Purpose: reproduce the ICCV 2019 presence-only geographic-prior baseline for
  FlyTech Milestone 2 preparation.

The upstream tree at this commit does not include an explicit LICENSE or
COPYING file. The FlyTech project owner's instruction authorises storing this
snapshot in this project repository, but does not create or imply a licence for
reuse, redistribution, modification, or deployment outside that authorised
project context. Preserve the upstream attribution and commit identity. Seek a
licence clarification from the upstream authors before external distribution
or production use.

No pretrained weight was added: the historical model URL embedded in
`demo.py` returned HTTP 404 over both HTTP and HTTPS on 7 September 2026.
