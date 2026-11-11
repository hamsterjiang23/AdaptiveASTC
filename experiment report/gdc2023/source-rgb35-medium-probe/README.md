# GDC measured-label dependency probe

Eight source images completed four candidate encodings each, producing 32 actual ASTCs and decoded images. Strict RGB PSNR >35 dB was feasible for 7/8 images; the remaining image retained the highest measured PSNR and an explicit infeasible flag. `[verified: labels.json images, candidate_encodings, target_met and selection]`

An identical-recipe cache replay preserved the original collection and per-image receipt hashes. Source hashes, candidate coverage, actual ASTC dimensions/bytes, saved reconstructed PSNR and label selection were checked before assembling the RGB224 classifier dataset. `[verified: labels.json cache_replay; dataset.py validate_receipt/assemble; native probe execution]`

This is an eight-image dependency probe using reconstructed 6×6/8×8/10×10/12×12, astcenc 3.3 medium and source RGB8. It overlapped TexNN GPU training. A one-epoch training attempt recorded an AMP-skipped update, with empty optimizer state and loss scale 32768; it is not used as a trained-model result. The completed [smoke chain](../source-rgb35-medium-smoke/test16/README.md) uses a separate identity. Full provenance: [labels.json](labels.json). `[verified: labels.json protocol, model_training, model_final_encoding and timing_context; raw probe last.pt]`
