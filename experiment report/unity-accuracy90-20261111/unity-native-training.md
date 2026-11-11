# Unity 原生 CUDA 训练链路

随机初始化的原生质量模型已完成8张训练图／2张验证图的CUDA小样本闭环：2轮、4次实际更新、0次AMP跳步，最佳权重重载与保存预测一致。完整进程23.81秒，训练器含数据准备与复核19.28秒；这只证明执行链路可用，完整Unity训练和独立测试90%尚未完成。`[verified: unity-native-smoke8-v1.json status、history、checkpoint_audit；unity-native-smoke8-v1-result.json process_seconds；opinion: 验收边界]`

## 入口与冻结范围

运行入口为[train_unity_quality.py](../../script/train_unity_quality.py)，本次配置为[smoke8配置](unity-native-smoke8-v1-config.json)。复跑必须更换output、report和job身份，已有目录及报告拒绝覆盖。训练器要求CUDA，未实现CPU训练回退。`[verified: script/train_unity_quality.py main；training/unity_quality_trainer.py run、fit]`

```powershell
uv run --frozen python -u script/train_unity_quality.py --config <新的配置文件>
```

输入绑定已冻结的2370图部分语料SHA；训练只取索引0、1、2、64、65、216、706、707，按输入属性覆盖sRGB、Linear、参与评价的Alpha、mip0法线和多级法线评价。验证使用该语料原有2图，不访问test或calibration。正式训练入口要求coverage=complete、实际train10000／validation1000且与完整预期一致，不能把这份部分语料标为正式训练。`[verified: unity-native-smoke8-v1-config.json；unity-native-smoke8-v1-result.json sampled_input_kinds；UnityQualityTrainer.validate_coverage；test_unity_quality_training.py]`

## 训练与监督协议

- 每轮将选中图像打乱并各访问一次，每图有放回抽4个原尺寸patch；这不同于GDC成组实验中图像本身也有放回的抽样方式。整图头接受所抽patch的聚合特征，以完整图的零误差通道及MS-SSIM／角度为监督，是抽样输入下的整图预测假设。`[verified: unity_image_bags.py __getitem__；unity_quality_trainer.py fit；opinion: 学习假设]`
- 模型为随机初始化ResNet-18原生适配，共11,377,660参数，FP32参数45,510,640字节。输入／输出定义沿用[原生模型报告](unity-native-model.md)，本次不增加层数或宽度，不使用预训练或图像变换增强。`[verified: unity-native-smoke8-v1.json config.parameters、fp32_parameter_bytes、initialization、augmentations；models/unity_quality.py]`
- AdamW学习率0.0003、weight decay0.05，1轮warmup后余弦，FP16 AMP、梯度范数上限5；三个附加损失权重均0.1，零通道概率门槛固定0.5。这个原生起点未启用EMA、资产组限权、单调输出或GDC新增聚合loss；后续配方变动使用新实验身份并单项比较。`[verified: unity-native-smoke8-v1.json config；UnityQualityTrainer.fit；opinion: 后续对照]`
- 验证覆盖每图全部patch，先聚合物理MSE，再结合预测零通道与整图质量套用原Unity规则。最佳权重按块大小准确率、再按颜色图近阈值RMSE选择；完整训练的早停使用该RMSE，本次两轮检查关闭patience。`[verified: UnityQualityTrainer.evaluate、fit；unity-native-smoke8-v1-config.json patience]`

## 实际执行与证据保护

| 检查 | 结果 |
|---|---|
| 训练更新 | 两轮各2次，合计4次；AMP跳步0。`[verified: unity-native-smoke8-v1.json history、training_updates]` |
| 分项loss | patch、零通道、MS-SSIM、角度四项均有限且实际参与；总loss两轮为1.39217／1.10580。`[verified: unity-native-smoke8-v1.json history[*].loss]` |
| 权重重载 | 选中epoch1；重载预测与保存数组在绝对容差1e-5内一致，决策完全一致。`[verified: unity-native-smoke8-v1.json checkpoint_audit；UnityQualityTrainer.audit_best]` |
| 显存与时间 | PyTorch峰值分配446,280,192字节；准备17.07秒，训练器19.28秒，进程23.81秒。与Unity采集并行，仅记录开发成本。`[verified: unity-native-smoke8-v1-result.json；opinion: 计时边界]` |
| 小样本预测 | 验证2图块大小命中1图、完整配置命中0图；两图原标签均12×12。该数值不用于选正式配方或声称泛化效果。`[verified: unity-native-smoke8-v1.json checkpoint_audit.metrics；opinion: 小样本限制]` |

检查点、预测数组和决策文件在选模时记录SHA，重载前后再次核验；配置和源码也必须一致。训练结束后重新核对选中训练图的参考／目标文件哈希，重建冻结验证Dataset，并重新绑定每张图原采集的策略来源。实际optimizer更新即时写入共享状态，失败报告保留已发生的更新次数。`[verified: UnityQualityTrainer.verify_artifacts、verify_input_files、audit_best、track_update；test_unity_quality_training.py]`

独立代码审查发现的三项问题——检查点事后替换、结束时输入未重新核验、异常中断少记更新数——均在首次CUDA启动前修复。新增训练检查与既有模型检查共35项通过，ruff格式／lint及basedpyright通过；原始训练日志、权重、预测、job receipt保存于.local，公开结果绑定SHA。`[verified: unity-native-training-verification.json；unity-native-smoke8-v1-result.json inputs_sha256；baseline_code_review C1–C3复核]`

## 后续验收

继续完成原生参考采集、20候选补测及完整训练清单，再按验证结果比较采样、目标权重和模型改进。最终仍需Unity独立测试Top-1≥90%，同时评价真实质量、payload和预处理／推理／最终编码成本；当前没有生产验收准确率。`[verified: V1“目标与开发数据”；unity-native-smoke8-v1.json status=passed_smoke；opinion: 后续范围]`
