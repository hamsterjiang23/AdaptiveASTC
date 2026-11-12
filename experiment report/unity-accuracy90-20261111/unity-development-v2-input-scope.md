# 开发语料的 V2 输入范围检查

2026-11-12，完整开发语料的导入属性检查发现18张Cube：训练集13张、验证集5张。原采集、20候选测量、patch目标和规则重放均已完成，但这些图片超出V2规定的Tex2D输入范围，因此开发语料尚不能标记为V2范围验收通过。`[verified: unity-development-v2-input-scope-initial.json counts、out_of_scope_counts、v2_input_scope_ready；unity-development-data11000-verification.json；experiment plan/V2/README.md“Unity协议”]`

| 划分 | 原始语料 | Cube | 其余符合类型范围的图片 |
|---|---:|---:|---:|
| train | 10000 | 13 | 9987。`[verified: unity-development-v2-input-scope-initial.json counts、out_of_scope_counts]` |
| validation | 1000 | 5 | 995。`[verified: unity-development-v2-input-scope-initial.json counts、out_of_scope_counts]` |

这18张的实际类型均为Default／Cube。原生输入适配器`UnityCaptureInputAdapter.project`对全部18张均明确拒绝；另检查了Default、Sprite和NormalMap各一张Tex2D，三张均通过属性与像素一致性检查。本次没有模型forward或训练。`[verified: unity-development-v2-input-scope-verification.json actual_input_adapter_rejections、supported_examples、model_forward_calls、training_updates]`

原开发清单、图像、标签、候选测量、计时和报告保持不变。已向用户提交一个范围决定：补采18张并生成新版本，保留10000／1000规模；或为V2生成排除18张的视图，使用9987／995。处理方式待确认，不能按任一选项提前修改划分。`[verified: 本轮异步问题；unity-development-v2-input-scope-initial.json decision、source_splits_modified]`

修订后的确认集2000张继续独立采集，完整像素审计队列也保持。当前收尾验证器新增开发集Tex2D检查；范围问题解决前不允许宣布V2数据交接完成。随后需按获批的新开发范围核对确认集隔离、实际输入准入与像素审计覆盖。`[verified: unity-data-delivery-verifier-readiness.json status、development_scope_audit；verify_data_delivery_v2.py 开发语料范围断言；opinion: 后续验收范围]`

证据入口：[逐图范围清单](unity-development-v2-input-scope-initial.json)、[实际输入适配器验证](unity-development-v2-input-scope-verification.json)、[数据交接](unity-data-handoff.md)。`[verified: 对应本地文件]`
