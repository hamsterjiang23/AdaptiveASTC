# 原生模型封存与验证图推理

完成模型／输入／规则封存组件，并在两张已观察的Unity验证图上通过真实CUDA推理：13个patch，四组预测数组与原训练保存结果完全一致，最终选参一致，完整进程9.933秒。本轮没有训练更新、最终编码或确认集测试；正式独立评价调用方尚待接入。`[verified: unity-sealed-inference-verification.json images、patches、prediction_differences、choices_match、process_seconds、scope]`

## 已验证内容

| 检查 | 结果与范围 |
|---|---|
| 模型来源 | 沿用原生smoke8权重`b4679b4f…`，核对训练进程成功退出、所运行配置、训练报告、选中epoch、三份最佳产物及训练源码。未选择新模型。`[verified: sealed_inference.py prepare/verify_checkpoint；smoke2-v2.json checkpoint_sha256]` |
| 原生输入与规则 | 从已完成的64训练／2验证参考系列取原validation两图，复核原搜索、回调、导入属性与策略来源。输入适配器只投影像素及导入属性，推理完成后才与已保存验证预测比较。`[verified: sealed_inference.py prepare/run；unity_capture_input.py project]` |
| 封存先于预测 | 实际seal创建时间早于forward尝试记录；绑定模型、输入清单指纹、策略指纹、240patch、batch16、zero阈值、运行库与文件SHA。`[verified: unity-sealed-inference-verification.json seal_before_forward；smoke2-v2.json seal.identity]` |
| 合同更改拒绝 | 在真实开发封存记录上尝试更换model／decision身份，均在预测前拒绝，原封存文件SHA保持不变；没有新增forward。`[verified: unity-sealed-inference-verification.json changed_contract_rejections、seal_sha256；verify_sealed_inference.py]` |
| 预测与选参 | channel_mse、channel_zero、zero_probability、image_quality最大差均0，全部选参相同。该结果证明接口一致，不是新的准确率提升。`[verified: smoke2-v2.json max_abs_prediction_difference、choices_match；opinion: 结果解释]` |
| CPU检查 | 73项通过，包含竞争创建、不同模型／规则拒绝、源文件或内存身份变化、缺失缓存后来出现、失败预测保留记录、验证划分不打开确认测试，以及tuple／list配置兼容。ruff和basedpyright通过。`[verified: unity-sealed-inference-verification.json cpu_tests；本轮检查输出；tests/test_unity_evaluation_seal.py、test_unity_sealed_inference.py]` |

## 时间与历史失败

本次证据准备0.960秒、模型加载0.330秒、输入准备0.0108秒、单次推理0.752秒；证据准备后的内部流程2.836秒，完整进程9.933秒。此次forward没有预热，不与此前预热后的推理延迟直接比较。审核、CUDA初始化、哈希核验和报告写入也计入各自包含范围。`[verified: unity-sealed-inference-verification.json 各seconds字段；sealed_inference.py run、UnityQualityInference.run；opinion: 比较边界]`

首轮`smoke2-v1`在封存／forward前失败：检查点保存tuple，JSON恢复为list，直接比较误判配置变化。实读检查点发现epoch均为1且配置指纹相同；改用原训练器相同的规范化指纹比较后，以`smoke2-v2`复跑通过。首轮配置、日志、失败报告与旧源码保留，旧源码SHA为`a09dd8a5476bf107dcbac01143a632cbef27a75662bc88abe29318181983515f`，位置为`.local/unity-accuracy90-20261111/unity-sealed-inference-smoke2-v1/prior-source/`。`[verified: unity-sealed-inference-verification.json prior_failure；unity_quality_trainer.py audit_best；test_unity_sealed_inference.py]`

## 接入约束与入口

- [UnityEvaluationSeal](../../src/adaptive_astc/utils/unity_evaluation_seal.py)通过同目录临时文件和不可覆盖的硬链接发布完整记录；同一registry内，同一cohort不能更换推理合同。每次forward前写入尝试记录，异常同样保留。调用方负责真实数据、模型、规则来源核验，该组件本身不证明像素隔离或模型质量。`[verified: unity_evaluation_seal.py __init__/acquire/forward及类说明]`
- 验证数据允许模型开发，因此当前smoke使用运行目录内的开发seal。后续确认集调用方必须使用共享且固定的cohort registry，同时绑定完整原生采集与像素审计，不能通过换输出目录绕过封存。正式2000图评价、质量／payload与端到端压缩对照仍未接通。`[verified: sealed_inference.py run registry注释与validation限制；opinion: 正式接入要求]`
- 入口[verify_unity_sealed_inference.py](../../script/verify_unity_sealed_inference.py)显式限制两张validation图，不能用改split的方式运行confirmation。复跑使用新配置和输出身份。`[verified: UnitySealedInferenceSmoke.__init__/run]`
- [通过配置](unity-sealed-inference-smoke2-v2-config.json)、[通过结果](unity-sealed-inference-smoke2-v2.json)、[初次失败](unity-sealed-inference-smoke2-v1.json)、[核验记录](unity-sealed-inference-verification.json)。`[verified: 对应文件]`

```powershell
uv run python script/verify_unity_sealed_inference.py --config "<新的冻结验证配置绝对路径>"
```
