# Sprite 候选补测与依赖队列恢复

原补测队列在train-030批次索引52（第53张）失败：`Assets/CustomMode/DisOrderNewMode/Art/Prefabs/Effect/Common/touzi/gold/9.png`，128×128、Sprite、sRGB、带Alpha。原回调profile=0、normal_pack=false、channel=4；失败发生在补测入口仅允许Default的检查。此时已完成7744训练／2验证图，失败批另保留前52张已完成候选产物。下游数据、训练和确认集等待任务因上游失败退出，原参考采集继续。`[verified: unity-candidate-queue-multimip-v2.json error、counts、current_batch；candidate-queue-multimip-v2/batches/unity-v1-train-030-20261111/receipt.json rows；原options-receipt.json rows[52]；各失败jobs/receipt.json]`

补测入口新增LDR Sprite，要求已记录实际encoder callback，再按原流程验证回调来源、Alpha、profile、RGBA、质量和选中payload。保留Sprite导入类型与原像素，NormalMap走既有法线分支，HDR及未知类型仍不进入该颜色路径。`[verified: ../../reproductions/unity_search_baseline/supplement.py validate_color_input、verify_actual_options；../../reproductions/unity_search_baseline/candidate_completion.py collect_image]`

[失败样本的20候选实测](unity-sprite-candidates20-v1.json)成功：原16项指标符合原报告精度，选中的完整ASTC和解码像素一致，新增4项候选。内部0.763秒／进程1.048秒，20项相关CPU测试通过。原引擎颜色质量判断由法线用途、HDR及sRGB分支决定，本次保留其同次搜索标签。`[verified: unity-sprite-recovery-readiness.json；unity-sprite-candidates20-v1.json rows；ASTCCompressor.cpp TestAllParameterCombinations质量分支；opinion: 协议边界]`

| 新任务 | 恢复内容 | 验收状态 |
|---|---|---|
| 候选补测sprite-v3 | 冻结32批已完成归档作为reuse，重新核验SHA；失败批使用新目录重新编码 | 已启动复核旧批，完整11000图尚未完成。`[verified: unity-candidate-queue-sprite-v3-config.json reuse；unity-candidate-queue-sprite-v3.json]` |
| 全量数据full-v3 | 依赖新补测队列；复用原patch shards，原四阶段检查保持 | 等待上游。`[verified: unity-native-pipeline-full-v3-config.json；unity-native-pipeline-full-v3.json]` |
| CUDA训练full-v2 | 训练配方未变，新的32图预检目录与正式输出 | 新预检已通过，等待完整数据；正式训练未开始。`[verified: unity-native-training-full-v2.json stages、status；unity-sprite-recovery-readiness.json training_recipe_changed]` |
| 确认集smoke2-v2 | 原预留名单前两张不变，绑定新依赖和当前15份源码 | 等待开发任务成功，未采集新确认标签或打开模型测试。`[verified: unity-confirmation-capture-smoke2-v2.json status、native_labels_collected、test_opened；对应config]` |

新候选队列的计数从零开始表示本次已重新核验的批次；原7746图候选仍保留，不是丢失后从零采集。失败批52图已完成部分单列保留，这次不把部分批次冒充完整批次复用；额外重编成本保留在新任务。旧队列27583.49秒包含已完成工作及等待，旧下游任务的11953.40／5314.24／1312.40秒也含等待，不能全部计为失败处理或部署耗时。`[verified: unity-sprite-recovery.json prior_jobs、reuse_batches；opinion: 计时与恢复边界]`

旧配置、结果、失败日志保留；修复前supplement.py另归档，SHA为`aff26c333f70a30b12a21920ab8b892d5b43e69910befd1603aebf488e029781`，当前为`0bf58810a71d30cfebe497d7a67012d6370802001c7297ac3013636a30be48f8`。此修复发生在旧下游任务退出后，原参考采集使用的引擎、插件、采集入口未改。`[verified: unity-sprite-recovery-readiness.json old_supplement_source_sha256、new_supplement_source_sha256；git diff supplement.py；opinion: 修改范围]`

配置与真实小样本依据见[恢复前检查](unity-sprite-recovery-readiness.json)，当前进程与依赖见[恢复验证](unity-sprite-recovery-verification.json)及[progress.json](progress.json)。最终Unity独立测试90%仍未验收，goal保持active。`[verified: 对应JSON；get_goal status active；opinion: 完成边界]`
