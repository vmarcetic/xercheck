# Sources and licences

This file is the attribution record for the sample XER files shipped with the checker. The checker software itself is MIT-licensed; see `LICENSE`.

## `fixtures/public/` — Franco Duran research schedules (CC BY 3.0 US)

Two unmodified Primavera P6 XER exports from a research dataset. They are academic CPM networks created in P6 16.1, not a contractor's as-built programme.

| Item | Value |
| --- | --- |
| Title | Primavera P6 Schedules |
| Author | Diana Franco Duran |
| Year | 2019 |
| Publisher | University Libraries, Virginia Tech |
| DOI | https://doi.org/10.7294/w4-5r6z-d346 |
| Landing page | https://data.lib.vt.edu/articles/dataset/Primavera_P6_Schedules/14099552 |
| Public API record | https://api.figshare.com/v2/articles/14099552 |
| Citation | Franco Duran, Diana (2019). Primavera P6 Schedules. University Libraries, Virginia Tech. Dataset. https://doi.org/10.7294/w4-5r6z-d346 |
| Licence | [CC BY 3.0 US](https://creativecommons.org/licenses/by/3.0/us/) (`license.value` 120 on the API record) |
| Legal code | https://creativecommons.org/licenses/by/3.0/us/legalcode |

You are free to share and adapt the material, including commercially, if you give appropriate credit, provide a link to the licence, and indicate if changes were made. The deed also says no warranties are given.

The API record describes 142 networks created in Primavera P6 v16.1 for resource-constrained scheduling research, with 30 to 90 activities.

The two files were extracted, byte for byte, from the archive `RF = 0.25.zip` on that record (download https://ndownloader.figshare.com/files/26590055, 267,937 bytes, MD5 `2f6f18f28d472e2d643839bfc5b366e0`). No bytes were edited.

| Saved as | Original zip member | Bytes | SHA256 |
| --- | --- | --- | --- |
| `fixtures/public/P01_CPM.xer` | `RF = 0.25/P01_CPM.xer` | 26,908 | `b580b4fb384bef28529b28b530e13c9276157afcc1c00e395fce22b0b58953bc` |
| `fixtures/public/P02_CPM.xer` | `RF = 0.25/P02_CPM.xer` | 26,733 | `a945a7c55a88e4c78d75c4b0a24392f7dde7525b4ce8e6849d4a4c612482259f` |

Both start with `ERMHDR` version `16.1` and use CRLF. Re-check with:

```bash
sha256sum fixtures/public/P01_CPM.xer fixtures/public/P02_CPM.xer
```

## `fixtures/github/MDL4RA.xer` — five-house demo (MIT repository)

| Item | Value |
| --- | --- |
| Repository | https://github.com/inigmat/exupery |
| Commit | `b1ef15d17d123f4d55e9bd28095370c2fbe6d343` |
| Path in repo | `files/schedule/MDL4RA.xer` |
| Raw URL (pinned) | https://raw.githubusercontent.com/inigmat/exupery/b1ef15d17d123f4d55e9bd28095370c2fbe6d343/files/schedule/MDL4RA.xer |
| Licence in repo | MIT License, "Copyright (c) 2023 Ilgiz" |
| Bytes / SHA256 | 78,947 / `6fbad1e78450a4a0349e1f1a1a1f6a6d7568757ef142f0ba8819ab619c8668a6` |

This is a P6 export (`ERMHDR` 22.12, dated 2023-07-27) of the author's CPLEX "Model 4" five-house building example. The same model is described in a [public blog post](https://inigmat.github.io/home/2024/02/24/XER-reading.html). It is a demo/research model, not a client schedule. The file is included unchanged, with its original name. The repository licence is a software licence; no separate data licence was found.

## `fixtures/github/p2_activities.xer` — synthetic DCMA test fixture (MIT repository)

| Item | Value |
| --- | --- |
| Repository | https://github.com/danafitkowski/cpp-critical-path-validator |
| Commit | `c12d825ef20f8d5f2a81fb78cc01c3320412c42b` |
| Path in repo | `tests/fixtures/dcma_parity/p2_activities.xer` |
| Raw URL (pinned) | https://raw.githubusercontent.com/danafitkowski/cpp-critical-path-validator/c12d825ef20f8d5f2a81fb78cc01c3320412c42b/tests/fixtures/dcma_parity/p2_activities.xer |
| Licence in repo | MIT License, "Copyright (c) 2026 Dana Fitkowski / Critical Path Partners" |
| Bytes / SHA256 | 10,558 / `88ca9af696771297b157e5958de2e1cf0358f5d15803abcca2c9de705e6b732f` |

This is a synthetic DCMA-14 test fixture. The fixture README in that folder says "Synthetic schedules (no client data)". It is written by a generator script, not exported from a live project. It is included here because it is a small, clean public file that has stored negative float, high float, and blank float together. Present it as a test file, not as a real schedule. The repository licence is a software licence.

## `fixtures/synthetic/`

The `SYNTHETIC_*.xer` files were written for the tests in this repository. They are not extracts from the Franco Duran dataset and they are not public schedules. Each project short name is `SYNTHETIC`. See `fixtures/synthetic/README.md`.

## Column name

P6's XER import/export map names the TASK column `total_float_hr_cnt` as Total Float:

https://docs.oracle.com/cd/F74773_01/English/Mapping_and_Schema/xer_import_export_data_map_project/97906.htm

The P6 data dictionary describes that quantity as Total Float (hours):

https://docs.oracle.com/en/industries/construction-engineering/primavera-p6-project/26/p6-dd/totalfloathours-46478a.html

Oracle's manuals are not reproduced here. The checker does not convert the stored hours with a calendar.
