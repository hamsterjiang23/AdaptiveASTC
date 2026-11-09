# 数据准备报告

清单指纹为`e6053c623cb61cf17cfc6df6050489ee52efb4052930089c38095348ee8d41a7`。`[verified: data_summary.json /fingerprint]`

| 集合 | 数量 | 类别数量 | 资产组数 | 证据 |
|---|---|---|---|---|
| test | 2000 | {'6x6': 455, '8x8': 324, '12x12': 956, '10x10': 265} | 168 | `[verified: data_summary.json /splits]` |
| calibration | 1000 | {'6x6': 227, '10x10': 133, '8x8': 162, '12x12': 478} | 147 | `[verified: data_summary.json /splits]` |
| validation | 1000 | {'12x12': 478, '6x6': 227, '10x10': 133, '8x8': 162} | 184 | `[verified: data_summary.json /splits]` |
| train | 10000 | {'8x8': 1621, '12x12': 4778, '10x10': 1328, '6x6': 2273} | 1305 | `[verified: data_summary.json /splits]` |

入选图片逐张MD4和解码检查通过，跨集合内容哈希、资产组及协议近重复检查通过。`[verified: data_summary.json /audit；prepare完成路径]`

近重复审计使用协议中的pHash、宽高比和RGB缩略图阈值；清洗、Alpha、preset和RDO分布见配套统计。训练输入为RGB源图，标签为LITE历史策略。`[verified: data_summary.json /splits、/table_config]`

## 清洗与复现范围

元数据候选为157626个唯一内容，正式入选14000张均经源文件MD4及解码检查。两次独立准备清单完全一致。`[verified: data_summary.json；data_reproducibility.json]`

| 项目 | 数量 | 证据 |
|---|---|---|
| deduplicated_records | 14574 | `[verified: data_summary.json /filter_counts]` |
| missing_records | 5597 | `[verified: data_summary.json /filter_counts]` |
| conflicting_hash_groups | 1480 | `[verified: data_summary.json /filter_counts]` |
| conflicting_records | 4179 | `[verified: data_summary.json /filter_counts]` |
| excluded_resource_records | 648 | `[verified: data_summary.json /filter_counts]` |
| unsupported_extension_records | 219 | `[verified: data_summary.json /filter_counts]` |
| excluded_smoke_hashes | 208 | `[verified: data_summary.json /filter_counts]` |
| rejected_unsupported_png_bit_depth | 180 | `[verified: data_summary.json /filter_counts]` |
| rejected_md4_mismatch | 230 | `[verified: data_summary.json /filter_counts]` |
| rejected_cross_split_near_duplicate | 378 | `[verified: data_summary.json /filter_counts]` |

missing_records表示按本轮筛除顺序进入路径检查的缺失记录，完整附件路径覆盖见既有数据调查。哈希失配、源位深和近重复计数属于候选抽取过程。`[verified: data.py catalog与prepare；既有数据调查报告]`

留出母池为{'test': 1, 'calibration': 2, 'validation': 3}，测试、校准、验证覆盖168、147、184个资产组。初始版本和调整依据见[data_protocol_v1_audit.json](data_protocol_v1_audit.json)。`[verified: data_summary.json；data_protocol_v1_audit.json]`

软件试跑和资源探测合计208张图片及近重复候选已排除，正式模型从各自指定初始化重新训练。`[verified: data_summary.json /filter_counts/excluded_smoke_hashes；训练config.json]`
