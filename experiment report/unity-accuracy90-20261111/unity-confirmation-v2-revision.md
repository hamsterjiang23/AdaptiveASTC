# V2 确认集范围修正与重新采集

用户批准按 V2 的输入范围替换原确认集中的 47 张图，保留原名单与失败记录，按原备用顺序补齐 2000 张，并重新检查名单及像素隔离。新名单为 [unity-confirmation2000-v2.json](unity-confirmation2000-v2.json)，配置与原名单 SHA 均在报告中绑定。`[verified: 用户本次选择“按 V2 范围替换”；对应报告 prior、manifest_sha256]`

## 本次名单变化

| 检查项 | 结果 |
|---|---|
| 主名单 | 保留1953张原图及其位置，47个空位按原备用顺序补齐，仍为2000张。`[verified: unity-confirmation-v2-readiness.json retained_primary、replaced_primary、source_eligibility.replacement_order_independently_verified]` |
| 排除条件 | 39张GUI、7张Cube，以及1张不属于上述两类的HDR源图。HDR源扩展名共5张，其中4张同时属于Cube，不能将重叠原因直接相加。`[verified: unity-confirmation2000-v2.json primary_exclusion_reasons_overlapping；revision-audit.json inspections]` |
| 备用名单 | 原500张备用先排除12张范围外图，再使用47张，剩余441张。`[verified: unity-confirmation2000-v2.json reserve_images、inspected_sources、eligible_readable_sources；revision-audit.json]` |
| 源文件检查 | 核对全部2500份源文件MD4／SHA-256与meta SHA；2441张范围内图片均成功读取RGB像素。旧格式缺失的metadata字段不猜测为GUI或Cube。`[verified: confirmation_revision.py inspect；unity-confirmation2000-v2.json inspected_sources、eligible_readable_sources]` |
| 历史隔离 | 新主名单覆盖1231个资产组；主名单与剩余备用均重新检查9份历史清单，路径、资产组和源MD4重叠为0。`[verified: unity-confirmation2000-v2.json primary_groups、historical_asset_group_source_md4_overlaps；配置 excluded_manifests]` |
| 选择依据 | 只使用输入类型、文件可读取性与冻结身份；不使用质量、块大小标签或模型输出。原规则、编码器及开发集38份冻结源码均未改动。`[verified: confirmation_revision.py inspect、replace、revise；unity-confirmation-v2-readiness.json development_sources_unchanged]` |

原名单及258张成功归档、后续失败批次均保留。失败批次的Unity原始导入已完成，随后源HDR的Pillow读取导致归档失败；此前成功批次也包含GUI，因此不把旧258张直接计入新V2名单的完成数。新名单使用新的任务身份重新采集。`[verified: unity-confirmation-v2-readiness.json prior_confirmation_series；旧series及from00258报告；opinion: 完成口径]`

## 新的执行链

1. [两图原生预检](unity-confirmation-capture-smoke2-data-v2-config.json)：沿用已核验的Editor／DLL／原搜索配置，绑定新名单；只依赖已完成的开发数据，不等待训练。`[verified: 对应配置 reservation_report、development_series、dependencies]`
2. [2000张串行采集](unity-confirmation-series2000-data-v2-config.json)：两图预检通过并复核后，按256张批次继续，保留原搜索提前停止、实际属性和标签。`[verified: 对应配置 smoke_config、batch_size、expected_images；confirmation_series.py run]`
3. [13000张像素审计](unity-pixel-pipeline-full13000-data-v2-config.json)：等待新确认集采集完成，检查train10000／validation1000／confirmation2000精确RGBA和同尺寸对齐近重复；继承已通过的66图预检。`[verified: 对应配置 expected_counts、confirmation、smoke_provenance]`

名单修订阶段只完成源文件层面的准入检查。实际导入后的Default／Sprite／NormalMap、Tex2D、RGBA、颜色空间及参考像素一致性另行逐批验证，源身份无重叠不能证明像素独立。确认集不补测全20候选，不训练、不推理；Goal待完整采集、像素审计和交接完成后结束。`[verified: unity-confirmation-v2-readiness.json native_input_eligibility_verified、native_pixel_isolation_audit_complete、training_updates、test_opened、goal_complete；unity_capture_input.py project；opinion: 验收边界]`

## 采集进度（2026-11-12 09:07 UTC）

新版已归档258／2000张，两图预检及首个256张批次均通过，实际输入检查覆盖全部258张：251张Default、5张Sprite、2张NormalMap。256张批次完整采集1479.70秒，原生候选回调1479次；退出码0、无导入错误或meta恢复冲突，临时采集源码恢复到原SHA。下一批从索引258继续；13000张完整像素审计仍等待，尚未完成数据Goal。`[verified: unity-confirmation-series2000-data-v2.json；unity-confirmation-v2-input-audit.json texture_types、images；from00002报告wall_seconds、options_audit、managed_source_restoration；对应batch-receipt.json]`

收尾验收增加对像素审计原始明细、实际名单、PNG／patch目标文件及最终输入哈希的核对；观察脚本以同一份清单字节计算哈希并解析，缓存同时冻结实际导入属性。旧观察脚本和部分结果保留，原采集进程与冻结源码未重启或修改。[收尾检查准备记录](unity-data-delivery-verifier-readiness.json)的未完成任务拒绝检查已通过；完整交付检查要等采集、像素审计和观察进程全部完成后运行。`[verified: unity-data-delivery-verifier-readiness.json checks、completion_checks、observer_corrections、full_data_verification_executed；opinion: 完成边界]`

## 复跑与检查

入口为`uv run python script/revise_unity_confirmation.py --config <新配置路径>`，新配置必须使用尚不存在的输出目录与报告；原配置和输出不覆盖。替换映射与逐图预检保存于报告指向的`.local/revision-audit.json`。`[verified: script/revise_unity_confirmation.py main；confirmation_revision.py revise；confirmation.py __init__]`

格式、lint和类型检查通过；名单预留与修订共23项CPU测试通过，另独立重算47个替换位置与备用顺序一致。新采集配置、系列配置和像素管线构造／来源绑定检查通过，三项任务已启动，启动记录见[预检记录](unity-confirmation-v2-readiness.json)；这些检查不表示新2000张已经采完。`[verified: unity-confirmation-v2-readiness.json checks、jobs、source_eligibility；opinion: 验收边界]`
