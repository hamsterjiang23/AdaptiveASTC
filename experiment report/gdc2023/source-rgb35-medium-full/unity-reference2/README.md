# GDC on Unity reference pixels

Measured 2 captured mip0 RGB inputs from the training cohort. The frozen classifier passed strict RGB 35.0 dB on 2 images, fixed8 passed on 2, and Unity's selected payload passed on 0. `[verified: accompanying JSON quality and scope]`

Deployment time includes RGB input preparation, classifier preparation, inference and one final encode. The paired fixed8 time includes RGB preparation and fixed encoding. `[verified: accompanying JSON costs and per_image.timings]`

[Full measured results](pretrained-unity-reference.json) retain per-image quality, payload, source hashes and model identity. `[verified: accompanying JSON]`
