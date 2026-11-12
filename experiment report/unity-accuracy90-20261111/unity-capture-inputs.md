# 原生采集记录到模型输入的对齐检查

新增 `UnityCaptureInputAdapter`，直接从原生参考 PNG、导入属性与实际编码回调构造 Native240 输入，不需要候选解码图、patch 误差目标或搜索标签。真实开发样本核对通过：按资产路径去重的68张图片、812个patch 的 RGBA、有效区域掩码、元数据、索引及决策输入与训练端完全一致。此次为输入接口检查，没有模型 forward、训练或独立确认集评价。`[verified: unity_capture_input.py __init__/project/dataset；unity-capture-input-verification.json unique_images、unique_patches、max_tensor_difference、decision_inputs_equal、model_forward_calls]`

## 输入契约

- 保留显式 train／validation／confirmation 身份和资产顺序，拒绝混合划分、重复资产、导入与回调路径不一致、PNG 哈希／尺寸／RGBA 回调哈希不一致。RGBA 回调按上下翻转后的字节核对，模型仍读取参考 PNG 的显示方向。`[verified: unity_capture_input.py __init__/project；unity_inference.py pixels]`
- 只接受与现有训练协议相同的 LDR Tex2D RGBA 输入、Default／Sprite／NormalMap 用途及 `normal_pack=false`。sRGB、Alpha 需求从实际导入／回调核对；恒定 Alpha 与黑像素比例从参考图计算。法线评价 mip 深度由输入尺寸与 mipmaps 属性推导，最多四级；颜色图输入该维度为1。`[verified: unity_capture_input.py project；unity_capture_input.py UnityInferenceTexture.validate调用]`
- 模型输入对象与决策输入不携带原搜索选择、候选质量或监督文件；改变这些字段不改变输入指纹和张量，缺失的监督路径也不读取。构造 Dataset 前及核验结束后检查参考文件哈希。`[verified: test_unity_capture_input.py test_search_labels_and_targets_cannot_change_input_or_fingerprint、test_pixel_mutation_before_inference_is_rejected；capture_input_audit.py run]`
- 该适配器要求调用方先核验原生采集来源，并在独立模型 forward 前完成模型／规则冻结。它自身不替代来源审计、像素隔离或测试封存，也不会开启模型评价。`[verified: unity_capture_input.py class docstring；opinion: 接入约束]`

## 真实数据检查

| 输入来源 | 比较范围 | 结果 |
|---|---|---|
| 已完成66图语料 | train64／validation2，共794patch；Default和NormalMap，法线评价mip深度1 | 所有输入张量及决策输入一致。`[verified: unity-capture-input-parity68-v1.json splits前两项]` |
| 多mip法线语料 | train2／validation2，共31patch；法线评价mip深度4 | 所有输入张量及决策输入一致。`[verified: unity-capture-input-parity68-v1.json splits后两项]` |
| 合并覆盖 | 原始70次图像／825次patch比较；其中两张validation重复，按资产路径去重后覆盖68图／812patch | 重复记录的参考与目标哈希一致，分开统计比较次数与按资产路径去重后的覆盖。`[verified: unity-capture-input-verification.json observed_images、observed_patches、unique_images、unique_patches、duplicate_comparisons]` |

检查内部耗时7.87秒，含进程启动的墙钟11.76秒；使用单CPU计算线程，没有GPU模型推理或编码。Sprite目前由合成单元测试覆盖，本次真实语料的用途仅包含Default和NormalMap，不据此声称完成真实Sprite输入核验。`[verified: unity-capture-input-verification.json internal_seconds、process_seconds；capture_input_audit.py run；unity-capture-input-parity68-v1.json texture_types；test_unity_capture_input.py 参数化用例]`

## 文件与复跑

- [冻结配置](unity-capture-input-parity68-v1-config.json)绑定两个已完成开发语料及11份相关源码。`[verified: 对应JSON corpora、sources_sha256]`
- [原始对齐报告](unity-capture-input-parity68-v1.json)保留逐划分范围、输入指纹与结果；[核验记录](unity-capture-input-verification.json)保留去重统计、原任务回执SHA和完整耗时。`[verified: 对应JSON splits、input_fingerprint、process_receipt_sha256]`
- 可复跑入口为 `script/audit_unity_capture_inputs.py --config <新配置>`，新配置使用新的公开report路径；既有输出拒绝覆盖。启动参数仍通过uv管理，原始进程日志在 `.local/unity-accuracy90-20261111/jobs/unity-capture-input-parity68-v1/`。`[verified: script/audit_unity_capture_inputs.py main；capture_input_audit.py run；对应job receipt command]`

49项CPU测试通过，覆盖无标签依赖、回调／导入属性冲突、PNG变化、法线mip、已有输出保护与空语料拒绝。代码格式、Ruff与类型检查按本轮实际结果记录；真实确认集输入、独立模型预测、最终编码和90%验收仍待后续完成。活动数据／训练／确认采集的14／23／15／17份源码绑定及V1原始证据哈希均保持一致。`[verified: pytest tests/test_unity_capture_input.py tests/test_unity_inference.py 49 passed；unity-capture-input-verification.json unchanged_active_sources、v1_evidence_sha256；opinion: 完成边界]`
