# V3独立确认测试报告

## 实验结论

冻结的Unity参考图输入、ResNet-34、20候选预测起点续搜系统，在2000张独立确认图上块大小匹配率为 **97.65%**，达到90%的系统验收目标。执行状态、封存复核和输出审计均通过。`[verified: result.json status、accuracy90_met、summary；共享seal对应attempt]`

纯模型预测起点的块大小匹配率为91.45%，实际续搜系统为97.65%。开发验证1000图对应值为86.9%和93.6%。`[verified: result.json summary；V3开发summary.json recommendation及controls]`

## 测试对象与协议

测试使用开发阶段选定的同一权重、Unity参考像素、原始20候选标签及原生质量规则，采用共享cohort封存。各计时单元8图预热一次、正式重复三次，覆盖files／pixels_ready及batch／single四种组合。`[verified: execution-config-v2.json；execution-seal.json；result.json measurements]`

测试CPU为Intel(R) Core(TM) i7-14700KF，28个逻辑处理器，内存63.78 GiB。GPU为NVIDIA GeForce RTX 4070，显存12282 MiB，驱动581.80。`[verified: hardware.json cpu、logical_processors、ram_bytes、gpu]`

封存运行信息为PyTorch 2.8.0+cu128、NumPy 2.5.4、device=cuda、threads=4。`[verified: 共享seal identity.runtime]`

确认集含2000张图，总像素数2,021,930,100，RGBA原始字节总量为8,087,720,400。输出范围为LDR、RGBA8、mip0，RDO关闭，法线用途由导入配置提供。`[verified: prepared-inputs.json rows；UnityCaptureInputAdapter；冻结V3协议]`

## 主要结果

| 指标 | 独立确认结果 |
|---|---|
| 系统块大小匹配 | 1953／2000，97.65%。`[verified: result.json summary.footprint_accuracy]` |
| Blocksize＋Quality匹配 | 86.65%。`[verified: result.json summary.full_choice_accuracy]` |
| 严格质量通过 | 1772／2000，88.60%。`[verified: result.json summary.strict_quality_pass_rate]` |
| 相对原标签严格质量回退 | 0张。原标签严格合格1768张。`[verified: result.json summary.quality_regression_images；主评分rows.json original_selection]` |
| 平均实际编码次数 | 1.6035次／图，P95为4次，最大15次。`[verified: result.json summary.candidates_measured]` |
| mip0 payload | 248,140,176字节，为固定8×8几何payload的49.07%。`[verified: result.json summary.payload_bytes、payload_ratio_to_fixed8]` |
| 相对原标签payload | 100.18%。`[verified: result.json summary.payload_ratio_to_original]` |

## 真实耗时

| 计时口径 | 三轮整集耗时中位数摊销 |
|---|---|
| 文件输入／批量摊销 | 620.91 ms／图。`[verified: result.json results.files_batch]` |
| 像素就绪／批量摊销 | 591.35 ms／图。`[verified: result.json results.pixels_ready_batch]` |
| 文件输入／逐图均值 | 630.12 ms／图。`[verified: result.json results.files_single]` |
| 像素就绪／逐图均值 | 616.81 ms／图。`[verified: result.json results.pixels_ready_single]` |

文件输入逐图模式的三轮均值为639.53、626.34、630.12 ms，中位数为206.56、198.30、199.03 ms，P95为3205.70、3028.54、3101.36 ms。`[verified: result.json measurements中files／single的single_image_latencies_seconds]`

主计时从所需模型及DLL就绪开始，覆盖必要文件或已就绪像素到最终内存ASTC，包含预测、选参、实际编码以及续搜中的解码和质量门控。Unity导入、模型／DLL加载、最终输出审计与写盘另列。`[verified: result.json measurements.timings.scope；V3DeploymentTrial.run]`

文件输入批量模式对整集预测，像素就绪批量模式按8图分组后聚合。两个口径的时间差同时包含输入边界与分组粒度的影响。`[verified: v3_confirmation.py L233–274；opinion: 时间差解释]`

