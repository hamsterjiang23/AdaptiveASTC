# Nah 2022 PSNR block-size search

This is a paper reimplementation of DOI 10.15701/kcgs.2022.28.2.21. `search.py` implements the directional search from Table 1. The encoder version, published class targets and unavailable manual initialization artifacts are recorded in `source.json`. `[verified: search.py; source.json; paper Table 1]`

The original stages are category-level manual analysis, fastest-mode search and thorough-mode final encoding. The reported timing excludes manual analysis; a full workflow report must also record that preparation cost. `[verified: paper §3 and §4.4]` `[opinion]`

The footprint list is ordered as in the 2023 author's implementation. The 2022 pseudocode abbreviates its list. Record this explicit reconstruction choice with results. Initial footprints must be supplied explicitly with their provenance. `[verified: source.json; 2023 Source/astcenccli_toplevel.cpp block_size_list]` `[opinion]`

Boundary tests cover first failure while moving toward larger footprints and the smallest footprint failing the target. Native encoding experiments wait for the complete Unity baseline. `[verified: tests/test_reproduction_baseline.py; accepted execution order]`
