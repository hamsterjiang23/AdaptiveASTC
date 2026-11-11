# TexNN 参考编码器与网络尺寸探针

用户提供的 Appendix 共 13 页，SHA-256 为 `beb6457e1aedb9c53028af812a3058fdc9560ff834e6b513b7dd828dcd2e0bf9`，六个模型使用其第1页 Tables 1–2 的层尺寸。`[verified: summary.json source/networks]`

历史参考编码器固定到 `ddadf547770ddbe8261cfd854b2a5f21b3a9074c`，版本按论文引用的 2017-06-20 访问日期补全。源码保持干净，标签观察代码通过生成文件接入，构建二进制及实现文件的哈希保存在汇总中。`[verified: summary.json source/build/implementation_sha256]`

已核验 11 次原生收集、140 个块。每次观察器的完整 ASTC 与原始编码器逐字节一致，每个标签匹配真实块字节、输入像素及合法配置表。`[verified: summary.json native_runs]`

| 运行 | 块大小 | 块数 | 常量块 | payload B | RGB PSNR dB |
|---|---|---|---|---|---|
| label-catalog-probe-4x4 | 4x4 | 12 | 0 | 192 | 21.2581 `[verified: summary.json native_runs]` |
| label-catalog-probe-6x6 | 6x6 | 6 | 0 | 96 | 14.9469 `[verified: summary.json native_runs]` |
| label-catalog-probe-8x8 | 8x8 | 4 | 0 | 64 | 13.7308 `[verified: summary.json native_runs]` |
| label-catalog-constant-4x4 | 4x4 | 12 | 12 | 192 | 无损 `[verified: summary.json native_runs]` |
| asset0-label-4x4 | 4x4 | 16 | 8 | 256 | 56.0019 `[verified: summary.json native_runs]` |
| asset0-label-6x6 | 6x6 | 9 | 5 | 144 | 47.2212 `[verified: summary.json native_runs]` |
| asset0-label-8x8 | 8x8 | 4 | 0 | 64 | 41.7490 `[verified: summary.json native_runs]` |
| asset1-label-4x4 | 4x4 | 36 | 29 | 576 | 无损 `[verified: summary.json native_runs]` |
| asset1-label-6x6 | 6x6 | 16 | 8 | 256 | 无损 `[verified: summary.json native_runs]` |
| asset1-label-8x8 | 8x8 | 9 | 1 | 144 | 无损 `[verified: summary.json native_runs]` |
| collector-final-check-4x4 | 4x4 | 16 | 8 | 256 | 56.0019 `[verified: summary.json native_runs]` |

输入为源图 RGB8、Linear LDR、原始尺寸、无 mip，编码线程为1。原始 PNG 由旧版 stb 读取器翻转 Y 轴，标签以左下角为原点，边界像素按编码器规则重复。常量块采用原生常量编码，并以独立标记保存。`[verified: native_runs 的 receipt 与 post_collection_pixel_check；astc_stb_tga.cpp L31/L76；native/labels.cpp]`

RGB 像素后拼接最多四个分区的24个理想 RGB 端点值，未使用分区补零。ReLU、Gaussian 标准差0.01和隐藏层 dropout 的位置属于本地补全设置，代码默认 dropout 丢弃概率为0.6。`[verified: models.py TexNNClassifier；native/labels.cpp]` `[opinion]`

本报告验收参考标签提取和六个网络的前向维度。数据集构建、模型训练、预测配置接回编码器及学习式编码质量和耗时评价继续执行。`[verified: summary.json scope；当前实现入口]`

源码、构建及收集命令见[TexNN 复现入口](../../../reproductions/texnn/README.md)。逐块原始记录与编码文件位于 `.local/reproduction-runs/texnn/`，本报告的逐运行摘要绑定原始 receipt 和产物哈希。`[verified: summary.json native_runs artifacts_sha256/receipt_sha256]`
