# V3独立确认执行记录

## Deviations

- 本轮用户已授权正式测试。保留开发期confirmation-contract.json原件，新增执行合同绑定该文件SHA、用户授权、V3选定权重与运行来源。`[verified: 用户本轮授权；experiment report/unity-v3-20261113/confirmation-contract.json]`
- 旧确认入口的模型准入绑定V2权重身份。新增V3入口复用修订确认集审计、Unity输入适配、V3部署、质量复算及共享seal。`[verified: forward_system_evidence.py L25–81；opinion: 兼容实现]`

## Discovered edge cases

- files批量与pixels_ready的8图分组，以及逐图模式，使用各自实测结果；逐轮一致性按同一计时口径检查。`[verified: v3_benchmark.py measure、run]`
- 机器当前未安装pueue，正式任务通过持续运行的exec会话及独立进度回执跟进。`[verified: 本轮Get-Command pueue为空；opinion: 调度选择]`
- 审查C1–C5已修复，覆盖seal失败状态、像素就绪预测留存与全局顺序、输出完整性、小样本身份以及可选缺失文件绑定。六项新增回归检查及相关旧检查合计106项通过，独立代码复审为clean。`[verified: tests/test_unity_v3_confirmation.py；本轮pytest与review输出]`
- 开发验证8图完成12个正式计时单元，起点、最终候选、查询轨迹和ASTC SHA均与既有V3同图结果一致。小样本用于执行闭环，其准确率按实际样本记录。`[verified: smoke-result.json；smoke-verification.json]`
- 2000确认图复审完成，输入指纹4bf92bf4e4659afa6c5d733f92d9125af69a2ae0fb215eb3bcb0fc5bfb5abc92、12个规则上下文与原合同一致，准备过程0次forward。`[verified: preparation.json]`
- 正式测试在共享cohort 43b77eb2...封存后启动，执行配置execution-config-v2.json，seal指纹8107309f811f8057fd90cbe6776272cdfc4bf2aa138c703a82be65b77958ccb8。进程PID45476，exec会话7697。`[verified: execution-seal.json；result.json；启动时进程检查]`
- 各计时单元分别8图预热一次，再运行三次正式重复。主评分取files/batch，像素就绪使用8图分组，逐图模式使用其实际延迟分布。`[verified: v3_confirmation.py evaluate、measure；execution-config-v2.json timing]`
- pixels_ready每8图建立独立trial，progress.json的completed_images和encoding_attempts为当前组内计数。聚合时source_index恢复完整2000图的全局顺序，最终覆盖通过完整trace及输出清单核对。`[verified: v3_confirmation.py L237–247；progress.json；opinion: 进度解读]`
- 文件输入的批量与逐图模式已各完成三轮，全部汇总指标一致。额外复核六份trace中的12000张次，起点、实际查询质量、全局索引与最终ASTC一致。`[verified: result.json measurements[0..5]；本轮trace_signatures核对输出]`
- 使用首轮2000图的实际指标制作临时图表布局预览，修复图例与数值重叠，预览只用于视觉检查。最终报告仍等待12个计时单元、共享seal及完整输出核验完成。`[verified: tmp/pdfs/v3-independent-test-preview/test-results.png；build_test_report.py main、overview；opinion: 报告交付安排]`

## Questions for review

- 开发集小样本闭环完成后，冻结一次确认合同并进行2000图正式评价。验收按系统块大小Top-1达到90%报告，确认结果用于独立评价。`[verified: 用户V3计划第5节；opinion: 执行安排]`

## 正式结果

- 12个计时单元完成，正式进程正常退出。共享cohort仅1次attempt，状态passed，模型参数与buffer保持，训练更新0次。`[verified: result.json status、model_parameters_and_buffers_unchanged、training_updates；共享seal attempts；exec会话7697 exit_code=0]`
- 系统块大小匹配1953／2000，完整配置匹配1733／2000，严格质量通过1772／2000，相对原标签严格质量回退0张。续搜纠正124张起点错误，新增错误0张，47张最终未匹配均使用更小块。`[verified: result.json summary；report-verification.json paired_start_to_final、quality_outcomes]`
- 文件批量三轮中位数摊销620.91 ms／图，文件逐图平均值的三轮中位数630.12 ms／图，像素就绪分别591.35和616.81 ms／图。确认图平均像素数为开发验证的4.23倍。`[verified: result.json results；report-verification.json dataset_size]`
- 16008份输出及记录、12份查询轨迹、12份重复预测档案已重新核验，24000条逐图重复轨迹一致，CSV含完整2000张。`[verified: report-verification.json saved_files_verified、traces_verified、prediction_archives_verified、per_image_trace_consistency_checks、csv_rows]`
- PDF为4页，嵌入中文字体，缺字检测0，逐页渲染及图表视觉检查通过。正式测试后再次运行相关CPU检查，106项通过，耗时8.95秒。`[verified: pdf-verification.json；report-verification.json latest_cpu_tests；本轮PDF页图检查]`
- execution-seal.json指针已同步正式完成状态。原开发合同与共享seal的身份不变，终态result.json保留原始执行结果。`[verified: execution-seal.json status、test_opened、fingerprint；report-verification.json shared_seal_verified]`
