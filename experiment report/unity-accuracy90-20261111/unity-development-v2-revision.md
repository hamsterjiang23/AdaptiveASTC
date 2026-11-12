# V2 开发集18张替补与新版本交接

补采等待任务已实际启动，状态为waiting_confirmation。确认集完成后自动调用原采集入口；运行前和等待期间核对43份执行源码及冻结配置。启动进程、预检、10项测试和407个本地链接检查保存在[启动验收记录](unity-development-v2-revision-readiness.json)。`[verified: unity-development-replacement18-queue-v2.json status；unity-development-v2-revision-readiness.json processes、execution_sources_verified、checks]`

用户已批准替换原开发语料的18张Cube：训练13张、验证5张，保持10000／1000规模。原图片、搜索标签、候选测量、成本和语料不覆盖。原始范围问题及全11000张输入检查见[范围检查](unity-development-v2-input-scope.md)。`[verified: 用户本轮补采选择；unity-development-v2-input-all11000.json accepted、rejected、cohort_modified]`

[新版名单](unity-development-cohort-v2.json)已冻结，18张替补来自18个新资产组。保留原名单位置，只替换批准的18个位置，旧test／calibration行保持；完整新版源名单和仅18张补采名单分别保存并绑定SHA。当前仅完成身份预留，尚未完成18张原生采集或新语料验收。`[verified: unity-development-cohort-v2.json files、replacements、replacement_groups、counts、native_capture_complete；独立名单核对输出]`

选择规则为固定seed与路径的SHA-256排序。排除全部历史名单及当前确认集主名单／备用名单的路径、资产组、源MD4，候选之间也不重复资产组或源MD4。源准入要求明确的Default／Sprite／NormalMap、Tex2D元数据、非HDR／EXR源、可读RGBA及匹配源MD4；随后仍检查实际导入属性。历史blockSize仅为旧采集清单结构所需的字段，不参与替补排序、准入或新标签生成。`[verified: development_revision.py reserve、inspect；unity-development-cohort-v2.json selection、selection_uses_quality_or_labels；opinion: 实际导入仍须验收]`

| 工作 | 入口与完成条件 |
|---|---|
| 新名单与旧位置映射 | [名单报告](unity-development-cohort-v2.json)与[配置](unity-development-cohort-v2-config.json)，已完成13／5身份替换，原始数据未改动。`[verified: 报告replacement_counts、replacements、original_data_modified]` |
| 原生补采 | [补采队列配置](unity-development-replacement18-queue-v2-config.json)等待当前confirmation2000任务成功后，调用[18张采集计划](unity-development-replacement18-series-v2-config.json)，分13张训练、5张验证两批，继续原搜索及同次标签／计时，采后实际输入适配器核对。`[verified: 队列配置dependency、reference_plan、capture_job；development_capture_queue.py run]` |
| 候选与patch目标 | 补采完成后沿用已有20候选补测和patch流程，补测成本单列，新候选与参考图绑定。`[opinion: 待执行]` |
| 新版开发语料 | 复用10982张已通过输入核对的图片和目标，在批准的18个位置加入补采结果；重新运行Dataset全读、原规则重放、实际输入检查和完整像素审计。`[verified: unity-development-v2-input-all11000.json accepted；opinion: 待执行]` |

名单逻辑已通过10项测试、格式、lint及类型检查。审查发现并修正了输出身份保护问题：报告不能覆盖本地名单，两个预构造任务不能覆盖同一公开报告。实际名单产生时使用独立公开报告，文件SHA均核对一致，产生时的源码已归档并由producer_source绑定。采集计划的只读验证和队列来源绑定检查通过；这些检查不代表18张已经采完。`[verified: 本轮pytest“10 passed”、ruff、basedpyright输出；独立审查C1／C2关闭；unity-development-cohort-v2.json files、producer_source、source_sha256；本轮reference_validation／queue_bindings输出]`

确认集采集继续使用已批准的2000张名单。原13000张像素审计队列保留为修订前范围的记录；最终交接需对新版开发语料与确认集重新绑定并审计。Goal仍只完成数据交接，训练和90%模型验收由后续V2执行。`[verified: unity-data-handoff.md本Goal完成条件；用户本轮补采选择；opinion: 修订审计边界]`
