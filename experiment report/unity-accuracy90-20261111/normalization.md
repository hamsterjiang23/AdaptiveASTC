# 固定权重的BatchNorm统计量诊断

原V1随机初始化、预训练及后续scratch低学习率三组诊断均已完成。每组读取完成训练的末轮last.pt，不更新任何学习参数，仅对BatchNorm的running mean／variance及计数做训练集重估；原始检查点保留。它是独立的训练后处理实验，不能与训练中选出的最佳epoch混为一组。`[verified: normalization-scratch.json；normalization-pretrained.json；normalization-scratch-lr0003.json；PatchNormalizationAudit.run/recalibrate；opinion: 比较边界]`

每个变体用相同seed抽取16384个原生训练patch，按图等期望权重、图内均匀采样，共128批；本次覆盖8066张训练图。重估不使用验证像素或标签，评估使用冻结validation1000。参数逐项一致性检查通过，optimizer更新0次，test未打开。`[verified: normalization-scratch.json calibration_patches、unique_training_images、rows.parameters_unchanged、optimizer_updates、test_opened]`

| 随机初始化末轮epoch14 | 验证Top-1 | 阈值附近RMSE |
|---|---|---|
| raw，原统计量 | 62.4% | 2.7289dB。`[verified: normalization-scratch.json rows[0]]` |
| raw，训练集重估统计量 | 70.5% | 2.2231dB。`[verified: normalization-scratch.json rows[1]]` |
| EMA，原统计量 | 48.3% | 5.5114dB。`[verified: normalization-scratch.json rows[2]]` |
| EMA，训练集重估统计量 | 76.7% | 1.6467dB。`[verified: normalization-scratch.json rows[3]]` |

这次固定EMA权重的重估使准确率提高28.4个百分点，说明该末轮EMA结果明显受BN统计量影响。重估后相比训练流程原先选出的epoch9 raw的76.0%提高0.7个百分点，仍未到90%。这不能解释随机初始化与预训练配方之间的全部差距，后续继续按固定容量的单项对照检查。`[verified: normalization-scratch.json rows；patch-v1/scratch-result.json；opinion: 结论范围与后续安排]`

重估后EMA的balanced accuracy为70.25%，质量达标率84.2%，payload93,352,736字节，参数量保持不变。两次BN重估各约125.5秒，含四次验证、输入核查和归档的内部墙钟395.73秒，整进程400.03秒。单进程数据读取与CUDA forward均计入重估成本。`[verified: normalization-scratch.json rows、wall_seconds；jobs/normalization-scratch/receipt.json]`

| 预训练末轮epoch14 | 验证Top-1 | 阈值附近RMSE |
|---|---|---|
| raw，原统计量 | 86.1% | 1.2943dB。`[verified: normalization-pretrained.json rows[0]]` |
| raw，训练集重估统计量 | 86.3% | 1.2436dB。`[verified: normalization-pretrained.json rows[1]]` |
| EMA，原统计量 | 81.3% | 1.3056dB。`[verified: normalization-pretrained.json rows[2]]` |
| EMA，训练集重估统计量 | 89.2% | 0.9512dB。`[verified: normalization-pretrained.json rows[3]]` |

预训练重估EMA的balanced accuracy为86.24%，四类召回90.83%／80.21%／78.91%／95.02%。相比训练原选中的88.8%提高0.4个百分点，仍未达到V1的90%／0.75dB。零余量质量达标率为87.3%，低于原选中模型的88.3%；payload89,813,696字节。余量0.5dB则准确率86.5%、质量达标91.1%、payload94,739,696字节。所有值来自同一开发validation，不能代替Unity独立验收。`[verified: normalization-pretrained.json rows[3].metrics；patch-v1/pretrained-result.json；opinion: 证据边界]`

预训练诊断内部墙钟419.17秒，整进程429.82秒。两组均保留所有四种变体，原始参数逐项一致，原checkpoint SHA未变；统计量重估是额外训练后成本，不计为零成本增益。`[verified: normalization-pretrained.json wall_seconds、rows.parameters_unchanged；jobs/normalization-pretrained/receipt.json；PatchNormalizationAudit.run；opinion: 成本口径]`

