# 实现记录

## Deviations

- 当前机器未配置Context7密钥，库接口依据已读取的PyTorch 2.8、uv和scikit-learn官方文档实现。`[verified: 环境检查context7_key_present=False；本轮官方文档读取]`
- 当前机器未发现pueue，任务通过可等待的命令会话执行，并保存进度、检查点和日志。`[verified: Get-Command pueue未返回路径]`
- 官方下载链路实测单连接约0.2–0.3 MB/s，改用镜像传输并由uv按uv.lock导出的精确版本和哈希安装38个依赖。Torch分块下载后另核对官方锁文件SHA-256，锁文件保留官方来源。`[verified: curl测速；uv pip --require-hashes安装输出；私有依赖下载脚本]`
- 为隔离软件试跑与最终测试，正式准备从固定母池剔除smoke的64张图片及近重复候选，原母池的资产分组和折号保留。`[verified: prepare的exclude_manifests流程；protocol.md]`
- 原定第0折仅一个资产组，初始2000张测试全部落在该组。正式协议按折号选前三个类别数量足够且至少50组的折，选后复核覆盖；资源probe的144张也加入排除参考。初始数据版本保存在私有目录，coverage-v2作为正式运行目录。此选择仅使用元数据。`[verified: data_protocol_v1_audit.json；select_split_folds及回归测试]`

## Discovered edge cases

- 快照存在1,480组相同MD4对应不同块大小，按协议整组剔除。`[verified: 本轮预检conflicting_content_hash_groups=1480]`
- 源图含透明度、多种通道用途及不同编码preset/RDO，RGB分类的标签正确率与压缩质量需分别解释。`[verified: 既有数据报告字段分布；用户确认的RGB与LITE实验协议]`
- 断点需先持久化新的最佳模型，再写最近检查点，避免中断后最佳分数与文件错位；已调整保存顺序。`[verified: review发现C1；training.py的save_checkpoint顺序]`
- 仅含PNG签名的截断文件需作为坏样本处理，已增加头长度检查和针对性测试。`[verified: review发现C2；data.py头检查；test_corrupt_and_mismatched_images]`
- TIFF的mode不足以识别源位深，已按BitsPerSample拒绝16位数据并添加真实二进制TIFF回归样本。`[verified: review发现C3；data.py TIFF检查；test_16_bit_rgb_tiff_rejected]`
- 正式校准和测试逐轮核对30轮、每轮10000个样本和157个优化步骤，防止短程探测后恢复的历史被误认为完整训练。`[verified: review发现C4；require_completed_training及对应回归测试]`
- 完整smoke发现inference_mode标签不能直接进入温度拟合的自动微分，已在拟合边界clone输入，并补回归测试。首轮smoke的T=1失败记录保留，使用smoke-v2重新验收校准。`[verified: smoke/temperature.json的Inference tensors错误；metrics.py修复及新增测试]`
- 审查C5发现推理logits直接写入存在中断残包风险，已复用原子检查点写入，并增加中断回归测试。此修改发生于预训练组运行期间，修改前源码按其配置哈希归档，并核对训练相关函数AST。`[verified: review C5；checkpoint_inference；源码快照与training_code_change_audit.json]`
- 重复准备时先比较新旧缓存字节哈希，存在处理配方冲突则保留既有缓存并要求新运行目录。回归测试模拟配方变化，检查旧数据得到保留。`[verified: decode_candidate；test_reprepare_preserves_existing_cache_on_recipe_conflict]`
- 清单保存preset、RDO、路径和像素属性，通道用途需结合Unity导入信息核实，已修正协议表述。`[verified: review C6；正式manifest字段；protocol.md]`

## Questions for review

- 演讲没有可核实的层数和初始化设置，本轮两组ResNet18均作为明确补全的复现设置。`[verified: 演讲12:28网络页；本轮用户确认]`

## 完成摘要

- 计划调整共5项，详情见Deviations。`[verified: 本文Deviations的5条记录]`
- 最需后续核对的选择是留出折的资产组覆盖规则，本轮采用至少50组。`[opinion]`
- 已记录10项数据、恢复、校准或文档边界，并在对应代码和报告中处理。`[verified: 本文Discovered edge cases的10条记录]`
- 两组各完成30轮，最佳模型为第2轮和第7轮，温度拟合均成功。`[verified: verification.json /arms]`
- 后续从training_report.md、protocol.md和verification.json继续核对，保留本轮封存结果。`[opinion]`