## 结论解读

块大小匹配率衡量最终参数与原Unity标签的一致性，完整配置匹配还要求Quality相同，严格质量通过率衡量最终解码像素是否满足原生门槛。放宽和最高PSNR回退均保留原始分支身份。`[verified: 主评分rows.json；UnityV3Policy.search、strict_quality]`

逐张配对后，续搜保留1829张正确起点，纠正124张起点错误，新增0张错误，仍有47张块大小未匹配。`[verified: 主评分rows.json starting_decision、original_selection、footprint_match]`

原标签严格合格1768张，系统严格合格1772张，相对原标签严格质量回退0张。当前严格未通过228张，按原标签分支分组，其中放宽分支186张，最高PSNR回退42张。`[verified: 主评分rows.json strict_quality_met、original_selection.selection_reason]`

47张块大小未匹配图中，系统使用更小块47张，更大块0张。相对原标签payload变化为+0.1796%。`[verified: result.json summary.smaller_block_images、larger_block_images、payload_ratio_to_original]`

原标签12×12占1481／2000张，四类平均召回率为95.12%。法线仅13张，Linear仅16张。`[verified: result.json summary.per_class、balanced_accuracy、groups]`

各用途的泛化判断应结合当前样本量，法线和Linear的覆盖仍有限。`[opinion]`

本轮确认结果用于评价已冻结系统。确认集尺寸分布及实际编码次数共同影响每图耗时，读图准备、模型预测和所有试压编码成本应结合计时分段阅读。`[opinion]`

开发验证1000图共238,941,165像素，平均0.239百万像素／图。独立确认2000图平均1.011百万像素／图，为开发验证平均像素数的4.23倍。`[verified: V3 source-manifest.json splits.validation target_width、target_height；主评分rows.json width、height]`

本次输出质量审计复算最终选中ASTC，查询轨迹保留运行时实际测得的候选质量。20候选整体质量RMSE需完整候选监督，本报告按当前实际测量范围解释误差。`[verified: result.json outputs_manifest及trace；opinion: 误差解释范围]`

## 结果图

![独立确认结果](<E:/ASTC_Compression/experiment report/unity-v3-confirmation-20261116/figures/test-results.png>)

![独立确认耗时](<E:/ASTC_Compression/experiment report/unity-v3-confirmation-20261116/figures/test-timing.png>)

## 证据与核验

12个正式计时单元、每单元2000图覆盖与有序原标签复核通过。重新核验16008份选中输出、行记录及预测文件，并核验12份查询轨迹和12份重复预测档案。模型参数与buffer保持验收前状态。`[verified: result.json；report-verification.json；outputs.json清单逐项SHA核对]`

执行证据保存在同目录execution-config-v2.json、authorization.json、preparation.json、smoke-verification.json、execution-seal.json和result.json。原始ASTC、PNG、NPZ与查询轨迹位置由result.json各outputs_manifest、trace和predictions_archive定位。`[verified: 对应文件与result.json measurements]`

- `astcenc-avx2-shared.dll`的SHA-256为`e78f35b6fc12654118b97a3edf6e0785dbdf865131abdd730963f6d2e6d32d64`。`[verified: 共享seal identity.files_sha256]` [库文件](<F:/MLBB_Test/haijiangli1_HAMSTERMLBB/Assets/Editor/Astc/Plugins/astcenc-avx2-shared.dll>)
- `unity_astc_quality.dll`的SHA-256为`445e037d1aa598527e38b0fa0ae3418a1926fe47339ddd2888a196960f6e41f3`。`[verified: 共享seal identity.files_sha256]` [库文件](<E:/ASTC_Compression/experiment report/.local/unity-accuracy90-20261111/unity-quality-native-retry1/build/Release/unity_astc_quality.dll>)

pixels_ready阶段按8图分组运行，progress.json中的completed_images为当前组内进度。完整2000图覆盖由聚合后的全局source_index、查询轨迹及输出清单核验。`[verified: v3_confirmation.py L237–274；report-verification.json]`
