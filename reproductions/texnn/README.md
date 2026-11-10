# TexNN paper reimplementation

The user-supplied paper is archived in `materials/paper.pdf`; `source.json` records its original path and SHA-256. The document contains 12 pages, journal pages 328–339, DOI 10.1111/cgf.13534. `[verified: source.json; supplied PDF metadata]`

P-NN predicts the lexicographically ordered partition count/index label from block pixels. DEM-NN jointly predicts endpoint/decimation configuration from block pixels and computed base colors. Top-k predictions must feed a real encoder before encoding quality and speed can be evaluated. `[verified: supplied PDF p.7, §3.5 and Fig.5–6]`

The paper trains separate 4×4, 6×6 and 8×8 networks using cross entropy, an 85/15 block split, batch sizes 100–200, learning rates around 1e-4 and dropout 0.6. Original exact architecture tables S1/S2 are in a separate Appendix referenced on p.12. Record reconstructed settings separately when that material is unavailable. `[verified: supplied PDF pp.7–8 §3.6 and p.12 Supporting Information]` `[opinion]`

The user will supply the separate Appendix later. Exact network architecture implementation waits for that material. Encoder integration, training and end-to-end reproduction remain pending. `[verified: user reply, 2026-11-10, “暂时没有等我补充”; current reproduction directory contents]`
