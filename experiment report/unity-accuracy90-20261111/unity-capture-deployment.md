# 原生采集输入到最终压缩的闭环

原生参考图→封存模型推理→按原规则选参→每图一次ASTC编码→解码质量复算已通过两张已观察验证图的实际CUDA检查。评价过程直接使用原始采集与最终ASTC，不读取候选补测档案；独立确认集的正式调用方仍未接通。此次沿用旧smoke8权重，没有新增训练或生产准确率结论。`[verified: unity-capture-deployment-verification.json images、summary、test_opened、training_updates；capture_deployment.py run；capture_output.py run]`

## 实测结果与范围

| 项目 | 预测后编码 | 固定8×8 medium |
|---|---|---|
| 两图mip0 payload | 59,168字节 | 81,920字节。`[verified: unity-capture-deployment-verification.json summary.*.payload_bytes]` |
| 严格质量达标 | 1/2 | 2/2。`[verified: 同文件 summary.*.strict_quality_pass_rate]` |
| 对原搜索块大小标签的匹配 | 1/2；完整块大小＋preset匹配0/2 | 固定控制不作为标签预测模型。`[verified: 同文件 summary.prediction.footprint_accuracy、full_choice_accuracy；opinion: 控制用途]` |
| 两图端到端中位耗时 | 83.09毫秒 | 66.12毫秒。`[verified: 同文件 summary.*.median_end_to_end_seconds]` |
| 编码调用数 | 预热2次＋正式6次 | 预热2次＋正式6次，每轮每图一次。`[verified: 同文件 summary.*.warmup_encoding_calls、measured_encoding_calls]` |

计时包含参考PNG读取、输入准备、模型推理、规则选择及最终mip0编码，固定8×8不执行模型；同一轮两个分支都结束后才解码、评分和写文件。预热1轮、正式3轮，顺序交替，模型和DLL已加载。原Unity采集／归档仍在同机运行，这些小样本耗时不能用于生产加速结论。此次预测质量更低且耗时更长，也不支持等质量压缩收益。`[verified: capture_deployment.py run；deployment.py run；unity-capture-deployment-verification.json jobs、summary；opinion: 比较边界]`

完整进程20.31秒，内部执行8.58秒；模型11,377,660参数，state_dict内权重及buffer张量合计45,549,200字节，该数值不等于序列化模型文件大小。只编码mip0；法线质量函数可按导入信息从mip0计算最多四级角度指标，不表示已压缩完整mip链。`[verified: unity-capture-deployment-verification.json process_seconds、internal_seconds、parameters、weights_bytes；capture_deployment.py state.update；capture_output.py quality.measure；opinion: 文件与mip范围]`

## 一致性与验证

- 16份实际ASTC及解码PNG的SHA与已完成的对应编码档案相同，逐项原生质量指标一致；四轮预测数组与旧权重的验证输出最大差0。档案比对仅在独立核验脚本中执行，部署与评分组件不依赖它。`[verified: unity-capture-deployment-verification.json compared_native_outputs、decoded_pixels_and_metrics_match、max_prediction_difference；verify_capture_deployment.py]`
- 4次模型推理全部在固定模型／输入／规则／编码库／质量库身份后执行，尝试记录保留；本次均为validation，未打开confirmation测试。`[verified: 同文件 sealed_prediction_attempts、test_opened；smoke2-v2.json seal.identity]`
- 57项CPU检查通过，覆盖ASTC头／尺寸／payload、源像素变化、标签错位、阈值边界、法线分支、预测通过但实测失败，以及既有部署和封存行为；ruff、basedpyright通过。`[verified: 同文件 cpu_tests；本轮检查输出；tests/test_unity_capture_output.py]`
- 第一版实测也通过；随后补上原标签asset与输入asset的显式匹配检查，以新身份v2复跑。旧版评分源码归档于`.local/unity-accuracy90-20261111/unity-capture-deployment-smoke2-v1/prior-source/capture_output.py`，SHA为`3e30eaea02d6ef08c9e93263ff89f28ae1f9cda551d62486279a014c09d148c8`。`[verified: 同文件 prior_pass；对应v1/v2配置与结果]`
- 所有活动队列的14／23／15／17／25份执行文件及V1原始evidence哈希保持。`[verified: 同文件 unchanged_active_sources、v1_evidence_sha256]`

此次只真实编码选中的候选，因此报告的阈值附近误差只覆盖被选颜色候选，不能替代20候选的整体RMSE；未测候选误差明确为null。后续正式确认还需接通完整采集／像素隔离检查、共享固定cohort封存、独立2000图评价以及完整成本报告。`[verified: capture_output.py summarize；unity-capture-deployment-verification.json summary.*.all_candidate_rmse_db；opinion: 后续验收要求]`

## 入口与产物

- [运行入口](../../script/benchmark_unity_capture_deployment.py)、[部署实现](../../reproductions/unity_search_baseline/capture_deployment.py)、[可复用评分组件](../../reproductions/unity_search_baseline/capture_output.py)。入口显式限制已观察validation2，正式确认须另行接入，不能只改split绕过。`[verified: UnityCaptureDeploymentSmoke继承UnitySealedInferenceSmoke.__init__]`
- [冻结配置](unity-capture-deployment-smoke2-v2-config.json)、[实际结果](unity-capture-deployment-smoke2-v2.json)、[核验记录](unity-capture-deployment-verification.json)。重新执行须使用新输出身份；原始ASTC、解码图、预测数组和进程日志保存在`.local`。`[verified: 对应文件及capture_deployment.py run]`

```powershell
uv run python script/benchmark_unity_capture_deployment.py --config "<新的冻结验证配置绝对路径>"
```