[执行探针](normalization-smoke.json)先通过48训练图／16验证图、2批重估；该探针只检查CUDA路径、状态恢复和无参数更新。报告、四种状态的权重、预测和抽样索引分别保存，raw／EMA原统计量的重载准确率及RMSE均与原末轮记录一致。`[verified: normalization-smoke.json；normalization-scratch.json rows；PatchNormalizationAudit.baseline_matches]`

```powershell
uv run --frozen python script/patch_normalization.py --training <已完成训练目录> --output <新的诊断目录> --report <新的报告.json> --calibration-batches 128
```

此入口只接受已完成开发训练且有EMA的检查点，复核原训练代码／corpus身份，拒绝覆盖旧输出。报告中的last-epoch身份、训练参数不变与统计量重估成本必须随后续结果一起保留。`[verified: PatchNormalizationAudit.run；opinion: 后续记录要求]`

## 后续随机初始化lr0.0003的末轮诊断

[低学习率诊断](normalization-scratch-lr0003.json)使用已完成epoch12的last.pt、相同16384个训练patch／8066图。四种变体学习参数均未改变，0次优化器更新，test未打开；内部墙钟402.01秒，进程419.26秒。`[verified: normalization-scratch-lr0003.json calibration_patches、unique_training_images、rows.parameters_unchanged、optimizer_updates、wall_seconds；.local对应jobs/normalization-scratch-lr0003/receipt.json]`

| epoch12变体 | 验证Top-1 | 阈值附近RMSE |
|---|---|---|
| raw，原统计量 | 71.3% | 2.1745dB。`[verified: normalization-scratch-lr0003.json rows[0].metrics]` |
| raw，训练集重估 | 73.3% | 2.1017dB。`[verified: normalization-scratch-lr0003.json rows[1].metrics]` |
| EMA，原统计量 | 49.6% | 4.7631dB。`[verified: normalization-scratch-lr0003.json rows[2].metrics]` |
| EMA，训练集重估 | 80.9% | 1.3716dB。`[verified: normalization-scratch-lr0003.json rows[3].metrics]` |

重估EMA的balanced accuracy为76.97%，四类召回88.99%／71.35%／60.94%／86.58%；质量达标率87.9%、payload95,148,832字节。相对本轮训练选中的epoch7 raw，准确率高0.2个百分点、10×10召回高6.25个百分点，但12×12召回更低，payload也更大。这是独立后处理结果，未达到V1的90%／0.75dB，不能代替Unity生产验收。`[verified: normalization-scratch-lr0003.json rows[3].metrics；patch-fixed-capacity/scratch-lr0003-result.json metrics；opinion: 比较范围]`

## 去maxpool的末轮诊断

[去maxpool诊断](normalization-scratch-stem2-lr0003.json)使用完成训练的epoch15权重，以同样16384个训练patch／8066张图重估统计量。四种变体均核对学习参数未改变，优化器更新0次；内部589.30秒，完整进程599.74秒，成本与CPU数据准备重叠。`[verified: normalization-scratch-stem2-lr0003.json epoch、calibration_patches、unique_training_images、optimizer_updates、rows.parameters_unchanged、wall_seconds；.local对应job receipt]`

| epoch15变体 | 验证Top-1 | 阈值附近RMSE |
|---|---|---|
| raw，原统计量 | 73.7% | 2.8858dB。`[verified: normalization-scratch-stem2-lr0003.json rows[0].metrics]` |
| raw，训练集重估 | 77.5% | 2.4997dB。`[verified: normalization-scratch-stem2-lr0003.json rows[1].metrics]` |
| EMA，原统计量 | 52.4% | 4.0869dB。`[verified: normalization-scratch-stem2-lr0003.json rows[2].metrics]` |
| EMA，训练集重估 | 78.6% | 2.1127dB。`[verified: normalization-scratch-stem2-lr0003.json rows[3].metrics]` |

重估EMA的balanced accuracy为73.73%、质量达标率87.1%、payload96,820,144字节。相同后处理下，标准stem配方为80.9%／1.3716dB，仍优于这次去maxpool结果；下一项资产组抽样对照沿用标准stem。这里比较各自完成训练的末轮后处理，训练轮数不同，不能归因为单独的BN效果。`[verified: normalization-scratch-stem2-lr0003.json rows[3].metrics；normalization-scratch-lr0003.json rows[3].metrics；opinion: 后续配方与比较边界]`
