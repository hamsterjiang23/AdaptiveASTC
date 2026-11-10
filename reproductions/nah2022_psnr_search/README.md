# Nah 2022 PSNR block-size search

This is a paper reimplementation of DOI 10.15701/kcgs.2022.28.2.21. `search.py` implements the directional search from Table 1. The encoder version, published class targets and unavailable manual initialization artifacts are recorded in `source.json`. `[verified: search.py; source.json; paper Table 1]`

The original stages are category-level manual analysis, fastest-mode search and thorough-mode final encoding. The reported timing excludes manual analysis; a full workflow report must also record that preparation cost. `[verified: paper §3 and §4.4]` `[opinion]`

The footprint list is ordered as in the 2023 author's implementation. The 2022 pseudocode abbreviates its list. Record this explicit reconstruction choice with results. Initial footprints must be supplied explicitly with their provenance. `[verified: source.json; 2023 Source/astcenccli_toplevel.cpp block_size_list]` `[opinion]`

Boundary tests cover first failure while moving toward larger footprints and the smallest footprint failing the target. After complete Unity baseline acceptance, the two-image probe and [64-image source-RGB adaptation](<../../experiment report/nah2022_psnr_search/source-rgb64-game/README.md>) completed actual ASTC encoding and decoding. The Game target is 37.3873 dB, the reconstructed initial footprint is 6×6, and the final preset is thorough. Full-image RGBA meets the target for 64/64 and RGB for 62/64. `[verified: tests/test_reproduction_baseline.py; game-probe and source-rgb64-game receipts]`

Search plus final encoding took 546.329 seconds, with a same-preset fixed-8×8 control of 295.809 seconds. The run used source RGB8 at original resolution with no mip chain and one encoding thread, with CLI-default decoding. Repository checks and another run's offline quality audit shared the host during part of this validation. The original author images, manual ideal-footprint labels and category-specific initial values remain separate source artifacts to obtain for a published-protocol replication. `[verified: measured receipt.json protocol/timing fields; concurrent exec sessions 92587, 15732 and 18013; source.json missing_original_artifacts]`
