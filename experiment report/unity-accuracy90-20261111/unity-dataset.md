# Unity 原生 RGBA patch Dataset

原生 Dataset 已在258张训练图和2张验证图上完成检查，保留20组块大小／preset候选的逐通道监督。此次交付是训练输入与目标的配对验证，尚未训练Unity模型；独立测试90%验收仍待完成。`[verified: unity-dataset260-v2.json unique_images、training_updates、test_opened；opinion: 验收范围]`

## 输入和目标

入口为 [audit_unity_patch_dataset.py](../../script/audit_unity_patch_dataset.py)，数据类为 [UnityPatchDataset](../../src/adaptive_astc/data/unity_patch_dataset.py)。实验配置必须提供corpus.json的外部SHA-256；加载时同时校验参考图、目标数组、划分、候选顺序、实际编码属性及整图PSNR重建。只接受train／validation，拒绝test／calibration。`[verified: unity_patch_dataset.py __init__；unity-dataset260-v2-config.json corpora]`

| 内容 | 实际接口与约束 |
|---|---|
| 像素输入 | 原生RGBA，范围0–1，4×240×240；边缘复制填充，另给有效像素mask和像素数。逐像素重建及填充检查通过。`[verified: unity_patch_dataset.py __getitem__；unity-dataset260-v2.json corpora.*.splits.*.exact_pixel_and_padding_checks]` |
| 误差目标 | 每个patch的20×4通道整数SSE，转换为归一化log10(MSE+1e-10)，并保留逐通道精确零误差布尔目标。`[verified: unity_patch_dataset.py errors、targets、zero_error]` |
| 可用于输入的属性 | log2宽／高、sRGB、法线用途、Alpha需求、Alpha是否恒定、法线评价mip数、黑像素比例，共8项。原标签、preset、实测质量及搜索次数不进入该输入张量。`[verified: unity_patch_dataset.py METADATA_NAMES、metadata；test_unity_patch_dataset.py test_search_outputs_do_not_enter_input_metadata]` |
| 整图监督 | 原始策略选择、20候选的MS-SSIM及法线角度保留在图级记录中；不把这些非加性指标拆成patch均值。图级学习／聚合目标尚待实现。`[verified: unity_patch_dataset.py rows、image_quality；opinion: 学习范围]` |

256张训练图的5120个图级候选中，有377个至少一个RGB通道精确无损，38个RGB全部无损。原生PSNR按整图误差决定参与通道，因此保留零误差目标；未来模型不能直接把极小正误差当作原生零误差，相关预测与决策仍需单独验证。`[verified: unity-dataset260-v2.json corpora[0].splits.train；UnityChannelErrors.psnr；opinion: 模型要求]`

## 实测范围与成本

| 检查 | 覆盖 | 循环／完整进程耗时 |
|---|---|---|
| 初始小样本 | 5 train＋2 validation，32 patch | 0.24／6.11秒。`[verified: unity-dataset-smoke.json；jobs/unity-dataset-smoke/receipt.json]` |
| 首次扩展 | 唯一258 train＋2 validation，含18张法线 | 17.18／22.00秒；这是补强重复目标检查前的历史记录。`[verified: unity-dataset260.json；jobs/unity-dataset260/receipt.json]` |
| 最终实现复核 | 同一260图，1708次patch检查 | 9.52／13.22秒；最终代码哈希保存在报告。`[verified: unity-dataset260-v2.json；jobs/unity-dataset260-v2/receipt.json]` |

两个语料共享相同的2张验证图，合计1708次patch检查包含13次重复验证patch；唯一图对应1695个patch和5200个候选。完整语料尚在采集，此处只有2张验证图，不能据此评价泛化。最大原生PSNR重建差为3.7416e-6 dB以内。耗时与其他采集／训练重叠，且存在文件缓存差异，不作为性能加速比较。`[verified: unity-dataset260-v2.json corpora、unique_images；opinion: 成本与验证边界]`

## 重复数据修复与检查

独立审查发现：只比较整图SSE会接受同一图中不同的patch误差分配。修复后同时比较目标文件SHA与patch尺寸，拒绝跨语料划分冲突或监督冲突。新增反例保持整图误差总量不变，先确认两份语料各自能加载，再验证组合检查拒绝发布报告。19项测试通过，复查关闭该问题。`[verified: dataset_audit.py run；test_unity_patch_dataset.py test_audit_cross_corpus_identity；pytest 19 passed；review C1复查]`

先期小样本和首次扩展报告保留各自源码哈希；最终复核使用[新版配置](unity-dataset260-v2-config.json)和[新版结果](unity-dataset260-v2.json)。复跑需复制配置并指定新的输出报告，已有报告受覆盖保护。原始目标和训练中的GDC代码保持冻结。`[verified: dataset_audit.py run；unity-dataset260-v2-config.json prior_audit_report_sha256；opinion: 复跑要求]`
