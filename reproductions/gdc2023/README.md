# GDC 2023 block-size classification

The talk implementation follows offline ASTC candidate compression, decompression, PSNR-based label selection, ResNet classification and one final encode using the predicted footprint. Original label selection uses PSNR >35 dB. `[verified: archived talk 11:00, 11:28 and 12:28; source.json]`

The existing historical LITE experiment remains under `experiment report/gdc-lite-rgb-resnet18-seed20261109`. It uses RGB source images and historical mixed-preset/RDO labels. Final compression quality and byte benefits have not been measured there. `[verified: existing training_report.md L56–60]`

The new compression-loop reproduction follows Nah 2023, Nah 2022 and TexNN. Preserve the talk's reconstructed settings and the project LITE adaptation as separate experiment identities. `[verified: accepted plan]` `[opinion]`
