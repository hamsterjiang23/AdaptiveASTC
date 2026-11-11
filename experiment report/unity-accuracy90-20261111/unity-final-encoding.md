# Unity 保存预测到最终 ASTC 的编码核验

已完成两张开发验证图的实际编码闭环：按已完成原生小样本训练的冻结预测，各编码一次选中的块大小和preset，再执行固定8×8／medium对照。两条路径共四次新编码，完整ASTC字节、解码像素、原生质量及payload均与对应候选一致。这是mip0最终编码阶段的检查，完整Unity训练、独立测试90%及包含模型推理的端到端计时仍未完成。`[verified: unity-final-encoding-smoke2-v2.json rows、summary、timing_scope；opinion: 完成边界]`

## 可复跑入口与输入

入口为[encode_unity_predictions.py](../../script/encode_unity_predictions.py)，实现为[UnityFinalEncoding](../../reproductions/unity_search_baseline/final_encoding.py)。使用`uv run --frozen python script/encode_unity_predictions.py --config <新的配置路径>`；以[本次配置](unity-final-encoding-smoke2-v2-config.json)为模板，修改输出和报告到新的身份。执行源码变化时重新绑定SHA，已有结果禁止覆盖。`[verified: final_encoding.py execution_sources、prepare、run；opinion: 复跑要求]`

来源为`unity-native-smoke8-v1`的8训练图／2验证图、两轮4次更新的模型；本次仅使用其两张已保存验证预测，没有再次训练或运行模型forward，没有读取test。该模型仅为小样本执行检查，不将结果解释为生产泛化效果。`[verified: unity-native-smoke8-v1.json config、training_updates；unity-final-encoding-smoke2-v2.json training_scope、training_updates、test_opened；opinion: 解释范围]`

启动前校验完成报告、最佳checkpoint／预测／决策三个SHA、重载审计、冻结corpus和原搜索策略。用已保存的20候选预测重新执行原规则，必须复现已保存决策；实际编码只执行选中配置。候选原采集的DLL、实际RGBA回调哈希、Alpha、profile、normal-pack和法线评价mip范围保持。参考PNG送入DLL前翻转到原回调方向，输出PNG再翻回可视方向。`[verified: final_encoding.py prepare、candidate_source、encode_image；test_unity_final_encoding.py]`

## 实际结果

| 路径 | 新编码次数 | 合计payload | 严格质量通过 | DLL编码时间合计 |
|---|---:|---:|---:|---:|
| 保存预测选中的配置 | 2 | 59,168字节 | 1／2 | 0.02125秒。`[verified: unity-final-encoding-smoke2-v2.json summary.prediction]` |
| 固定8×8／medium | 2 | 81,920字节 | 2／2 | 0.03218秒。`[verified: unity-final-encoding-smoke2-v2.json summary.fixed8]` |

首图预测6×6／thorough，第二图预测12×12／fastest。第二图的真实质量没有通过完整门槛，报告保留该失败，没有通过追加搜索或回退改写预测结果。原策略本身的大图放宽接受与严格质量通过分别记录。实际小样本只覆盖两张sRGB颜色图；法线参数与多级角度路径经过合成接口检查，真实法线最终编码扩展仍待执行。`[verified: unity-final-encoding-smoke2-v2.json rows；test_unity_final_encoding.py；opinion: 范围边界]`

完整任务进程4.05秒，编码审计内部0.81秒，原始记录位于`experiment report/.local/unity-accuracy90-20261111/jobs/unity-final-encoding-smoke2-v2/receipt.json`。报告逐图分开记录参考图加载、DLL编码、DLL解码、编码解码wrapper及质量计算，wrapper覆盖其内部调用，不将两者相加。没有模型推理和整条mip链编码计时，不从这次单轮、并发运行的小样本推导部署加速比。`[verified: 对应job receipt wall_seconds；unity-final-encoding-smoke2-v2.json wall_seconds、rows、model_inference_seconds、end_to_end_seconds；opinion: 成本解释]`

## 检查与修订记录

- 40项相关CPU检查通过；初次跳过的两项原生指标测试，随后显式指定`UNITY_QUALITY_RECEIPT`并补跑，两项均通过，合计42项。检查包含每图每路径一次编码、方向／Alpha／profile、法线mip深度、输入与候选篡改、质量失败及构建身份；真实两图编码另由上述闭环覆盖。`[verified: 本轮pytest 40 passed、2 skipped及原生补跑2 passed；test_unity_supplement.py L21–23；unity-final-encoding-smoke2-v2.json]`
- 首轮[smoke2-v1](unity-final-encoding-smoke2-v1.json)也完成四次编码，进程3.85秒。随后审查发现质量DLL构建记录仅自校验，未与原采集的完整构建身份比较；修订后要求两者完全相等，增加替换构建与DLL篡改回归，再以v2独立身份重跑通过。原v1的十份执行源码归档在`experiment report/.local/unity-accuracy90-20261111/unity-final-encoding-smoke2-v1-source`，原结果保留为历史记录。`[verified: v1/v2 reports inputs_sha256；final_encoding.py bound_quality_receipt；对应jobs receipts；opinion: 历史解释]`
- 训练和原生数据队列使用的冻结源码保持。后续在完整模型上复用此入口时，还需单独接入实际预处理／forward／决策计时，并扩展到独立测试及对应的完整最终编码范围。`[verified: 本轮冻结源码SHA核验；opinion: 后续验收要求]`
