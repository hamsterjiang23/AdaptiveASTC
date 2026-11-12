# Unity 原生参考像素重复审计

已核对冻结的7744张训练图和2张验证图。精确RGBA重复有5组、共10张，均在训练集内，组内原选中块大小／preset一致；仅比较RGB得到18组、共102张，其中13组Alpha不同，8组原选中配置不同。当前两张验证图没有精确重复，完整validation1000及confirmation2000仍待采齐后审计；本次没有改动划分或运行模型。`[verified: unity-pixel-identity-completed-v1.json counts、rgba、rgb_only；其details的rgba_groups、rgb_groups；opinion: 覆盖边界]`

| 范围 | 精确RGBA | 仅RGB诊断 |
|---|---|---|
| 唯一像素身份 | 7741 | 7662。`[verified: unity-pixel-identity-completed-v1.json rgba、rgb_only.unique_identities]` |
| 重复组／涉及图片 | 5／10 | 18／102。`[verified: 同上duplicate_groups、images_in_duplicate_groups]` |
| 跨划分重复组 | 0 | 0；本次validation只有2张。`[verified: 同上cross_split_groups、counts]` |

RGB相同的图片不能直接作为当前RGBA模型的重复输入删除。原生用途、Alpha参与方式和颜色空间仍需分别保留；原选中配置不同也不能仅凭本次分组归因于Alpha。本次重复统计用于数据诊断，冻结开发划分保持原样。`[verified: unity-pixel-identity-completed-v1.json splits_modified；pixel-identities.json rows.observed_options；opinion: 解释与处置边界]`

## 身份与实现

- 精确身份为解码后的`RGBA8 + width + height + SHA-256(RGBA bytes)`，另算RGB身份作为诊断。不同PNG压缩方式可对应同一像素身份；相同字节流、不同宽高不视为相同输入。`[verified: ../../reproductions/unity_search_baseline/pixel_identity.py pixel_identity；../../tests/test_unity_pixel_identity.py]`
- 每批绑定原参考receipt、实际回调receipt、原导入phase receipt及归档manifest的SHA；验证成功退出、metadata／托管源码恢复、图片数量／顺序／划分，以及每份原生PNG哈希。PNG显示行序的RGBA用于分组；翻转上下行后的SHA独立核对encoder callback，RGB显示顺序哈希核对原参考receipt。`[verified: pixel_identity.py bound_json、batch_rows；../../reproductions/unity_search_baseline/metadata.py L253–255]`
- 不做缩放、裁剪或感知哈希匹配，没有近重复保证；公开报告明确`independent_test_isolation_proven=false`。确认集将来仍须与完整开发及历史已用输入比较，像素隔离与模型冻结／最终测试分别验收。`[verified: pixel_identity.py run scope、independent_test_isolation_proven；opinion: 后续验收]`
- 仅读取明确列出的已完成归档。本次快照指7746张已完成图，不代表整个计划11000张开发图。报告路径必须在原始输出目录之外，独占创建阻止并发覆盖同一公开身份。`[verified: unity-pixel-identity-completed-v1-config.json batches、expected_counts、snapshot_provenance；pixel_identity.py run；opinion: 覆盖解释]`

## 实测与修正

首次66图运行因为遗漏PNG与callback的上下行差异而失败，保留[首次报告](unity-pixel-identity-smoke66-v1.json)和原始错误日志；方向修正后[66图检查](unity-pixel-identity-smoke66-v2.json)成功，完整进程2.06秒。随后[7746图审计](unity-pixel-identity-completed-v1.json)成功，内部74.43秒／进程74.64秒。`[verified: 对应jobs/receipt.json status、wall_seconds、process_exit_code；公开报告wall_seconds]`

代码复审另修复明细／报告路径别名及并发覆盖两个输出问题，最终21项CPU测试通过；[最终66图检查](unity-pixel-identity-smoke66-v3.json)进程1.49秒。7746图运行实际使用分离的报告路径，方向修正后的执行源码已归档，SHA与当时报告一致；后续输出保护改动没有回写历史结果。首次并发测试夹具重复等待屏障，修正夹具后21项全通过。`[verified: test_unity_pixel_identity.py；unity-pixel-identity-verification.json tests、executed_source_sha256、current_source_sha256、jobs；opinion: 历史源码范围]`

原始逐图身份、重复组成员索引、执行源码和日志保存在`experiment report/.local/unity-accuracy90-20261111/unity-pixel-identity-completed-v1/`及对应`jobs/`目录；公开报告保存明细与输入SHA。运行只有CPU文件读取和哈希，没有训练、推理或最终编码，耗时属于数据审计成本。`[verified: unity-pixel-identity-completed-v1.json details、details_sha256、inputs_sha256、training_updates；opinion: 成本范围]`

## 复跑

入口为[原生像素审计](../../script/audit_unity_pixel_identity.py)，实现为[UnityPixelIdentityAudit](../../reproductions/unity_search_baseline/pixel_identity.py)。复制[配置](unity-pixel-identity-completed-v1-config.json)并给出新的`output`与`report`，保留原SHA或明确生成下一份完成批次快照；已使用的输出会被拒绝。`[verified: pixel_identity.py __init__、run；opinion: 复跑方式]`

```powershell
uv run python script/audit_unity_pixel_identity.py --config "path/to/new-pixel-audit-config.json"
```

检查记录见[验证文件](unity-pixel-identity-verification.json)。本次结果没有证明完整确认集隔离，也没有提供新模型准确率。`[verified: unity-pixel-identity-verification.json；opinion: 验收边界]`
