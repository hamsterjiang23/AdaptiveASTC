# Unity 原生 patch 语料合并

冻结的11个已发布批次已完成2370图目标提取及统一清单组装：2368张train、2张validation，共15619个patch、47400候选。20候选逐通道误差重建原生PSNR的最大差为3.772e-6dB；这些是数据验证，尚无Unity模型训练准确率。完整开发划分要求10000／1000，目前标记partial。`[verified: unity-patch-batches2370.json counts、patch_counts；unity-patch-assembly2370.json candidate_count、max_psnr_reconstruction_error_db、coverage、training_updates；opinion: 完成边界]`

## 实现与复跑

入口为[assemble_unity_patch_corpus.py](../../script/assemble_unity_patch_corpus.py)，实现为[UnityPatchCorpusAssembly](../../reproductions/unity_search_baseline/patch_assembly.py)，配置见[2370图组装配置](unity-patch-assembly2370-config.json)。读取已完成准备报告及外部SHA，沿队列配置、原参考计划、源划分逐级验证身份，再逐批验证corpus哈希、RGBA参考图、20×4通道目标和原生图级质量。`[verified: patch_assembly.py frozen_json、run L60–80、L152–155；unity-patch-assembly2370-config.json]`

```powershell
uv run --frozen python script/assemble_unity_patch_corpus.py --config "experiment report/unity-accuracy90-20261111/unity-patch-assembly2370-config.json"
```

现有输出不可覆盖；复跑须复制配置并使用新的output和report，输入SHA继续绑定相同冻结报告。合并只创建新清单，共享既有参考PNG与目标NPZ，保留原批次来源／绑定／行索引，按原始source manifest顺序重排。重复、跨划分、未知资产、held-out重叠和不完整准备报告均拒绝；只有真实计数等于完整源划分才能标记complete。`[verified: patch_assembly.py run L60–80、L152–155；test_unity_patch_assembly.py；opinion: 复跑要求]`

## 检查与成本

先在64训练图／2验证图上完成合并与完整CPU DataLoader遍历，再扩展到2370图。并发审查发现两类覆盖风险：输出目录抢占、报告路径别名或并发覆盖；修复采用独占目录建立、暂存后无覆盖硬链接发布，并新增真实并发回归。15项合并测试通过，原小语料与两版源码归档保留。`[verified: unity-patch-assembly66.json；unity-assembly66-dataset-audit.json；unity-patch-assembly66-v2.json；test_unity_patch_assembly.py；review C1–C3复查]`

| 操作 | 实测范围与耗时 |
|---|---|
| 2370图分批提取 | 2368／2图、15606／13patch；包含来源重新核验及已完成语料复用，循环1205.56秒、进程1208.54秒。`[verified: unity-patch-batches2370.json wall_seconds；jobs/unity-patch-batches2370/receipt.json]` |
| 66图首轮合并 | 781／13patch，组装3.30秒；随后794个patch的完整Dataset检查通过，0次训练更新。`[verified: unity-patch-assembly66.json；unity-assembly66-dataset-audit.json corpora、training_updates]` |
| 66图输出发布修复复查 | 独立输出身份，组装2.45秒、进程5.53秒；只核验发布路径，不作为速度改进结论。`[verified: unity-patch-assembly66-v2.json；jobs/unity-patch-assembly66-v2/receipt.json；opinion: 计时解释]` |
| 2370图合并 | 全部分批corpus和合并后的train／validation均经Dataset构造检查，组装36.02秒；随后完整15619patch的CPU DataLoader检查通过，耗时78.85秒，0次训练更新。`[verified: unity-patch-assembly2370.json wall_seconds；patch_assembly.py run；unity-assembly2370-dataset-audit.json corpora、wall_seconds、training_updates]` |

## 后续范围

完整原参考／策略标签采集及20候选补测继续。Unity模型仍需学习非PSNR质量分支，并按原规则决策；不能把GDC四候选RGB开发准确率当作Unity生产验收。独立测试90%、质量／payload／完整延迟及最小达标模型均继续保留在goal内。`[verified: V1限制与待核实；unity-policy260-bound-v2.json matching_fields、psnr_only_footprint_matches；opinion: 后续工作]`
