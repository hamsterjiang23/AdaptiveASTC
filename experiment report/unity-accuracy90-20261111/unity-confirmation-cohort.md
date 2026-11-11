# Unity 独立确认集的源资产预留

已预留2000张主名单和500张备用，主名单覆盖1227个未出现在9份历史清单中的资产组。2500张实际源文件的MD4、SHA-256、字节数及meta SHA均已再次核对，路径／资产组／源MD4与历史清单交集均为零。当前状态是源身份`reserved`，尚无此批的Unity参考像素、同次搜索标签或模型测试结果。`[verified: unity-confirmation2000-v1.json primary_images、primary_groups、reserve_images、status；unity-confirmation-reservation-verification.json source_and_meta_identities_rechecked、path_group_source_md4_overlap；opinion: 完成边界]`

## 隔离范围与选择方式

既有GDC test2000已有观察结果，只作历史对照。新确认集排除9份内容不同的历史源清单中的全部划分，覆盖26758个唯一资产路径和2484个资产组；不只排除当前train／validation。冻结输入与SHA见[配置](unity-confirmation2000-v1-config.json)，清单及其指纹保存在报告指向的`.local`目录。`[verified: V1“目标与开发数据”；unity-confirmation2000-v1-config.json excluded_manifests；unity-confirmation2000-v1.json historical_unique_assets、historical_unique_groups、manifest_sha256]`

候选来自183051条参数快照，但选择只读取路径和源文件MD4，不读取blockSize、PSNR或其他压缩质量字段。先排除历史资产组、路径和相同源内容，再按`SHA256("unity-confirmation-v1|20261112|" + casefold路径)`排序，核对磁盘源文件与meta；前2000张为主名单，后500张为备用。组名统一大小写，Characters／Monster／Environment沿用角色级分组，其他路径沿用父目录及SD／HD／FHD合并规则。`[verified: confirmation.py reserve、asset_path、asset_group；splitting.py DatasetSplitter.asset_group；unity-confirmation2000-v1-config.json seed]`

| 检查阶段 | 数量与处理 |
|---|---|
| 快照条目 | 183051；身份预筛后12753条进入实际文件检查候选序列。`[verified: unity-confirmation2000-v1.json source_entries、eligible_before_file_checks]` |
| 已有资产组 | 排除169830条。`[verified: unity-confirmation2000-v1.json exclusions.historical_group]` |
| 历史相同源MD4 | 额外排除326条。`[verified: unity-confirmation2000-v1.json exclusions.historical_source_md4]` |
| 非工程Assets路径 | 排除142条，例如Packages资源。`[verified: unity-confirmation2000-v1.json exclusions.outside_project_assets]` |
| 源文件或meta缺失 | 在遍历到的候选中排除1513条。`[verified: unity-confirmation2000-v1.json exclusions.missing_source_or_meta]` |
| 当前源MD4与快照不同 | 在遍历到的候选中排除344条。`[verified: unity-confirmation2000-v1.json exclusions.source_md4_changed]` |
| 已选路径或源内容重复 | 在遍历到的候选中排除208条。`[verified: unity-confirmation2000-v1.json exclusions.duplicate_selected_identity]` |

后面三项是取得2500张前实际遍历到的排除数，不代表12753条全部查完。原始排除路径和原因保存在名单的`rejected`中；没有按预测错误或质量违规剔除样本。`[verified: confirmation.py reserve循环的停止条件、manifest.rejected；opinion: 数量解释]`

## 实现、执行与复核

入口是[prepare_unity_confirmation.py](../../script/prepare_unity_confirmation.py)，实现是[UnityConfirmationCohort](../../reproductions/unity_search_baseline/confirmation.py)。配置和历史清单在开始／结束均校验SHA，输出目录拒绝复用，公开报告使用独占创建；失败重试使用新身份。仅预留源资产，不启动Editor或CUDA。`[verified: confirmation.py __init__、verify_inputs、reserve；prepare_unity_confirmation.py main]`

```powershell
uv run python script/prepare_unity_confirmation.py --config "experiment report/unity-accuracy90-20261111/unity-confirmation2000-v1-config.json"
```

上面是已执行入口。原输出保留后重跑会被拒绝；复现实验须复制配置并指定新的output／report，保留相同输入SHA、seed及候选规则。`[verified: confirmation.py __init__；opinion: 复跑要求]`

首次20图预检因快照包含Packages路径而失败，保留[失败报告](unity-confirmation-smoke20-v1.json)。修订为显式统计工程范围后，完成20图预检；审查又补强公开报告的独占创建和特殊资产组的大小写归一化，最终[20图复跑](unity-confirmation-smoke20-v3.json)及[2000＋500正式预留](unity-confirmation2000-v1.json)成功。正式预留内部47.03秒、完整进程52.71秒。`[verified: unity-confirmation-smoke20-v1.json error；unity-confirmation-smoke20-v3.json status；unity-confirmation2000-v1.json wall_seconds；unity-confirmation-reservation-verification.json reservation_process_seconds]`

[16项CPU测试](../../tests/test_unity_confirmation.py)覆盖历史test组排除、相同源内容排除、确定性排序、变更输入拒绝、缺失／修改源文件、越界路径、不可覆盖、并发报告占用，以及三类特殊组的大小写。另从9份历史清单重建隔离集合，对全部2500源文件和meta独立复核，检查名单指纹与排序，见[复核记录](unity-confirmation-reservation-verification.json)。此次没有模型forward或新训练。`[verified: test_unity_confirmation.py；unity-confirmation-reservation-verification.json historical_manifests、source_and_meta_identities_rechecked、test_opened、training_updates]`

## 后续验收约束

- 主名单和备用顺序现在冻结。仅在预测前按已声明的身份失败或像素重复规则替换，并保留原条目、原因与替换链；不得按标签、质量或模型错误筛样。`[opinion]`
- 先完成Unity导入后参考像素和同次原始搜索标签采集，保留原搜索提前停止、配置、失败及恢复记录；当前开发采集入口的train／validation限制保持，新确认集需独立受控入口。`[opinion]`
- 源MD4隔离不能排除不同文件编码、不同导入配置形成的相同或近重复像素。须将导入后参考图与历史开发数据及确认集内部做像素重复审计，并记录其影响；目前`native_pixels_audited=false`。`[verified: unity-confirmation2000-v1.json native_pixels_audited；opinion: 隔离边界与后续要求]`
- 最终模型、决策阈值和输入协议冻结后才打开确认集预测；逐类结果、原规则一致率、质量、真实payload和完整成本一起报告。不能把2000张名单已预留写成独立测试已通过，也不能把该名单的自然分布准确率与人工配比的旧test2000混用。`[opinion]`
