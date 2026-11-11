# Unity 原搜索规则重放

260 张开发图的完整质量记录重放通过：块大小、preset、选择原因和实际候选尝试次数，四项均与同次 Unity 原搜索一致。样本为 train258／validation2，含 18 张法线；使用实测候选质量，没有模型预测，也没有打开测试集。`[verified: unity-policy260-bound-v2.json counts、normal_images、matching_fields、mismatches、test_opened]`

## 原规则与验收

采用原采集缓存中的 LITE 配置：PSNR 基础门槛 30 dB，纯黑像素比例严格超过 40%／80% 时分别为 35／37 dB；sRGB 的 MS-SSIM 门槛为 21 dB；法线平均／p95 角度门槛为 3.2°／9°；大图面积门槛 512²，RDO 关闭。比较先转为原生 float32，保留阈值处的包含关系。`[verified: unity-policy260-bound-v2-config.json policy_caches；policy.py UnitySearchPolicy.__init__、select；原缓存 tableConfig]`

| 原搜索分支 | 图数 | 重放行为 |
|---|---:|---|
| 普通首个合格候选 | 198 | 按 12／10／8／6 的块大小和各自五个 preset 顺序，接受第一个通过对应质量门槛的候选。`[verified: unity-policy260-bound-v2.json branch_counts.first_valid；policy.py select]` |
| 大图严格通过 | 35 | 首个 PSNR 通过候选锁定块大小，同块继续尝试，到 MS-SSIM 同时通过时接受。`[verified: unity-policy260-bound-v2.json branch_counts.size_first_strict；policy.py select]` |
| 大图放宽结果 | 25 | 锁定块始终未同时通过两项门槛，保留该块最后一个 PSNR 通过候选；切换块大小的下一候选已被测量，也计入次数。`[verified: unity-policy260-bound-v2.json branch_counts.size_first_relaxed；policy.py select；ASTCCompressor.cpp L3241–3294、L3353–3364]` |
| 最高 PSNR 回退 | 2 | 没有有效候选时按最高 PSNR 回退，并列保留先出现者。`[verified: unity-policy260-bound-v2.json branch_counts.highest_psnr_fallback；policy.py select；ASTCCompressor.cpp L3373–3386]` |

233／260 张原选中候选严格通过对应质量门槛；另外 25 张采用大图放宽规则、2 张采用回退规则。规则标签复现成功与严格质量通过分别计数，这些样本不能用来声明全数据的质量上限。`[verified: unity-policy260-bound-v2.json strict_quality_passing_images、branch_counts；opinion: 统计边界]`

## 只保留 PSNR 会怎样

诊断使用相同 20 组候选的真实 PSNR、相同黑像素门槛和候选顺序，仅去掉 MS-SSIM、法线角度及大图分支，按普通 PSNR 规则决策。块大小与原标签一致 207／260（79.62%），块大小＋preset 一致 110／260（42.31%）。这是选定开发子集上的规则删减结果，不是模型准确率或可学习上限。`[verified: unity-policy260-analysis.json overall_psnr_only_footprint_accuracy、overall_psnr_only_full_choice_accuracy；policy_audit.py psnr_only_diagnostic；opinion: 解释范围]`

| 类型 | 图数 | 仅 PSNR 的块大小命中 | 仅 PSNR 的块大小＋preset 命中 |
|---|---:|---:|---:|
| sRGB 小图 | 180 | 140 | 84。`[verified: unity-policy260-analysis.json groups.srgb_small]` |
| sRGB 大图 | 60 | 60 | 22。`[verified: unity-policy260-analysis.json groups.srgb_large]` |
| 法线 | 18 | 5 | 2。`[verified: unity-policy260-analysis.json groups.normal]` |
| 其他 Linear | 2 | 2 | 2。`[verified: unity-policy260-analysis.json groups.linear]` |

Unity 迁移继续保留 RGBA 通道误差、MS-SSIM 和法线角度监督，并使用原规则选择配置；下一步需要验证整图质量预测与聚合方法。GDC 四个 medium 候选的 PSNR 回归仍按其原协议计分。当前没有完成 Unity 模型训练或独立测试 90% 验收。`[verified: unity-patches-train256.json scope；unity-policy260-bound-v2.json scope；opinion: 后续模型要求与验收边界]`

## 来源绑定、执行与成本

入口为 `script/replay_unity_policy.py --config ...`。正式结果见 [绑定原采集的配置](unity-policy260-bound-v2-config.json)、[重放结果](unity-policy260-bound-v2.json) 和 [分组诊断](unity-policy260-analysis.json)。配置包含本机原始归档路径及 SHA；复跑需保留这些归档，并为输出目录和报告指定新身份，已有结果拒绝覆盖。`[verified: script/replay_unity_policy.py main；policy_audit.py run；unity-policy260-bound-v2-config.json]`

首次 [重放记录](unity-policy260.json) 只绑定调用者提供的缓存路径和 SHA。审查发现替换成另一份近似规则缓存仍可能得到相同标签，不能证明用了原采集规则。修正后，从冻结采集 identity／phase 配置推导缓存路径，要求其与当前输入一致，再运行原 LITE 全配置及来源审计；用独立 bound-v2 身份重新核验 260 张图。旧结果保留为有该限制的历史记录。`[verified: unity-policy260-bound-v2-config.json prior_audit；policy_audit.py verify_policy_origin；test_unity_policy_audit.py test_foreign_cache_cannot_substitute_for_original_policy]`

绑定后的审计循环耗时 0.9674 秒，完整进程 3.6460 秒。这里只消费已测质量，没有重新编码或训练，不能与完整 Unity 搜索耗时直接计算模型加速比。规则边界及替换缓存反例共 16 项检查通过。`[verified: unity-policy260-bound-v2.json wall_seconds；.local/unity-accuracy90-20261111/jobs/unity-policy260-bound-v2/receipt.json wall_seconds；pytest 16 passed；opinion: 成本范围]`
