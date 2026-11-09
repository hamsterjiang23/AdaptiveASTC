# GDC分类复现与独立留出集校准

## 固定输入与范围

使用183,051条附件LITE历史标签和原始源图。快照SHA-256为`4b7a5a7314f4e58cefc1a578d7b3d4f609024971692ef8a3c8c65828c548f843`，图片根目录为`F:\MLBB_Test\haijiangli1_HAMSTERMLBB`。标签来源为`C:\Users\admin\Downloads\parameter_cache_detail.json`。`[verified: 本轮预检输出及用户确认方案]`

研究对象为历史选参策略的四类块大小分类。LITE基础PSNR为30，用户研究目标为35；源图与Unity处理后参考图的对应关系需要单独测量。preset、RDO和资源路径保留在清单中，贴图通道用途需结合Unity导入信息核实。`[verified: 既有实际数据调查报告“配置差异”“训练可用性”；正式manifest字段]`

## 清洗与划分

固定类序`6x6,8x8,10x10,12x12`，seed为20261109。单帧8位LDR PNG/JPEG/TGA/BMP/TIFF进入候选，编辑器、插件、工具和Packages排除。冲突内容标签整组排除，一致内容仅保留一个有效源文件；入选样本全量MD4与解码校验。`[verified: 用户确认方案]`

角色、怪物、环境按具体资产目录分组，其余按父目录，同目录SD/HD/FHD变体归组。仍生成10折分层分组；正式留出池按折号递增，选择类别数量足够且至少50个资产组的前三折，其余用于训练。选后再核对每份留出集合至少50组。按总体类别比例和最大余数法选训练10000、验证1000、校准1000、测试2000。原定第0折仅有一个超大资产组，此调整依据元数据完成。`[verified: data_protocol_v1_audit.json；select_split_folds；用户确认的规模与分组要求]`

近重复判据为64位pHash汉明距离≤4、宽高比相差≤1%、32×32 RGB预览RMSE≤3/255。优先保留测试、校准、验证、训练；低优先级冲突从同母池同类补足。清单固定后做隔离与指纹复查。该检查具有上述启发式范围。`[verified: 用户确认方案]`

正式准备显式传入smoke和资源探测清单，先按完整候选生成母池，再剔除试跑用过的内容哈希；这些图片也作为近重复参考，所有正式集合避开相应候选。两组正式模型重新初始化。`[verified: prepare的exclude_manifests流程；正式实验命令]`

## 模型与训练

两组ResNet18分别使用IMAGENET1K_V1和随机初始化，四分类头，全参数训练，共享数据与超参数，各30轮。RGB整图224×224双线性抗锯齿缩放，ImageNet归一化，确定性输入。省略Alpha，记录其样本占比。`[verified: 用户确认方案]`

无权重交叉熵，SGD momentum=0.9、weight_decay=0.0001、lr=0.01，30轮余弦下降。有效batch=64，AMP FP16、workers=2。不足时采用32/16微批量和梯度累积。验证NLL最低选模，同值按准确率与较早轮次。每轮保留最佳/最近检查点及恢复状态。`[verified: 用户确认方案]`

## 校准与封存测试

冻结最佳模型，在独立1000张校准图上分别以NLL拟合log(T)，初值0，CPU float64 L-BFGS最多100次。保留T=1比较，无改善使用1，非有限或优化失败单列。两模型与温度锁定后统一测试。`[verified: 用户确认方案]`

报告accuracy、macro F1、balanced accuracy、逐类precision/recall、混淆矩阵、训练多数类基线，及NLL、多类Brier、15等宽箱ECE和可靠性图。Brier为逐样本各类平方误差之和的平均。正温度下断言argmax一致，概率指标与实际压缩质量分别解释。`[verified: 用户确认方案；Guo等§4.2公式9]`

## 工具与报告

Python3.12与uv统一管理，torch2.8.0/torchvision0.23.0使用官方cu128来源。uv.lock锁定依赖。64张smoke成功后进入正式准备和训练，记录准备、训练、预测耗时以及资源峰值。`[verified: 用户确认方案]`

正式产物由实际运行生成，[数据报告](data_report.md)、[训练与校准报告](training_report.md)和[验证记录](verification.json)分别记录运行证据。逐图数据、检查点、原始日志和缓存在`../.local/`中。`[opinion]`
